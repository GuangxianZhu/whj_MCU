/*
 * dxl_example2.c — two XL330 on one bus (IDs 1 and 2, 57600 bps).
 *
 * Before this: give the second servo ID 2 (docs/两个舵机.md, step 2).
 * Call dxl_example2_run() from main() after clocks, the UART and DIR are set up.
 *
 * What you should see:
 *   1. both servos answer a ping, model numbers printed
 *   2. LED of ID 1 blinks, then LED of ID 2   -> each ID is the servo you think
 *   3. both horns move at the same time, in opposite directions (Sync Write),
 *      and both positions are read back with one packet (Sync Read)
 */
#include "dxl.h"

extern void delay_ms(uint32_t ms);
extern void log_printf(const char *fmt, ...);

#define N_SERVOS 2
static const uint8_t IDS[N_SERVOS] = {1, 2};

void dxl_example2_run(void)
{
    /* 1. every servo must answer */
    for (;;) {
        int all = 1;
        for (int k = 0; k < N_SERVOS; k++) {
            uint16_t model = 0;
            int r = dxl_ping(IDS[k], &model);
            log_printf("ping ID %d -> %d, model %u\r\n", IDS[k], r, model);
            if (r != DXL_OK) all = 0;
        }
        if (all) break;
        log_printf("not all servos answered; check IDs, power and the cable between servos\r\n");
        delay_ms(1000);
    }

    /* 2. blink each LED in turn, so you can see which servo is which ID */
    for (int k = 0; k < N_SERVOS; k++) {
        for (int b = 0; b < 2; b++) {
            dxl_set_led(IDS[k], 1); delay_ms(250);
            dxl_set_led(IDS[k], 0); delay_ms(250);
        }
    }

    /* 3. torque on, then move both together */
    for (int k = 0; k < N_SERVOS; k++) dxl_set_torque(IDS[k], 1);

    for (int step = 0; ; step ^= 1) {
        int32_t goal[N_SERVOS] = { step ? 1024 : 3072, step ? 3072 : 1024 };
        dxl_sync_write_goal_position(IDS, N_SERVOS, goal);    /* one packet, both move */
        delay_ms(1000);

        int32_t pos[N_SERVOS] = {0, 0};
        int res[N_SERVOS];
        dxl_sync_read_present_position(IDS, N_SERVOS, pos, res);
        for (int k = 0; k < N_SERVOS; k++) {
            if (res[k] == DXL_OK) log_printf("ID %d goal %ld present %ld\r\n", IDS[k], (long)goal[k], (long)pos[k]);
            else                  log_printf("ID %d no position (%d)\r\n", IDS[k], res[k]);
        }
    }
}
