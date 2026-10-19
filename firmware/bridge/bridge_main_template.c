/*
 * bridge_main_template.c — copy into your Keil project and fill in the TODOs
 * with KM1M7C SDK calls. Everything else (bridge.c, dxl.c) stays unchanged.
 *
 * Two UARTs:
 *   PC UART    : USB virtual COM to the PC
 *   SERVO UART : TX -> TXB A3, RX <- TXB A2 (see docs/breadboard)
 *   DIR GPIO   : -> TXB A1   (1 = send, 0 = receive)
 * Both UARTs 57600 bps, 8 data bits, no parity, 1 stop bit.
 *
 * Files to add to the project:
 *   firmware/dxl/dxl.c, firmware/bridge/bridge.c, this file
 * Include paths: firmware/dxl, firmware/bridge
 */
#include <stdint.h>
#include "bridge.h"
#include "bridge_port.h"
#include "dxl_port.h"

/* ================================================================ clock */

static volatile uint32_t s_ms;

void SysTick_Handler(void) { s_ms++; }           /* TODO: SysTick every 1 ms */

uint32_t bridge_now_ms(void) { return s_ms; }

/* ================================================================ PC side */

void bridge_pc_write(const uint8_t *data, uint16_t n)
{
    for (uint16_t k = 0; k < n; k++) {
        /* TODO: wait until the PC UART can take a byte, then write data[k] */
        (void)data[k];
    }
}

void PC_UART_IRQHandler(void)                     /* TODO: use the real handler name */
{
    /* TODO: while the PC UART has a received byte:
     *           uint8_t b = <read PC UART data register>;
     *           bridge_pc_rx_isr(b);
     *       and clear the interrupt flag if the SDK needs it. */
}

/* ================================================================ servo side (dxl_port.h) */

#define SERVO_RX_BUF 256                          /* power of 2 */
static volatile uint8_t  s_srx[SERVO_RX_BUF];
static volatile uint16_t s_srx_head, s_srx_tail;

void SERVO_UART_IRQHandler(void)                  /* TODO: use the real handler name */
{
    /* TODO: while the servo UART has a received byte:
     *           uint8_t b = <read servo UART data register>;
     *           uint16_t next = (s_srx_head + 1) & (SERVO_RX_BUF - 1);
     *           if (next != s_srx_tail) { s_srx[s_srx_head] = b; s_srx_head = next; }
     *       and clear the interrupt flag if the SDK needs it. */
}

void dxl_port_set_tx(int tx)
{
    /* TODO: write the DIR GPIO: tx ? 1 : 0 */
    (void)tx;
}

void dxl_port_write(const uint8_t *data, uint16_t n)
{
    for (uint16_t k = 0; k < n; k++) {
        /* TODO: wait for "transmit buffer empty", then write data[k] to the servo UART */
        (void)data[k];
    }
}

void dxl_port_wait_tx_complete(void)
{
    /* TODO: wait for the servo UART "transmission complete" (TC) flag.
     *       NOT "transmit buffer empty": that is one byte too early. */
}

void dxl_port_flush_rx(void)
{
    s_srx_tail = s_srx_head;
}

int dxl_port_read_byte(uint8_t *b, uint32_t timeout_ms)
{
    uint32_t start = bridge_now_ms();
    while (s_srx_tail == s_srx_head) {
        if ((uint32_t)(bridge_now_ms() - start) >= timeout_ms) return 0;
    }
    *b = s_srx[s_srx_tail];
    s_srx_tail = (uint16_t)((s_srx_tail + 1) & (SERVO_RX_BUF - 1));
    return 1;
}

/* ================================================================ main */

int main(void)
{
    /* TODO: system clock
     * TODO: SysTick 1 ms
     * TODO: DIR GPIO as push-pull output, write 0
     * TODO: PC UART 57600 8N1, receive interrupt on
     * TODO: servo UART 57600 8N1, receive interrupt on
     */
    bridge_init();
    for (;;) {
        bridge_poll();
        /* Later: if (control period elapsed) build a Sync Write packet with
         * dxl_build_packet() and give it to bridge_submit(pkt, n, my_reply_fn). */
    }
}
