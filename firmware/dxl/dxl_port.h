/*
 * dxl_port.h — hardware hooks for the DYNAMIXEL driver.
 *
 * Implement these five functions with the KM1M7C SDK (UART + one GPIO).
 * Everything else in dxl.c is plain C and needs no changes.
 *
 * Wiring this driver assumes (see docs/breadboard):
 *   MCU TX  -> TXB0104 B2 -> A2 -> 74LVC2G241 2A  (send path)
 *   MCU RX  <- TXB0104 B1 <- A1 <- 74LVC2G241 1Y  (receive path)
 *   MCU GPIO-> TXB0104 B3 -> A3 -> 2OE and 1OE     (DIR: 1 = send, 0 = receive)
 *   UART: 57600 bps, 8 data bits, no parity, 1 stop bit (XL330 factory default)
 */
#ifndef DXL_PORT_H
#define DXL_PORT_H

#include <stdint.h>

/* Drive the DIR GPIO. tx = 1: send (2Y on, 1Y off). tx = 0: receive.
 * Initialise the pin as an output driven LOW before anything else. */
void dxl_port_set_tx(int tx);

/* Push n bytes into the UART. May return as soon as the last byte is queued. */
void dxl_port_write(const uint8_t *data, uint16_t n);

/* Block until the last stop bit has left the UART shift register.
 * Use the "transmission complete" flag, NOT "transmit buffer empty":
 * the buffer is empty one byte too early, and switching DIR then cuts
 * off the final byte of the packet. */
void dxl_port_wait_tx_complete(void);

/* Discard any bytes already sitting in the UART receive buffer / FIFO. */
void dxl_port_flush_rx(void);

/* Wait up to timeout_ms for one received byte.
 * Return 1 and store it in *b, or return 0 on timeout. */
int dxl_port_read_byte(uint8_t *b, uint32_t timeout_ms);

#endif /* DXL_PORT_H */
