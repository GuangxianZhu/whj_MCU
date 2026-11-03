"""Compare each joint's measured motor travel across calibration rounds.

Every calibrate.py run writes ``motor_travel_measured`` (degrees the motor
turned between the joint's two hardstops) into calibration.yaml, also on
v2.0 hands where orca_core itself does not check it. This script uses it to
see whether pre-tension + calibration rounds are converging:

  * prev / delta  - change since the last saved round (should shrink)
  * v2.1 ref      - orca_core's v2.1 baseline from config.yaml, reference only
                    (v2.0 geometry may differ)
  * vs siblings   - this joint's (measured / ref) against the median of the
                    same joint type on index/middle/ring/pinky. Far below the
                    siblings usually means too tight or binding; orca_core uses
                    the same 25 % margin on v2.1.

Read only, no hardware. Usage:
    python compare_travel.py HAND_DIR [--save]
HAND_DIR holds config.yaml and calibration.yaml (e.g. tools/orca/my_hand).
--save stores this round in HAND_DIR/travel_history/ for the next comparison.
"""
import argparse
import datetime
import glob
import os
import statistics
import sys

import yaml

FINGERS = ("index", "middle", "ring", "pinky")
KINDS = ("abd", "mcp", "pip")
MARGIN = 0.25  # orca_core calibration_travel_margin default


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("hand_dir")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()

    calib_path = os.path.join(a.hand_dir, "calibration.yaml")
    if not os.path.isfile(calib_path):
        print(f"no {calib_path} yet - run calibration first")
        return 1
    travel = {k: float(v) for k, v in (load(calib_path).get("motor_travel_measured") or {}).items()}
    if not travel:
        print("calibration.yaml has no motor_travel_measured")
        return 1
    cfg_path = os.path.join(a.hand_dir, "config.yaml")
    ref = {}
    if os.path.isfile(cfg_path):
        ref = {k: float(v) for k, v in (load(cfg_path).get("joint_motor_travel_v21") or {}).items()}

    hist_dir = os.path.join(a.hand_dir, "travel_history")
    previous = sorted(glob.glob(os.path.join(hist_dir, "*.yaml")))
    prev = {k: float(v) for k, v in load(previous[-1]).items()} if previous else {}
    if prev:
        print(f"previous round: {os.path.basename(previous[-1])}")

    ratio = {j: travel[j] / ref[j] for j in travel if ref.get(j)}
    sib_median = {}
    for kind in KINDS:
        vals = [ratio[f"{f}_{kind}"] for f in FINGERS if f"{f}_{kind}" in ratio]
        if len(vals) >= 3:
            sib_median[kind] = statistics.median(vals)

    print(f"\n{'joint':12s} {'now':>7s} {'prev':>7s} {'delta':>7s} {'v2.1ref':>8s} {'vs sib':>7s}  note")
    flagged = 0
    for joint in sorted(travel):
        now = travel[joint]
        p = prev.get(joint)
        delta = f"{now - p:+7.1f}" if p is not None else "      -"
        pstr = f"{p:7.1f}" if p is not None else "      -"
        rstr = f"{ref[joint]:8.1f}" if joint in ref else "       -"
        note, sib = "", "      -"
        finger, _, kind = joint.partition("_")
        if finger in FINGERS and kind in sib_median and joint in ratio:
            rel = ratio[joint] / sib_median[kind]
            sib = f"{rel * 100:6.0f}%"
            if rel < 1 - MARGIN:
                note = "much shorter than siblings: too tight / binding?"
            elif rel > 1 + MARGIN:
                note = "much longer than siblings: slack / slipped?"
        if note:
            flagged += 1
        print(f"{joint:12s} {now:7.1f} {pstr} {delta} {rstr} {sib}  {note}")
    print(f"\nflagged joints: {flagged}")

    if a.save:
        os.makedirs(hist_dir, exist_ok=True)
        name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".yaml"
        with open(os.path.join(hist_dir, name), "w", encoding="utf-8") as f:
            yaml.safe_dump({k: round(v, 2) for k, v in travel.items()}, f, sort_keys=True)
        print(f"saved this round as travel_history/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
