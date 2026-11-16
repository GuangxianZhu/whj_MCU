#!/usr/bin/env python3
"""Keep one board transmitting so the TX path can be checked with a multimeter.

Run it with NO servo connected to that board:

    uv run python <whj_MCU>\\tools\\orca\\multibus\\tx_test.py COM5

For 20 seconds it sends a steady stream of zero bytes through the board.
While it runs, measure DC volts against GND:

    DATA (servo socket pin 3)   idle: about 5 V     while sending: clearly lower
    241 pin 7 (direction)       idle: about 0 V     while sending: clearly higher

A zero byte keeps the line low 90 percent of the time, so a multimeter, which
shows the average, drops well below 5 V when the transmit path works. Nothing
is sent that a servo would understand; it is only a level test.

All output is plain ASCII so any Windows console can print it.
"""
import argparse
import sys
import time

import serial


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("port", help="the board's COM port, e.g. COM5")
    ap.add_argument("--baud", type=int, default=1000000, help="baud rate (default 1000000)")
    ap.add_argument("--seconds", type=float, default=20.0, help="how long to send (default 20)")
    a = ap.parse_args()

    try:
        port = serial.Serial(a.port, a.baud, timeout=0, write_timeout=1)
    except serial.SerialException as exc:
        print(f"Could not open {a.port}: {exc}".encode("ascii", "replace").decode())
        print("Is another program (serial terminal, the hand software) using it?")
        return 1

    block = bytes(256)
    sent = 0
    stalled = 0
    print(f"Sending on {a.port} at {a.baud} baud for {a.seconds:g} s.")
    print("Measure now:  DATA should read clearly below 5 V (typically 0.5 to 3.5 V),")
    print("              241 pin 7 should read clearly above 0 V.")
    end = time.time() + a.seconds
    last = 0
    try:
        while time.time() < end:
            try:
                sent += port.write(block)
            except serial.SerialTimeoutException:
                stalled += 1
            left = int(end - time.time())
            if left != last and left % 5 == 0:
                last = left
                print(f"  ... {left} s left")
    except KeyboardInterrupt:
        print("Stopped by Ctrl+C.")
    finally:
        port.close()

    print(f"Done. {sent} bytes handed to the port.")
    if sent == 0:
        print("PROBLEM: the port accepted no data at all. Check the USB cable and the COM number.")
        return 1
    print("Measure again: DATA should be back at about 5 V, 241 pin 7 at about 0 V.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
