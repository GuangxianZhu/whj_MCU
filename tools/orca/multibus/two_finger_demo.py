#!/usr/bin/env python3
"""Open and close two fingers together, slowly (grasp-like demo).

Run from the orca_core folder, the same way as the official scripts:

    uv run python <whj_MCU>\\tools\\orca\\multibus\\two_finger_demo.py %CFG%
    uv run python <whj_MCU>\\tools\\orca\\multibus\\two_finger_demo.py %CFG% --close-deg 40 --cycles 5

What it does: connect -> torque on -> neutral pose -> N times (close, open)
-> neutral pose -> torque off and disconnect. Ctrl+C stops it at any time and
still switches the torque off.

It refuses to start without a calibration (it never calibrates by itself),
and it only moves the MCP and PIP joints of the fingers named in --fingers.
Angles are clamped to the joint ranges in config.yaml by orca_core.

All output is plain ASCII so any Windows console can print it.
"""
import argparse
import sys
import time

from orca_core.utils.cli import (
    add_hand_arguments,
    connect_hand,
    create_hand_from_args,
    shutdown_hand,
)

STEP_S = 0.02


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_hand_arguments(parser)
    parser.add_argument("--fingers", nargs="+", default=["index", "middle"],
                        help="fingers to move (default: index middle)")
    parser.add_argument("--close-deg", type=float, default=50.0,
                        help="how far MCP and PIP bend when closed, in degrees (default 50)")
    parser.add_argument("--cycles", type=int, default=3, help="close/open repetitions (default 3)")
    parser.add_argument("--seconds", type=float, default=1.5,
                        help="time for one close or one open (default 1.5)")
    args = parser.parse_args()

    hand = create_hand_from_args(args)
    try:
        connect_hand(hand)
        if not hand.calibrated:
            print("STOP: this hand has no complete calibration (calibration.yaml beside")
            print("      config.yaml). Run scripts\\calibrate.py first; this demo never calibrates.")
            return 1

        absent = set(hand.absent_joints)
        joints = [f"{finger}_{part}" for finger in args.fingers for part in ("mcp", "pip")]
        unknown = [j for j in joints if j not in hand.config.joint_ids]
        if unknown:
            print(f"STOP: no such joints in config.yaml: {unknown}")
            return 1
        missing = [j for j in joints if j in absent]
        if missing:
            print(f"STOP: these joints did not answer at connect: {missing}")
            print("      Check the board and wiring of that finger (run check_buses.py).")
            return 1

        neutral = hand.config.neutral_position
        opened = {j: float(neutral[j]) for j in joints}
        closed = {j: float(args.close_deg) for j in joints}
        steps = max(int(args.seconds / STEP_S), 1)

        print(f"Moving joints: {joints}")
        print(f"closed = {args.close_deg:g} deg, {args.cycles} cycles, {args.seconds:g} s per move")
        hand.init_joints()
        hand.set_neutral_position()
        time.sleep(0.5)
        for cycle in range(1, args.cycles + 1):
            print(f"cycle {cycle}/{args.cycles}: close")
            hand.set_joint_positions(closed, num_steps=steps, step_size=STEP_S)
            time.sleep(0.5)
            print(f"cycle {cycle}/{args.cycles}: open")
            hand.set_joint_positions(opened, num_steps=steps, step_size=STEP_S)
            time.sleep(0.5)
            hand.get_joint_position()
            if not hand.last_read_ok:
                print("WARNING: the motors did not all answer a read (a board dropped out?)")
        hand.set_neutral_position()
        print("Done.")
        return 0
    except KeyboardInterrupt:
        print("\nStopped by Ctrl+C.")
        return 0
    finally:
        shutdown_hand(hand)


if __name__ == "__main__":
    sys.exit(main())
