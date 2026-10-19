/*
 * bridge.c — PC <-> XL330 packet bridge. See bridge.h and firmware/应用通信流程.md.
 *
 * Three parts, in the order data flows:
 *   1. ring buffer   : the PC UART interrupt drops bytes in, the main loop takes them out
 *   2. packet parser : turns PC bytes into complete, CRC-checked packets -> queue
 *   3. bus transaction: one queued packet at a time, DIR = 1 / send / wait TC / DIR = 0,
 *                      then collect the reply and hand it to whoever sent the packet
 * Only part 1 runs in the interrupt. Everything else runs from bridge_poll().
 */
#include "bridge.h"
#include "bridge_port.h"
#include "../dxl/dxl.h"
#include "../dxl/dxl_port.h"

#if (BRIDGE_PC_RX_BUF & (BRIDGE_PC_RX_BUF - 1)) != 0
#error "BRIDGE_PC_RX_BUF must be a power of 2"
#endif

static bridge_stats_t s_stats;

/* ---------------------------------------------------------------- 1. ring buffer */

static volatile uint8_t  s_rx[BRIDGE_PC_RX_BUF];
static volatile uint16_t s_rx_head;          /* written only by the interrupt */
static volatile uint16_t s_rx_tail;          /* written only by the main loop */
static volatile uint32_t s_rx_last_ms;       /* time of the last byte from the PC */

void bridge_pc_rx_isr(uint8_t byte)
{
    uint16_t next = (uint16_t)((s_rx_head + 1) & (BRIDGE_PC_RX_BUF - 1));
    if (next == s_rx_tail) return;           /* full: drop the byte */
    s_rx[s_rx_head] = byte;
    s_rx_head = next;
    s_rx_last_ms = bridge_now_ms();
}

static int rx_pop(uint8_t *b)
{
    if (s_rx_tail == s_rx_head) return 0;
    *b = s_rx[s_rx_tail];
    s_rx_tail = (uint16_t)((s_rx_tail + 1) & (BRIDGE_PC_RX_BUF - 1));
    return 1;
}

/* ---------------------------------------------------------------- queue */

typedef struct {
    uint8_t         data[BRIDGE_MAX_PACKET];
    uint16_t        n;
    bridge_reply_fn on_reply;
} request_t;

static request_t s_q[BRIDGE_QUEUE_LEN];
static uint8_t   s_q_head, s_q_tail, s_q_count;

int bridge_submit(const uint8_t *packet, uint16_t n, bridge_reply_fn on_reply)
{
    if (n < 10 || n > BRIDGE_MAX_PACKET) return 0;
    if (s_q_count == BRIDGE_QUEUE_LEN) { s_stats.queue_full++; return 0; }
    request_t *r = &s_q[s_q_head];
    for (uint16_t k = 0; k < n; k++) r->data[k] = packet[k];
    r->n = n;
    r->on_reply = on_reply;
    s_q_head = (uint8_t)((s_q_head + 1) % BRIDGE_QUEUE_LEN);
    s_q_count++;
    return 1;
}

/* ---------------------------------------------------------------- 2. packet parser */

static const uint8_t HEADER[4] = {0xFF, 0xFF, 0xFD, 0x00};
static uint8_t  s_pkt[BRIDGE_MAX_PACKET];
static uint16_t s_pkt_n;                     /* bytes collected so far */
static uint16_t s_pkt_need;                  /* total length once LEN is known, else 0 */

static void pc_reply(const uint8_t *bytes, uint16_t n, int timed_out)
{
    /* Transparent: forward the servo's bytes as they are. On a timeout send
     * nothing, so tools like DYNAMIXEL Wizard see exactly what a U2D2 would give. */
    if (!timed_out && n) bridge_pc_write(bytes, n);
}

static void parser_reset(void) { s_pkt_n = 0; s_pkt_need = 0; }

static void parser_byte(uint8_t b)
{
    if (s_pkt_n < 4) {                                   /* hunting for FF FF FD 00 */
        if (b == HEADER[s_pkt_n]) { s_pkt[s_pkt_n++] = b; return; }
        if (b == 0xFF) {                                 /* e.g. FF FF FF: keep the last two */
            s_pkt_n = (s_pkt_n >= 2 && s_pkt[s_pkt_n - 1] == 0xFF) ? 2 : 1;
            s_pkt[0] = 0xFF; s_pkt[1] = 0xFF;
            return;
        }
        s_pkt_n = 0;
        return;
    }
    s_pkt[s_pkt_n++] = b;
    if (s_pkt_n == 7) {                                  /* ID, LEN_L, LEN_H are in */
        uint16_t len = (uint16_t)(s_pkt[5] | (s_pkt[6] << 8));
        if (len < 3 || 7u + len > BRIDGE_MAX_PACKET) { parser_reset(); return; }
        s_pkt_need = (uint16_t)(7 + len);
        return;
    }
    if (s_pkt_need && s_pkt_n == s_pkt_need) {           /* whole packet received */
        uint16_t crc = (uint16_t)(s_pkt[s_pkt_n - 2] | (s_pkt[s_pkt_n - 1] << 8));
        if (dxl_crc16(s_pkt, (uint16_t)(s_pkt_n - 2)) == crc) {
            s_stats.pc_packets++;
            bridge_submit(s_pkt, s_pkt_n, pc_reply);
        } else {
            s_stats.pc_crc_errors++;                     /* never put a bad packet on the bus */
        }
        parser_reset();
    }
}

static void parse_pc_bytes(void)
{
    uint8_t b;
    int got = 0;
    while (rx_pop(&b)) { parser_byte(b); got = 1; }
    /* bytes stopped in the middle of a packet: throw the half packet away */
    if (!got && s_pkt_n > 0 &&
        (uint32_t)(bridge_now_ms() - s_rx_last_ms) > BRIDGE_PC_GAP_MS) {
        s_stats.pc_timeouts++;
        parser_reset();
    }
}

/* ---------------------------------------------------------------- 3. bus transaction */

/* 0 = no reply, 1 = reply(s) until the bus goes quiet, 2 = broadcast ping window */
static int reply_kind(const uint8_t *p)
{
    uint8_t id = p[4], inst = p[7];
    if (inst == 0x83 || inst == 0x93) return 0;          /* Sync Write, Bulk Write */
    if (id == DXL_BROADCAST_ID) {
        if (inst == 0x01) return 2;                      /* broadcast Ping: one reply per servo */
        if (inst == 0x82 || inst == 0x92 || inst == 0x8A || inst == 0x9A) return 1; /* Sync/Bulk Read */
        return 0;                                        /* other broadcast instructions */
    }
    return 1;
}

static uint8_t s_reply[BRIDGE_REPLY_BUF];

static void run_transaction(const request_t *r)
{
    dxl_port_flush_rx();                 /* clear old bytes BEFORE sending, never after */
    dxl_port_set_tx(1);
    dxl_port_write(r->data, r->n);
    dxl_port_wait_tx_complete();         /* "transmission complete", not "buffer empty" */
    dxl_port_set_tx(0);                  /* the servo starts replying after ~0.5 ms */

    int kind = reply_kind(r->data);
    uint16_t n = 0;
    uint8_t b;

    if (kind == 0) {
        if (r->on_reply) r->on_reply(s_reply, 0, 0);
        return;
    }
    if (kind == 1) {
        if (dxl_port_read_byte(&b, BRIDGE_FIRST_BYTE_MS)) {
            s_reply[n++] = b;
            while (dxl_port_read_byte(&b, BRIDGE_QUIET_MS))
                if (n < BRIDGE_REPLY_BUF) s_reply[n++] = b;
        }
    } else {                                             /* broadcast ping */
        uint32_t start = bridge_now_ms();
        for (;;) {
            uint32_t used = bridge_now_ms() - start;
            if (used >= BRIDGE_BCAST_PING_MS) break;
            if (dxl_port_read_byte(&b, BRIDGE_BCAST_PING_MS - used)) {
                if (n < BRIDGE_REPLY_BUF) s_reply[n++] = b;
            }
        }
    }
    if (n == 0) s_stats.bus_no_reply++;
    if (r->on_reply) r->on_reply(s_reply, n, n == 0);
}

/* ---------------------------------------------------------------- main loop */

void bridge_init(void)
{
    s_rx_head = s_rx_tail = 0;
    s_q_head = s_q_tail = s_q_count = 0;
    parser_reset();
    s_stats = (bridge_stats_t){0};
    dxl_port_set_tx(0);                  /* bus idle = receive */
}

void bridge_poll(void)
{
    parse_pc_bytes();
    if (s_q_count == 0) return;
    run_transaction(&s_q[s_q_tail]);
    s_q_tail = (uint8_t)((s_q_tail + 1) % BRIDGE_QUEUE_LEN);
    s_q_count--;
}

const bridge_stats_t *bridge_stats(void) { return &s_stats; }
