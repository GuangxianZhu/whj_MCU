/*
 * bridge.h — PC <-> XL330 packet bridge (design: firmware/应用通信流程.md).
 *
 * The PC sends complete DYNAMIXEL Protocol 2.0 packets over its serial port.
 * The bridge collects one whole packet, checks its CRC, sends it on the servo
 * bus with the DIR sequence, collects the servo reply and sends it back to the
 * PC unchanged. Later, your own code (sensor control) can put packets into the
 * same queue with bridge_submit().
 *
 * How to use it:
 *   1. Implement the servo side: the 5 functions in ../dxl/dxl_port.h.
 *   2. Implement the PC side and the clock: the 2 functions in bridge_port.h.
 *   3. In the PC UART receive interrupt, call bridge_pc_rx_isr(byte).
 *   4. main(): init clocks, both UARTs, DIR (output, 0), SysTick, then
 *          bridge_init();
 *          for (;;) bridge_poll();
 */
#ifndef BRIDGE_H
#define BRIDGE_H

#include <stdint.h>

/* ---- settings (change here) ---- */
#define BRIDGE_MAX_PACKET        320   /* biggest packet accepted from a source; 17-servo
                                          Sync Write of a 12-byte block is 235 bytes      */
#define BRIDGE_QUEUE_LEN           4   /* packets waiting for the bus                 */
#define BRIDGE_PC_RX_BUF        1024   /* ring buffer for bytes from the PC (power of 2) */
#define BRIDGE_REPLY_BUF        1024   /* all reply bytes of one transaction (17-servo
                                          Sync Read of 12 bytes is 391 bytes)             */
#define BRIDGE_PC_GAP_MS          20   /* max gap between bytes inside one PC packet   */
#define BRIDGE_FIRST_BYTE_MS      10   /* wait this long for a servo to start replying */
#define BRIDGE_QUIET_MS            3   /* reply is over after this much silence        */
#define BRIDGE_BCAST_PING_MS     800   /* broadcast ping: collect replies this long    */

/* Who gets the reply. timed_out = 1 when the servo said nothing. */
typedef void (*bridge_reply_fn)(const uint8_t *bytes, uint16_t n, int timed_out);

void bridge_init(void);

/* Call from the main loop as often as possible. Does at most one bus
 * transaction per call. */
void bridge_poll(void);

/* Call from the PC UART receive interrupt, once per received byte. */
void bridge_pc_rx_isr(uint8_t byte);

/* Put a complete packet (e.g. one built with dxl_build_packet) in the queue.
 * on_reply may be NULL. Returns 1 if queued, 0 if the queue is full. */
int bridge_submit(const uint8_t *packet, uint16_t n, bridge_reply_fn on_reply);

/* Counters, handy to print while debugging (never sent to the PC port). */
typedef struct {
    uint32_t pc_packets;      /* complete, CRC-correct packets from the PC */
    uint32_t pc_crc_errors;   /* dropped: CRC wrong                        */
    uint32_t pc_timeouts;     /* dropped: bytes stopped in the middle      */
    uint32_t queue_full;      /* dropped: queue was full                   */
    uint32_t bus_no_reply;    /* a reply was expected but none came        */
} bridge_stats_t;

const bridge_stats_t *bridge_stats(void);

#endif /* BRIDGE_H */
