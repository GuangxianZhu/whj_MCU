/*
 * dxl_example3.c — three servos on one bus: XC330 (ID 1), XC330 (ID 2), XC430-T240BB (ID 3).
 * 57600 bps, Protocol 2.0. Same driver as dxl_example2.c; only the ID list and the goals differ.
 *
 * Before this: every servo has its own ID (docs/加XC430.md, step 1).
 * Call dxl_example3_run() from main() after clocks, the UART and DIR are set up.
 *
 * What you should see:
 *   1. all three answer a ping; models 1220 (XC330-T288) / 1210 (XC330-T181) / 1080 (XC430-T240BB)
 *   2. each LED blinks in turn: ID 1, ID 2, ID 3      -> each ID is the servo you think
 *   3. all three move at the same time (one Sync Write packet), ID 2 the other way,
 *      then all positions are read back with one Sync Read packet
 *
 * To use more or fewer servos, change N_SERVOS, IDS and the two GOAL_ rows only.
 */
#include "dxl.h"

extern void delay_ms(uint32_t ms);
extern void log_printf(const char *fmt, ...);

#define N_SERVOS 3
static const uint8_t IDS[N_SERVOS]    = {1, 2, 3};
static const int32_t GOAL_A[N_SERVOS] = {3072, 1024, 3072};   /* +90, -90, +90 from the centre */
static const int32_t GOAL_B[N_SERVOS] = {2048, 2048, 2048};   /* back to the centre            */

static const char *model_name(uint16_t m)
{
    switch (m) {
    case 1190: return "XL330-M077";
    case 1200: return "XL330-M288";
    case 1210: return "XC330-T181";
    case 1220: return "XC330-T288";
    case 1080: return "XC430-T240BB";
    default:   return "?";
    }
}

void dxl_example3_run(void)
{
    /* 1. every servo must answer */
    for (;;) {
        int all = 1;
        for (int k = 0; k < N_SERVOS; k++) {
            uint16_t model = 0;
            int r = dxl_ping(IDS[k], &model);
            log_printf("ping ID %d -> %d, model %u %s\r\n", IDS[k], r, model, r == DXL_OK ? model_name(model) : "");
            if (r != DXL_OK) all = 0;
        }
        if (all) break;
        log_printf("not all servos answered; check IDs, the PHB switch and the cables\r\n");
        delay_ms(1000);
    }

    /* 2. blink each LED in turn, so you can see which servo is which ID */
    for (int k = 0; k < N_SERVOS; k++) {
        for (int b = 0; b < 2; b++) {
            dxl_set_led(IDS[k], 1); delay_ms(250);
            dxl_set_led(IDS[k], 0); delay_ms(250);
        }
    }

    /* 3. slow down (Profile Velocity, address 112 = 50, about 11 rpm), torque on, then move together */
    const uint8_t slow[4] = {50, 0, 0, 0};
    for (int k = 0; k < N_SERVOS; k++) dxl_write(IDS[k], 112, slow, 4);
    for (int k = 0; k < N_SERVOS; k++) dxl_set_torque(IDS[k], 1);

    for (int step = 0; ; step ^= 1) {
        const int32_t *goal = step ? GOAL_B : GOAL_A;
        dxl_sync_write_goal_position(IDS, N_SERVOS, goal);    /* one packet, all move, no reply */
        delay_ms(2000);

        int32_t pos[N_SERVOS] = {0};
        int res[N_SERVOS];
        dxl_sync_read_present_position(IDS, N_SERVOS, pos, res);
        for (int k = 0; k < N_SERVOS; k++) {
            if (res[k] == DXL_OK) log_printf("ID %d goal %ld present %ld\r\n", IDS[k], (long)goal[k], (long)pos[k]);
            else                  log_printf("ID %d no position (%d)\r\n", IDS[k], res[k]);
        }
    }
}
