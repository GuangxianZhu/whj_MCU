/*
 * dxl.h — minimal DYNAMIXEL Protocol 2.0 driver for one half-duplex TTL bus.
 *
 * Covers what the XL330 demo needs: ping, read, write, a few helpers, and
 * Sync Write / Sync Read for several servos on the same bus.
 * Hardware access goes through dxl_port.h.
 */
#ifndef DXL_H
#define DXL_H

#include <stdint.h>

#define DXL_BROADCAST_ID   0xFE
#define DXL_BUF_SIZE       128    /* largest packet handled, in bytes   */
#define DXL_MAX_SERVOS     16     /* most servos in one Sync Read       */
#define DXL_BYTE_TIMEOUT_MS 20    /* max gap while waiting for a reply  */

/* XL330 control table (RAM area unless noted) */
#define XL330_ADDR_ID               7   /* EEPROM, 1 byte  */
#define XL330_ADDR_BAUD_RATE        8   /* EEPROM, 1 byte  */
#define XL330_ADDR_RETURN_DELAY     9   /* EEPROM, 1 byte, unit 2 us */
#define XL330_ADDR_OPERATING_MODE  11   /* EEPROM, 1 byte  */
#define XL330_ADDR_TORQUE_ENABLE   64   /* 1 byte          */
#define XL330_ADDR_LED             65   /* 1 byte          */
#define XL330_ADDR_HW_ERROR        70   /* 1 byte, read only */
#define XL330_ADDR_PROFILE_ACCEL  108   /* 4 bytes         */
#define XL330_ADDR_PROFILE_VEL    112   /* 4 bytes         */
#define XL330_ADDR_GOAL_POSITION  116   /* 4 bytes         */
#define XL330_ADDR_PRESENT_POSITION 132 /* 4 bytes         */

/* Instructions */
#define DXL_INST_PING   0x01
#define DXL_INST_READ   0x02
#define DXL_INST_WRITE  0x03
#define DXL_INST_REBOOT 0x08
#define DXL_INST_SYNC_READ  0x82
#define DXL_INST_SYNC_WRITE 0x83

/* Return codes */
#define DXL_OK            0
#define DXL_ERR_TIMEOUT  -1   /* no (complete) reply                      */
#define DXL_ERR_CRC      -2   /* reply arrived but CRC does not match     */
#define DXL_ERR_ID       -3   /* reply came from a different ID           */
#define DXL_ERR_STATUS   -4   /* servo reported an error, see *servo_err  */
#define DXL_ERR_ARG      -5   /* packet too large for DXL_BUF_SIZE        */
#define DXL_ERR_FORMAT   -6   /* reply is not a status packet             */

uint16_t dxl_crc16(const uint8_t *data, uint16_t n);

/* Build a complete instruction packet (with byte stuffing and CRC) into out.
 * Returns its length, or 0 if it does not fit in out_max. */
uint16_t dxl_build_packet(uint8_t id, uint8_t inst,
                          const uint8_t *params, uint16_t n,
                          uint8_t *out, uint16_t out_max);

/* Send one instruction and, unless id is broadcast, wait for the status reply.
 * reply_params/reply_n receive the destuffed parameters (may be NULL).
 * servo_err receives the status packet's error byte (may be NULL). */
int dxl_txrx(uint8_t id, uint8_t inst, const uint8_t *params, uint16_t n,
             uint8_t *reply_params, uint16_t reply_max, uint16_t *reply_n,
             uint8_t *servo_err);

int dxl_ping(uint8_t id, uint16_t *model_number);
int dxl_write(uint8_t id, uint16_t addr, const uint8_t *data, uint16_t n);
int dxl_read(uint8_t id, uint16_t addr, uint16_t n, uint8_t *out);

int dxl_set_led(uint8_t id, uint8_t on);
int dxl_set_torque(uint8_t id, uint8_t on);
int dxl_set_goal_position(uint8_t id, int32_t position);
int dxl_get_present_position(uint8_t id, int32_t *position);

/* ---- several servos on one bus ----
 * Every servo needs its own ID first (dxl_set_id, one servo connected at a time). */

/* Same address and length to several servos in one packet; they all act at once.
 * data holds n_ids * len bytes: servo k's bytes start at data[k * len]. No reply. */
int dxl_sync_write(uint16_t addr, uint16_t len, const uint8_t *ids, uint8_t n_ids,
                   const uint8_t *data);

/* Read the same address and length from several servos. out gets n_ids * len bytes.
 * results[k] (may be NULL) is the per-servo code: DXL_OK, DXL_ERR_TIMEOUT if that
 * servo did not answer, ... Returns DXL_OK only if every servo answered. */
int dxl_sync_read(uint16_t addr, uint16_t len, const uint8_t *ids, uint8_t n_ids,
                  uint8_t *out, int *results);

int dxl_sync_write_goal_position(const uint8_t *ids, uint8_t n_ids, const int32_t *positions);
int dxl_sync_read_present_position(const uint8_t *ids, uint8_t n_ids, int32_t *positions,
                                   int *results);

/* Restart one servo (clears a hardware error). */
int dxl_reboot(uint8_t id);

/* Change a servo's ID (saved in EEPROM). Connect ONLY that servo while doing it.
 * Turns torque off first, writes the new ID, then pings the new ID. */
int dxl_set_id(uint8_t old_id, uint8_t new_id);

#endif /* DXL_H */
