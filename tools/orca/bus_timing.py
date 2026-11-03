"""Read-only bus timing test for the ORCA hand: U2D2 vs KM1M7C bridge.

Connects with the given config, then repeats one full read of every motor
(position + velocity + current, the read the control loop uses) and reports
how long it takes and how many reads came back stale. Also prints each
motor's Return Delay Time, which the KM1M7C bridge's TXEN timing must beat.

Nothing moves: torque is never enabled (disconnect turns it off anyway).

Usage (inside the orca_core uv environment):
    python bus_timing.py CONFIG.yaml [-n 200]
"""
import argparse
import statistics
import sys
import time

from orca_core import load_hand


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config", help="hand config.yaml")
    ap.add_argument("-n", type=int, default=200, help="number of full reads (default 200)")
    a = ap.parse_args()

    hand = load_hand(config_path=a.config)
    ok, msg = hand.connect()
    print(f"connect: {ok} {msg}")
    if not ok:
        return 1
    try:
        cfg = hand.config
        client = hand.motor_client
        print(f"port={cfg.port}  motor_type={cfg.motor_type}  baudrate={cfg.baudrate}")
        absent = hand.absent_motor_ids
        print(f"motors configured={len(cfg.motor_ids)}  absent={absent or 'none'}")

        print("\nReturn Delay Time per motor (us; factory 500, chain setup 20):")
        delays = {}
        for mid in cfg.motor_ids:
            if mid in absent:
                continue
            delays[mid] = client.read_config_register(mid, "return_delay_time")
        print("  " + "  ".join(f"{m}:{d}" for m, d in delays.items()))

        times, stale = [], 0
        for _ in range(a.n):
            t0 = time.perf_counter()
            client.read_position_velocity_current()
            times.append((time.perf_counter() - t0) * 1000.0)
            if not client.last_read_ok:
                stale += 1
    finally:
        hand.disconnect()

    times.sort()
    p95 = times[int(0.95 * (len(times) - 1))]
    mean = statistics.mean(times)
    print(f"\n{a.n} full reads of {len(cfg.motor_ids) - len(absent)} motors:")
    print(f"  mean {mean:.1f} ms   median {statistics.median(times):.1f} ms   "
          f"p95 {p95:.1f} ms   max {times[-1]:.1f} ms")
    print(f"  => about {1000.0 / mean:.0f} reads per second")
    print(f"  stale / failed reads: {stale}  (should be 0)")
    print("\nCopy everything above into docs (U2D2 baseline vs KM1M7C).")
    return 0 if stale == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
