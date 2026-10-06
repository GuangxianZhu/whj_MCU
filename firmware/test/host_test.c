/*
 * host_test.c — checks the driver on a PC, with a fake servo behind the port.
 *
 *   cc -std=c99 -Wall -Wextra -I../dxl ../dxl/dxl.c host_test.c -o host_test && ./host_test
 */
#include <stdio.h>
#include <string.h>
#include "dxl.h"
#include "dxl_port.h"

/* ---- fake port ---- */
static uint8_t sent[128]; static uint16_t sent_n;
static uint8_t reply[128]; static uint16_t reply_n, reply_pos;
static int dir_tx, dir_during_write = -1, dir_after = -1;

void dxl_port_set_tx(int tx) { dir_tx = tx; }
void dxl_port_write(const uint8_t *d, uint16_t n) { memcpy(sent + sent_n, d, n); sent_n += n; dir_during_write = dir_tx; }
void dxl_port_wait_tx_complete(void) {}
void dxl_port_flush_rx(void) {}
int dxl_port_read_byte(uint8_t *b, uint32_t t) { (void)t; dir_after = dir_tx; if (reply_pos >= reply_n) return 0; *b = reply[reply_pos++]; return 1; }

static void reset(void) { sent_n = 0; reply_n = 0; reply_pos = 0; dir_during_write = dir_after = -1; }
static void queue_status(uint8_t id, uint8_t err, const uint8_t *p, uint16_t n, int noise)
{
    uint8_t params[64];
    params[0] = err; memcpy(params + 1, p, n);
    uint16_t k = 0;
    if (noise) { reply[k++] = 0x00; reply[k++] = 0xFF; }          /* junk before header */
    uint16_t len = dxl_build_packet(id, 0x55, params, (uint16_t)(n + 1), reply + k, (uint16_t)(sizeof reply - k));
    reply_n = (uint16_t)(k + len);
}

static int fails;
#define CHECK(c, msg) do { if (c) printf("ok   %s\n", msg); else { printf("FAIL %s\n", msg); fails++; } } while (0)

int main(void)
{
    /* 1. ping packet matches the ROBOTIS e-Manual example */
    const uint8_t ping_ref[] = {0xFF,0xFF,0xFD,0x00,0x01,0x03,0x00,0x01,0x19,0x4E};
    uint8_t buf[64];
    uint16_t n = dxl_build_packet(1, DXL_INST_PING, 0, 0, buf, sizeof buf);
    CHECK(n == sizeof ping_ref && memcmp(buf, ping_ref, n) == 0, "ping packet = FF FF FD 00 01 03 00 01 19 4E");

    /* 2. ping round trip with a fake XL330-M288 (model 1200 = 0x04B0, fw 0x2E) */
    reset();
    const uint8_t pr[] = {0xB0, 0x04, 0x2E};
    queue_status(1, 0, pr, 3, 1);
    uint16_t model = 0;
    int r = dxl_ping(1, &model);
    CHECK(r == DXL_OK && model == 1200, "ping reply parsed, model 1200 (with junk before header)");
    CHECK(dir_during_write == 1 && dir_after == 0, "DIR = 1 while sending, 0 while receiving");

    /* 3. LED write packet */
    reset(); queue_status(1, 0, 0, 0, 0);
    r = dxl_set_led(1, 1);
    const uint8_t led_ref[] = {0xFF,0xFF,0xFD,0x00,0x01,0x06,0x00,0x03,0x41,0x00,0x01,0xCC,0xE6};
    CHECK(r == DXL_OK && sent_n == sizeof led_ref && memcmp(sent, led_ref, sent_n) == 0, "LED on packet");

    /* 4. byte stuffing on transmit: FF FF FD inside params gets an extra FD */
    const uint8_t sp[] = {0x10, 0x00, 0xFF, 0xFF, 0xFD, 0x07};
    n = dxl_build_packet(1, DXL_INST_WRITE, sp, sizeof sp, buf, sizeof buf);
    CHECK(n == 7 + 1 + 7 + 2 && buf[13] == 0xFD && buf[14] == 0x07 && buf[5] == 10, "transmit byte stuffing and LEN");

    /* 5. read present position, including a stuffed value in the reply */
    reset();
    const uint8_t pos[] = {0xFF, 0xFF, 0xFD, 0x00};     /* = 0x00FDFFFF */
    queue_status(1, 0, pos, 4, 0);
    int32_t p = 0;
    r = dxl_get_present_position(1, &p);
    CHECK(r == DXL_OK && p == 0x00FDFFFF, "read position with receive destuffing");

    /* 6. timeout and CRC error */
    reset();
    CHECK(dxl_ping(1, 0) == DXL_ERR_TIMEOUT, "no reply -> timeout");
    reset(); queue_status(1, 0, pr, 3, 0); reply[reply_n - 1] ^= 0x55;
    CHECK(dxl_ping(1, 0) == DXL_ERR_CRC, "corrupted reply -> CRC error");

    /* 7. servo error byte */
    reset(); queue_status(1, 0x02, 0, 0, 0);
    uint8_t e = 0;
    r = dxl_txrx(1, DXL_INST_WRITE, sp, 2, 0, 0, 0, &e);
    CHECK(r == DXL_ERR_STATUS && e == 0x02, "servo error byte reported");

    printf(fails ? "\n%d FAILED\n" : "\nall passed\n", fails);
    return fails ? 1 : 0;
}
