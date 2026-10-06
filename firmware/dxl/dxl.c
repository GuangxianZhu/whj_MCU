/*
 * dxl.c — minimal DYNAMIXEL Protocol 2.0 driver (see dxl.h).
 *
 * Packet layout:
 *   FF FF FD 00 | ID | LEN_L LEN_H | INST | PARAMS... | CRC_L CRC_H
 *   LEN counts INST + PARAMS + CRC, after byte stuffing.
 *   Byte stuffing: whenever FF FF FD appears from INST onwards, an extra FD
 *   is inserted after it so it cannot be mistaken for a header.
 */
#include "dxl.h"
#include "dxl_port.h"

#define HDR_LEN   7   /* FF FF FD 00 ID LEN_L LEN_H */
#define IDX_ID    4
#define IDX_LEN_L 5
#define IDX_LEN_H 6
#define IDX_INST  7
#define IDX_ERR   8
#define STATUS_INST 0x55

static uint8_t s_tx[DXL_BUF_SIZE];
static uint8_t s_rx[DXL_BUF_SIZE];

uint16_t dxl_crc16(const uint8_t *data, uint16_t n)
{
    uint16_t crc = 0;
    while (n--) {
        crc ^= (uint16_t)(*data++) << 8;
        for (int i = 0; i < 8; i++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x8005) : (uint16_t)(crc << 1);
    }
    return crc;
}

uint16_t dxl_build_packet(uint8_t id, uint8_t inst,
                          const uint8_t *params, uint16_t n,
                          uint8_t *out, uint16_t out_max)
{
    uint16_t i = 0;
    if (out_max < HDR_LEN + 1 + 2) return 0;
    out[i++] = 0xFF; out[i++] = 0xFF; out[i++] = 0xFD; out[i++] = 0x00;
    out[i++] = id;
    i += 2;                         /* LEN filled in below */
    out[i++] = inst;
    for (uint16_t k = 0; k < n; k++) {
        if (i + 1 + 1 + 2 > out_max) return 0;   /* byte + possible stuff + CRC */
        out[i++] = params[k];
        if (i - 3 >= IDX_INST &&
            out[i - 3] == 0xFF && out[i - 2] == 0xFF && out[i - 1] == 0xFD)
            out[i++] = 0xFD;
    }
    uint16_t len = (uint16_t)(i - IDX_INST + 2);
    out[IDX_LEN_L] = (uint8_t)(len & 0xFF);
    out[IDX_LEN_H] = (uint8_t)(len >> 8);
    uint16_t crc = dxl_crc16(out, i);
    out[i++] = (uint8_t)(crc & 0xFF);
    out[i++] = (uint8_t)(crc >> 8);
    return i;
}

/* Receive one status packet into s_rx. Returns total length or an error. */
static int receive_status(void)
{
    uint8_t b;
    uint16_t i = 0;

    /* hunt for the header FF FF FD 00 */
    while (i < 4) {
        if (!dxl_port_read_byte(&b, DXL_BYTE_TIMEOUT_MS)) return DXL_ERR_TIMEOUT;
        static const uint8_t hdr[4] = {0xFF, 0xFF, 0xFD, 0x00};
        if (b == hdr[i]) {
            s_rx[i++] = b;
        } else if (b == 0xFF) {           /* e.g. FF FF FF FD: keep the last two FF */
            i = (i >= 1 && s_rx[i - 1] == 0xFF) ? 2 : 1;
            s_rx[0] = 0xFF; s_rx[1] = 0xFF;
        } else {
            i = 0;
        }
    }
    for (; i < HDR_LEN; i++) {
        if (!dxl_port_read_byte(&b, DXL_BYTE_TIMEOUT_MS)) return DXL_ERR_TIMEOUT;
        s_rx[i] = b;
    }
    uint16_t len = (uint16_t)(s_rx[IDX_LEN_L] | (s_rx[IDX_LEN_H] << 8));
    if (len < 4 || HDR_LEN + len > DXL_BUF_SIZE) return DXL_ERR_FORMAT;
    for (uint16_t k = 0; k < len; k++) {
        if (!dxl_port_read_byte(&b, DXL_BYTE_TIMEOUT_MS)) return DXL_ERR_TIMEOUT;
        s_rx[i++] = b;
    }
    uint16_t crc = (uint16_t)(s_rx[i - 2] | (s_rx[i - 1] << 8));
    if (dxl_crc16(s_rx, (uint16_t)(i - 2)) != crc) return DXL_ERR_CRC;
    if (s_rx[IDX_INST] != STATUS_INST) return DXL_ERR_FORMAT;
    return (int)i;
}

int dxl_txrx(uint8_t id, uint8_t inst, const uint8_t *params, uint16_t n,
             uint8_t *reply_params, uint16_t reply_max, uint16_t *reply_n,
             uint8_t *servo_err)
{
    uint16_t tx_len = dxl_build_packet(id, inst, params, n, s_tx, DXL_BUF_SIZE);
    if (tx_len == 0) return DXL_ERR_ARG;
    if (reply_n) *reply_n = 0;

    dxl_port_flush_rx();
    dxl_port_set_tx(1);
    dxl_port_write(s_tx, tx_len);
    dxl_port_wait_tx_complete();
    dxl_port_set_tx(0);               /* XL330 replies after ~500 us by default */

    if (id == DXL_BROADCAST_ID) return DXL_OK;

    int rx_len = receive_status();
    if (rx_len < 0) return rx_len;
    if (s_rx[IDX_ID] != id) return DXL_ERR_ID;

    /* destuff the parameters: they sit between the error byte and the CRC */
    uint16_t out = 0;
    uint16_t end = (uint16_t)(rx_len - 2);
    for (uint16_t k = IDX_ERR + 1; k < end; k++) {
        if (k >= IDX_INST + 3 && s_rx[k] == 0xFD &&
            s_rx[k - 1] == 0xFD && s_rx[k - 2] == 0xFF && s_rx[k - 3] == 0xFF)
            continue;                 /* stuffed byte */
        if (reply_params && out < reply_max) reply_params[out] = s_rx[k];
        out++;
    }
    if (reply_n) *reply_n = out;
    if (servo_err) *servo_err = s_rx[IDX_ERR];
    return (s_rx[IDX_ERR] & 0x7F) ? DXL_ERR_STATUS : DXL_OK;
}

int dxl_ping(uint8_t id, uint16_t *model_number)
{
    uint8_t p[3];
    uint16_t n;
    int r = dxl_txrx(id, DXL_INST_PING, 0, 0, p, sizeof p, &n, 0);
    if (r == DXL_OK && model_number) *model_number = (n >= 2) ? (uint16_t)(p[0] | (p[1] << 8)) : 0;
    return r;
}

int dxl_write(uint8_t id, uint16_t addr, const uint8_t *data, uint16_t n)
{
    uint8_t p[DXL_BUF_SIZE];
    if ((uint32_t)n + 2u > (uint32_t)sizeof p) return DXL_ERR_ARG;
    p[0] = (uint8_t)(addr & 0xFF);
    p[1] = (uint8_t)(addr >> 8);
    for (uint16_t k = 0; k < n; k++) p[2 + k] = data[k];
    return dxl_txrx(id, DXL_INST_WRITE, p, (uint16_t)(n + 2), 0, 0, 0, 0);
}

int dxl_read(uint8_t id, uint16_t addr, uint16_t n, uint8_t *out)
{
    uint8_t p[4] = {(uint8_t)(addr & 0xFF), (uint8_t)(addr >> 8),
                    (uint8_t)(n & 0xFF), (uint8_t)(n >> 8)};
    uint16_t got;
    int r = dxl_txrx(id, DXL_INST_READ, p, 4, out, n, &got, 0);
    if (r == DXL_OK && got != n) return DXL_ERR_FORMAT;
    return r;
}

int dxl_set_led(uint8_t id, uint8_t on)
{
    uint8_t v = on ? 1 : 0;
    return dxl_write(id, XL330_ADDR_LED, &v, 1);
}

int dxl_set_torque(uint8_t id, uint8_t on)
{
    uint8_t v = on ? 1 : 0;
    return dxl_write(id, XL330_ADDR_TORQUE_ENABLE, &v, 1);
}

int dxl_set_goal_position(uint8_t id, int32_t position)
{
    uint32_t u = (uint32_t)position;
    uint8_t v[4] = {(uint8_t)u, (uint8_t)(u >> 8), (uint8_t)(u >> 16), (uint8_t)(u >> 24)};
    return dxl_write(id, XL330_ADDR_GOAL_POSITION, v, 4);
}

int dxl_get_present_position(uint8_t id, int32_t *position)
{
    uint8_t v[4];
    int r = dxl_read(id, XL330_ADDR_PRESENT_POSITION, 4, v);
    if (r == DXL_OK && position)
        *position = (int32_t)((uint32_t)v[0] | ((uint32_t)v[1] << 8) |
                              ((uint32_t)v[2] << 16) | ((uint32_t)v[3] << 24));
    return r;
}
