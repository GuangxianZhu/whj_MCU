/*
 * bridge_port.h — the two hardware hooks the bridge needs besides dxl_port.h.
 *
 * Implement them with the KM1M7C SDK.
 */
#ifndef BRIDGE_PORT_H
#define BRIDGE_PORT_H

#include <stdint.h>

/* Milliseconds since power-on (a SysTick counter incremented every 1 ms). */
uint32_t bridge_now_ms(void);

/* Send bytes to the PC serial port (blocking is fine). */
void bridge_pc_write(const uint8_t *data, uint16_t n);

#endif /* BRIDGE_PORT_H */
