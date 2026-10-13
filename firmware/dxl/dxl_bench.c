/*
 * dxl_bench.c — test programs for the staged check (docs/breadboard/分级检查.md).
 *
 * Pick one mode in main() and call dxl_bench_run(mode). It never returns.
 *
 *   'A'  DIR = 0, UART idle.             Stage 1 items 1.4, 1.6; stage 4 item 4.6
 *   'B'  DIR = 1, UART idle.             Stage 1 item 1.5
 *   'L'  loopback: every 0.5 s send a ping with the normal DIR sequence and
 *        print every byte that comes back.  Items 1.7, 1.8, 2.16, 3.28, 3.29
 *   'S'  servo: LED on/off + ping ID 1, print the result.  Items 4.7, 4.8, 4.9
 *
 * Uses only the hooks in dxl_port.h plus delay_ms() and log_printf().
 * For 'L' the UART must keep receiving while it is sending (receive in an
 * interrupt into a buffer, see dxl_port.h), because in the loopback tests the
 * bytes come back while they are still being sent.
 */
#include "dxl.h"
#include "dxl_port.h"

extern void delay_ms(uint32_t ms);
extern void log_printf(const char *fmt, ...);

static const uint8_t PING[10] = {0xFF, 0xFF, 0xFD, 0x00, 0x01, 0x03, 0x00, 0x01, 0x19, 0x4E};
static const uint8_t PING_ALL[10] = {0xFF, 0xFF, 0xFD, 0x00, 0xFE, 0x03, 0x00, 0x01, 0x31, 0x42};

static void dump(const uint8_t *b, int n)
{
    for (int i = 0; i < n; i++) log_printf("%02X ", b[i]);
    log_printf("\r\n");
}

/* Send one packet with the normal DIR sequence, then collect what comes back. */
static int send_and_collect(const uint8_t *pkt, int n, uint8_t *rx, int max)
{
    int got = 0;
    dxl_port_flush_rx();          /* clear old bytes BEFORE sending, never after */
    dxl_port_set_tx(1);
    dxl_port_write(pkt, (uint16_t)n);
    dxl_port_wait_tx_complete();  /* "transmission complete", not "buffer empty" */
    dxl_port_set_tx(0);
    while (got < max && dxl_port_read_byte(&rx[got], 20)) got++;
    return got;
}

static void loopback(void)
{
    uint8_t rx[32];
    for (;;) {
        int got = send_and_collect(PING, 10, rx, sizeof rx);
        log_printf("[L] sent 10, got %d: ", got);
        dump(rx, got);
        if (got == 0) {
            log_printf("    nothing came back\r\n");
        } else if (got == 10) {
            int same = 1;
            for (int i = 0; i < 10; i++) if (rx[i] != PING[i]) same = 0;
            log_printf(same ? "    OK: identical\r\n" : "    10 bytes but different: baud rate or noise\r\n");
        } else if (got < 10) {
            log_printf("    short: last bytes cut off, wait for TX COMPLETE before DIR = 0\r\n");
        } else {
            log_printf("    more than sent: something else is on the line\r\n");
        }
        delay_ms(500);
    }
}

static void servo(void)
{
    uint8_t rx[32];
    for (int k = 1; ; k ^= 1) {
        int r = dxl_set_led(1, (uint8_t)k);
        log_printf("[S] LED %s -> %d (0 = OK, -1 = no reply; LED should %s)\r\n", k ? "on" : "off", r, k ? "light" : "go dark");

        uint16_t model = 0;
        r = dxl_ping(1, &model);
        log_printf("[S] ping ID 1 -> %d (0 = OK, -1 = no reply), model %u (1200 = XL330-M288)\r\n", r, model);

        int got = send_and_collect(PING_ALL, 10, rx, sizeof rx);
        log_printf("[S] broadcast ping, got %d: ", got);
        dump(rx, got);
        delay_ms(1000);
    }
}

void dxl_bench_run(char mode)
{
    dxl_port_set_tx(0);
    switch (mode) {
    case 'A': log_printf("[A] DIR = 0, UART idle\r\n"); for (;;) delay_ms(1000);
    case 'B': dxl_port_set_tx(1); log_printf("[B] DIR = 1, UART idle\r\n"); for (;;) delay_ms(1000);
    case 'L': loopback(); break;   /* never returns */
    case 'S': servo();    break;   /* never returns */
    default:  log_printf("unknown mode %c\r\n", mode); for (;;) delay_ms(1000);
    }
}
