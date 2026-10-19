/*
 * bridge_test.c — checks the PC <-> XL330 bridge on a PC, with a fake clock,
 * a fake PC port and two fake servos (ID 1 and ID 2) on the bus.
 *
 *   cc -std=c99 -Wall -Wextra -I../dxl -I../bridge ../dxl/dxl.c ../bridge/bridge.c bridge_test.c -o bridge_test && ./bridge_test
 */
#include <stdio.h>
#include <string.h>
#include "dxl.h"
#include "dxl_port.h"
#include "bridge.h"
#include "bridge_port.h"

/* ---- fake clock and PC port ---- */
static uint32_t now;
uint32_t bridge_now_ms(void) { return now; }
static uint8_t pc_out[1024]; static uint16_t pc_out_n;
void bridge_pc_write(const uint8_t *d, uint16_t n) { memcpy(pc_out + pc_out_n, d, n); pc_out_n += n; }

/* ---- fake servo bus ---- */
static uint8_t bus_sent[1024]; static uint16_t bus_sent_n; static int packets_on_bus;
static uint8_t bus_rx[1024]; static uint16_t bus_rx_n, bus_rx_pos;
static int dir, dir_during_write = -1, dir_when_reading = -1;
static int servo_present[3] = {0, 1, 1};       /* index = ID */

static void servo_reply(uint8_t id)            /* status packet of a ping, model 1200 */
{
    const uint8_t p[4] = {0x00, 0xB0, 0x04, 0x2E};
    bus_rx_n += dxl_build_packet(id, 0x55, p, 4, bus_rx + bus_rx_n, (uint16_t)(sizeof bus_rx - bus_rx_n));
}

void dxl_port_set_tx(int tx) { dir = tx; }
void dxl_port_write(const uint8_t *d, uint16_t n)
{
    memcpy(bus_sent + bus_sent_n, d, n); bus_sent_n += n; packets_on_bus++;
    dir_during_write = dir;
    uint8_t id = d[4], inst = d[7];
    if (inst == 0x01 && id == 0xFE) { if (servo_present[1]) servo_reply(1); if (servo_present[2]) servo_reply(2); }
    else if (inst == 0x01 && id < 3 && servo_present[id]) servo_reply(id);
}
void dxl_port_wait_tx_complete(void) {}
void dxl_port_flush_rx(void) { bus_rx_n = bus_rx_pos = 0; }
int dxl_port_read_byte(uint8_t *b, uint32_t timeout_ms)
{
    dir_when_reading = dir;
    if (bus_rx_pos < bus_rx_n) { *b = bus_rx[bus_rx_pos++]; return 1; }
    now += timeout_ms;                         /* nothing came: the full timeout passes */
    return 0;
}

/* ---- helpers ---- */
static void reset_all(void)
{
    bridge_init();
    pc_out_n = 0; bus_sent_n = 0; packets_on_bus = 0; bus_rx_n = bus_rx_pos = 0;
    dir_during_write = dir_when_reading = -1;
}
static void pc_sends(const uint8_t *d, uint16_t n) { for (uint16_t k = 0; k < n; k++) bridge_pc_rx_isr(d[k]); }
static void poll_n(int n) { while (n--) { bridge_poll(); now += 1; } }

static int fails;
#define CHECK(c, msg) do { if (c) printf("ok   %s\n", msg); else { printf("FAIL %s\n", msg); fails++; } } while (0)

static const uint8_t PING1[] = {0xFF,0xFF,0xFD,0x00,0x01,0x03,0x00,0x01,0x19,0x4E};
static const uint8_t PING3[] = {0xFF,0xFF,0xFD,0x00,0x03,0x03,0x00,0x01,0x00,0x00};   /* CRC fixed below */
static const uint8_t PING_ALL[] = {0xFF,0xFF,0xFD,0x00,0xFE,0x03,0x00,0x01,0x31,0x42};
static const uint8_t SYNC_WRITE[] = {0xFF,0xFF,0xFD,0x00,0xFE,0x11,0x00,0x83,0x74,0x00,0x04,0x00,
                                     0x01,0x96,0x00,0x00,0x00,0x02,0xAA,0x00,0x00,0x00,0x82,0x87};

static uint8_t app_got[64]; static uint16_t app_got_n; static int app_timed_out = -1;
static void app_reply(const uint8_t *b, uint16_t n, int to) { memcpy(app_got, b, n); app_got_n = n; app_timed_out = to; }

int main(void)
{
    uint8_t expect[64];
    const uint8_t pr[4] = {0x00, 0xB0, 0x04, 0x2E};
    uint16_t expect_n = dxl_build_packet(1, 0x55, pr, 4, expect, sizeof expect);

    /* 1. ping from the PC: forwarded unchanged, reply forwarded unchanged */
    reset_all();
    pc_sends(PING1, sizeof PING1); poll_n(2);
    CHECK(bus_sent_n == sizeof PING1 && memcmp(bus_sent, PING1, bus_sent_n) == 0, "PC ping goes on the bus byte for byte");
    CHECK(dir_during_write == 1 && dir_when_reading == 0, "DIR = 1 while sending, 0 while waiting for the reply");
    CHECK(pc_out_n == expect_n && memcmp(pc_out, expect, expect_n) == 0, "servo reply goes back to the PC byte for byte");

    /* 2. packet arriving in two pieces, 5 ms apart: still one packet */
    reset_all();
    pc_sends(PING1, 5); poll_n(5); CHECK(packets_on_bus == 0, "half a packet is not sent");
    pc_sends(PING1 + 5, 5); poll_n(2); CHECK(packets_on_bus == 1, "second half arrives -> packet sent");

    /* 3. bytes stop in the middle for longer than BRIDGE_PC_GAP_MS: half packet dropped */
    reset_all();
    pc_sends(PING1, 5); poll_n(BRIDGE_PC_GAP_MS + 5);
    pc_sends(PING1 + 5, 5); poll_n(2);
    CHECK(packets_on_bus == 0 && bridge_stats()->pc_timeouts == 1, "interrupted packet is thrown away");
    pc_sends(PING1, sizeof PING1); poll_n(2);
    CHECK(packets_on_bus == 1, "next full packet works again");

    /* 4. wrong CRC: never reaches the bus */
    reset_all();
    uint8_t bad[sizeof PING1]; memcpy(bad, PING1, sizeof bad); bad[9] ^= 0x01;
    pc_sends(bad, sizeof bad); poll_n(2);
    CHECK(packets_on_bus == 0 && bridge_stats()->pc_crc_errors == 1, "packet with a wrong CRC is dropped");

    /* 5. Sync Write: sent, no waiting for a reply, nothing back to the PC */
    reset_all();
    uint32_t t0 = now;
    pc_sends(SYNC_WRITE, sizeof SYNC_WRITE); bridge_poll(); bridge_poll();
    CHECK(packets_on_bus == 1 && memcmp(bus_sent, SYNC_WRITE, sizeof SYNC_WRITE) == 0, "Sync Write forwarded");
    CHECK(now == t0 && pc_out_n == 0, "Sync Write does not wait and returns nothing");

    /* 6. two packets in one burst: both run, in order */
    reset_all();
    pc_sends(SYNC_WRITE, sizeof SYNC_WRITE); pc_sends(PING1, sizeof PING1); poll_n(4);
    CHECK(packets_on_bus == 2 && memcmp(bus_sent + sizeof SYNC_WRITE, PING1, sizeof PING1) == 0 && pc_out_n == expect_n,
          "back-to-back packets are queued and run one after another");

    /* 7. broadcast ping: replies of both servos reach the PC */
    reset_all();
    pc_sends(PING_ALL, sizeof PING_ALL); poll_n(2);
    CHECK(pc_out_n == 2 * expect_n && pc_out[4] == 1 && pc_out[expect_n + 4] == 2, "broadcast ping returns ID 1 and ID 2");

    /* 8. servo that is not there: nothing back, counted */
    reset_all();
    uint8_t p3[sizeof PING3]; memcpy(p3, PING3, sizeof p3);
    uint16_t c = dxl_crc16(p3, 8); p3[8] = (uint8_t)c; p3[9] = (uint8_t)(c >> 8);
    pc_sends(p3, sizeof p3); poll_n(2);
    CHECK(packets_on_bus == 1 && pc_out_n == 0 && bridge_stats()->bus_no_reply == 1, "missing servo: no reply, counted");

    /* 9. junk before the header is skipped */
    reset_all();
    const uint8_t junk[] = {0x00, 0x12, 0xFF, 0xFF, 0xFF};
    pc_sends(junk, sizeof junk); pc_sends(PING1, sizeof PING1); poll_n(2);
    CHECK(packets_on_bus == 1 && memcmp(bus_sent, PING1, sizeof PING1) == 0, "junk before FF FF FD 00 is ignored");

    /* 10. your own code can use the same bus (later: sensor control) */
    reset_all();
    CHECK(bridge_submit(PING1, sizeof PING1, app_reply) == 1, "bridge_submit accepts a packet");
    poll_n(1);
    CHECK(app_got_n == expect_n && app_timed_out == 0 && pc_out_n == 0, "reply goes to the submitter, not to the PC");

    printf(fails ? "\n%d FAILED\n" : "\nall passed\n", fails);
    return fails ? 1 : 0;
}
