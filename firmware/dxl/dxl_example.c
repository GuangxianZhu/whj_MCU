/*
 * dxl_example.c — first bring-up sequence for one XL330 (ID 1, 57600 bps).
 *
 * Call dxl_example_run() from main() after clocks, the UART (57600 8N1)
 * and the DIR GPIO (output, LOW) are initialised.
 *
 * What you should see:
 *   1. ping succeeds           -> wiring, DIR and baud rate are right
 *   2. servo LED blinks 3 times -> writes work
 *   3. horn turns between two positions and the position is read back
 */
#include "dxl.h"

#define SERVO_ID 1

/* Provide these two from your project (SysTick delay, debug printf/VCOM). */
extern void delay_ms(uint32_t ms);
extern void log_printf(const char *fmt, ...);

static const char *err_name(int r)
{
    switch (r) {
    case DXL_OK:          return "OK";
    case DXL_ERR_TIMEOUT: return "no reply (check DIR, TX/RX, baud, power)";
    case DXL_ERR_CRC:     return "CRC error (noise or DIR switched too early)";
    case DXL_ERR_ID:      return "reply from another ID";
    case DXL_ERR_STATUS:  return "servo reported an error";
    case DXL_ERR_ARG:     return "packet too large";
    default:              return "bad reply format";
    }
}

void dxl_example_run(void)
{
    uint16_t model = 0;
    int r;

    /* 1. ping until the servo answers */
    while ((r = dxl_ping(SERVO_ID, &model)) != DXL_OK) {
        log_printf("ping ID %d: %s\r\n", SERVO_ID, err_name(r));
        delay_ms(500);
    }
    log_printf("ping OK, model number %u (XL330-M288 = 1200, XL330-M077 = 1190)\r\n", model);

    /* 2. blink the LED */
    for (int k = 0; k < 3; k++) {
        dxl_set_led(SERVO_ID, 1); delay_ms(300);
        dxl_set_led(SERVO_ID, 0); delay_ms(300);
    }

    /* 3. move between two positions (0..4095 = one turn, 2048 = centre) */
    r = dxl_set_torque(SERVO_ID, 1);
    log_printf("torque on: %s\r\n", err_name(r));

    const int32_t targets[2] = {1024, 3072};
    for (int k = 0; ; k ^= 1) {
        dxl_set_goal_position(SERVO_ID, targets[k]);
        delay_ms(1000);
        int32_t pos;
        r = dxl_get_present_position(SERVO_ID, &pos);
        if (r == DXL_OK) log_printf("goal %ld, present %ld\r\n", (long)targets[k], (long)pos);
        else             log_printf("read position: %s\r\n", err_name(r));
    }
}
