"""Smallest program that moves fingers and the wrist with orca_core.

Copy this file to start your own control program. It uses only orca_core's
public API, so it runs the same through the KM1M7C bridge or a U2D2.

    python finger_wrist_example.py CONFIG.yaml      # real hand (after calibration)
    python finger_wrist_example.py --mock           # simulated hand, no hardware

Joint angles are in degrees, joint names as in config.yaml (wrist, index_mcp,
index_pip, thumb_cmc ...). Every target is clamped to the joint's ROM
(joint_roms in config.yaml) before it is sent, so a typo cannot over-drive a
tendon.
"""
import argparse
import time

from orca_core import load_hand
from orca_core.utils.cli import connect_hand, shutdown_hand

STEPS = 50        # interpolation steps per move
STEP_S = 0.02     # seconds between steps  -> 50 x 0.02 = 1 s per move


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config", nargs="?", default=None)
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    if not a.mock and not a.config:
        ap.error("give CONFIG.yaml, or --mock")

    hand = load_hand(config_path=a.config, mock=a.mock)
    try:
        connect_hand(hand)          # asks the hardware version (2 / 21) the first time
        hand.init_joints()          # calibrates only if calibration.yaml is missing, then neutral

        # 1) one finger, in degrees: curl the index finger
        print("index curl")
        hand.set_joint_positions({"index_mcp": 80, "index_pip": 90},
                                 num_steps=STEPS, step_size=STEP_S)
        time.sleep(0.5)

        # 2) the wrist alone: tilt one way, then the other (ROM -65 .. 35 deg on v2)
        for angle in (-40, 20, -20):
            print(f"wrist {angle} deg")
            hand.set_joint_positions({"wrist": angle}, num_steps=STEPS, step_size=STEP_S)
            time.sleep(0.3)

        # 3) whole-hand pose as fractions of each joint's ROM (0 = one end, 1 = other end)
        #    -> survives re-calibration and re-tensioning unchanged
        print("power grasp")
        grasp = hand.pose_from_fractions({
            "index_mcp": 0.85, "index_pip": 0.9,
            "middle_mcp": 0.85, "middle_pip": 0.9,
            "ring_mcp": 0.85, "ring_pip": 0.9,
            "pinky_mcp": 0.85, "pinky_pip": 0.9,
            "thumb_mcp": 0.2, "thumb_dip": 0.85,
        })
        hand.set_joint_positions(grasp, num_steps=STEPS, step_size=STEP_S)
        time.sleep(0.5)

        # 4) read back where every joint is now
        now = hand.get_joint_position().as_dict()
        print("index_mcp=%.1f  wrist=%.1f" % (now["index_mcp"], now["wrist"]))

        print("back to neutral")
        hand.set_neutral_position()
        return 0
    finally:
        shutdown_hand(hand)         # stops tasks, torque off, closes the port


if __name__ == "__main__":
    raise SystemExit(main())
