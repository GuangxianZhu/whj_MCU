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
static uint8_t sent[256]; static uint16_t sent_n;
static uint8_t reply[256]; static uint16_t reply_n, reply_pos;
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

    /* 8. Sync Write matches the e-Manual example (ID1 = 150, ID2 = 170 to Goal Position) */
    reset();
    const uint8_t ids[2] = {1, 2};
    const int32_t goals[2] = {150, 170};
    r = dxl_sync_write_goal_position(ids, 2, goals);
    const uint8_t sw_ref[] = {0xFF,0xFF,0xFD,0x00,0xFE,0x11,0x00,0x83,0x74,0x00,0x04,0x00,
                              0x01,0x96,0x00,0x00,0x00,0x02,0xAA,0x00,0x00,0x00,0x82,0x87};
    CHECK(r == DXL_OK && sent_n == sizeof sw_ref && memcmp(sent, sw_ref, sent_n) == 0,
          "Sync Write packet = e-Manual example");
    CHECK(dir_after == -1, "Sync Write does not wait for a reply");

    /* 9. Sync Read matches the e-Manual example, replies taken byte for byte from it */
    reset();
    const uint8_t sr_ref[] = {0xFF,0xFF,0xFD,0x00,0xFE,0x09,0x00,0x82,0x84,0x00,0x04,0x00,0x01,0x02,0xCE,0xFA};
    const uint8_t st1[] = {0xFF,0xFF,0xFD,0x00,0x01,0x08,0x00,0x55,0x00,0xA6,0x00,0x00,0x00,0x8C,0xC0};
    const uint8_t st2[] = {0xFF,0xFF,0xFD,0x00,0x02,0x08,0x00,0x55,0x00,0x1F,0x08,0x00,0x00,0xBA,0xBE};
    memcpy(reply, st1, sizeof st1); memcpy(reply + sizeof st1, st2, sizeof st2);
    reply_n = sizeof st1 + sizeof st2;
    int32_t pp[2] = {0, 0}; int res[2] = {9, 9};
    r = dxl_sync_read_present_position(ids, 2, pp, res);
    CHECK(sent_n == sizeof sr_ref && memcmp(sent, sr_ref, sent_n) == 0, "Sync Read packet = e-Manual example");
    CHECK(r == DXL_OK && pp[0] == 166 && pp[1] == 2079 && res[0] == DXL_OK && res[1] == DXL_OK,
          "Sync Read replies parsed: ID1 = 166, ID2 = 2079");

    /* 10. Sync Read with ID 1 missing: ID 2 still lands in its own slot */
    reset();
    memcpy(reply, st2, sizeof st2); reply_n = sizeof st2;
    pp[0] = pp[1] = -1; res[0] = res[1] = 9;
    r = dxl_sync_read_present_position(ids, 2, pp, res);
    CHECK(r == DXL_ERR_TIMEOUT && res[0] == DXL_ERR_TIMEOUT && res[1] == DXL_OK && pp[1] == 2079,
          "Sync Read: missing ID 1 reported, ID 2 still read");

    /* 11. Reboot packet matches the e-Manual example */
    reset(); queue_status(1, 0, 0, 0, 0);
    r = dxl_reboot(1);
    const uint8_t rb_ref[] = {0xFF,0xFF,0xFD,0x00,0x01,0x03,0x00,0x08,0x2F,0x4E};
    CHECK(r == DXL_OK && sent_n == sizeof rb_ref && memcmp(sent, rb_ref, sent_n) == 0, "Reboot packet = e-Manual example");

    /* 12. Change ID 1 -> 2: torque off, write ID, ping the new ID */
    reset();
    {
        uint16_t k = 0;
        k += dxl_build_packet(1, 0x55, (const uint8_t[]){0x00}, 1, reply + k, 40);               /* torque off */
        k += dxl_build_packet(1, 0x55, (const uint8_t[]){0x00}, 1, reply + k, 40);               /* write ID   */
        k += dxl_build_packet(2, 0x55, (const uint8_t[]){0x00, 0xB0, 0x04, 0x2E}, 4, reply + k, 40); /* ping 2 */
        reply_n = k;
    }
    r = dxl_set_id(1, 2);
    const uint8_t id_ref[] = {0xFF,0xFF,0xFD,0x00,0x01,0x06,0x00,0x03,0x07,0x00,0x02,0xBD,0x63};
    int found = 0;
    for (uint16_t k = 0; k + sizeof id_ref <= sent_n; k++) if (memcmp(sent + k, id_ref, sizeof id_ref) == 0) found = 1;
    CHECK(r == DXL_OK && found, "set ID 1 -> 2 sends FF FF FD 00 01 06 00 03 07 00 02 BD 63 and the new ID answers");

    printf(fails ? "\n%d FAILED\n" : "\nall passed\n", fails);
    return fails ? 1 : 0;
}
