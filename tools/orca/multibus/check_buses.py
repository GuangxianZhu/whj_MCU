#!/usr/bin/env python3
"""Which motors answer on which COM port? Read-only wiring check.

Run this BEFORE the hand software, with the servo power on:

    cd <orca_core folder>
    uv run python <whj_MCU>\\tools\\orca\\multibus\\check_buses.py
    uv run python <whj_MCU>\\tools\\orca\\multibus\\check_buses.py path\\to\\buses.yaml

It opens every USB serial port, pings motor IDs 1-17 and prints who answered.
It only pings: no torque, no writes, nothing moves. It does not need the
multibus patch, only the packages orca_core already installs.

With a buses.yaml it also says whether the wiring matches the table and
prints the table again with the COM numbers filled in.

All output is plain ASCII so any Windows console can print it.
"""
import argparse
import sys
import time

import dynamixel_sdk
import serial.tools.list_ports


def ping_ids(port, baud, ids):
    """{motor_id: model_number} for the IDs that answer; None if the port will not open."""
    handler = dynamixel_sdk.PortHandler(port)
    found = {}
    try:
        if not handler.openPort() or not handler.setBaudRate(baud):
            return None
        packet = dynamixel_sdk.PacketHandler(2.0)
        for motor_id in ids:
            model, comm, _ = packet.ping(handler, motor_id)
            if comm == dynamixel_sdk.COMM_SUCCESS:
                found[motor_id] = model
    except Exception as exc:
        print(f"    could not open: {exc}".encode("ascii", "replace").decode())
        return None
    finally:
        try:
            handler.closePort()
        except Exception:
            pass
        time.sleep(0.3)
    return found


def load_table(path):
    """{bus name: [ids]} from buses.yaml (both accepted shapes)."""
    import yaml

    with open(path, "r", encoding="utf-8-sig") as handle:
        raw = yaml.safe_load(handle) or {}
    table = {}
    for name, entry in (raw.get("buses") or {}).items():
        ids = entry.get("ids") if isinstance(entry, dict) else entry
        table[str(name)] = [int(m) for m in ids]
    return table, raw.get("baudrate")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("buses", nargs="?", help="buses.yaml to compare the wiring with")
    ap.add_argument("--baud", type=int, help="servo baud rate (default: buses.yaml, else 1000000)")
    ap.add_argument("--ports", nargs="+", help="only probe these ports, e.g. --ports COM5 COM6")
    ap.add_argument("--all", action="store_true", help="also probe ports that are not USB")
    a = ap.parse_args()

    table, table_baud = load_table(a.buses) if a.buses else ({}, None)
    baud = a.baud or table_baud or 1000000
    ids = list(range(1, 18))

    listed = list(serial.tools.list_ports.comports())
    print("Serial ports on this PC:")
    if not listed:
        print("  (none - are the boards plugged in?)")
    for p in listed:
        usb = f"USB {p.vid:04X}:{p.pid:04X}" if p.vid is not None else "not USB"
        line = f"  {p.device:<8} {usb:<14} {p.description}"
        print(line.encode("ascii", "replace").decode())

    if a.ports:
        ports = [x.upper() if x.upper().startswith("COM") else x for x in a.ports]
    else:
        ports = [p.device for p in listed if a.all or p.vid is not None]
        skipped = [p.device for p in listed if p.device not in ports]
        if skipped:
            print(f"  not probed (not USB): {', '.join(skipped)}  "
                  f"-> add --all, or --ports {skipped[0]}, to include")

    print(f"\nPinging motor IDs 1-17 at {baud} baud (read-only):")
    seen = {}
    for port in ports:
        print(f"  {port} ...")
        found = ping_ids(port, baud, ids)
        if found is None:
            print("    port could not be opened (in use by another program?)")
            continue
        seen[port] = found
        if found:
            print("    answered: " + ", ".join(f"ID {m} (model {found[m]})" for m in sorted(found)))
        else:
            print("    no motor answered")

    print("\nVerdict:")
    problems = 0
    where = {}
    for port, found in seen.items():
        for motor_id in found:
            where.setdefault(motor_id, []).append(port)
    doubled = {m: ps for m, ps in where.items() if len(ps) > 1}
    if doubled:
        problems += 1
        both = sorted({p for ps in doubled.values() for p in ps})
        print(f"  PROBLEM: motor IDs {sorted(doubled)} answer on more than one port ({', '.join(both)}).")
        print("           The DATA lines of those boards are connected together, most likely")
        print("           through the power board: its TTL sockets all share one DATA pin.")
        print("           From the power board take only GND and VDD to each finger.")
    if not where:
        problems += 1
        print("  PROBLEM: no motor answered on any port. Check: servo power on, DATA and GND")
        print("           wires to each board, baud rate, and that no other program holds the port.")

    if table:
        ports_of = {}
        for name, bus_ids in table.items():
            hits = sorted({p for m in bus_ids for p in where.get(m, [])})
            answered = sorted(m for m in bus_ids if m in where)
            missing = sorted(m for m in bus_ids if m not in where)
            if len(hits) == 1 and not missing:
                foreign = sorted(m for m in seen[hits[0]] if m not in bus_ids)
                owners = sorted({n for n, other in table.items() if n != name
                                 for m in foreign if m in other})
                if owners:
                    problems += 1
                    print(f"  PROBLEM: {hits[0]} carries bus '{name}' and also motors of bus {owners}.")
                else:
                    ports_of[name] = hits[0]
                    extra = f" (also sees IDs {foreign}, on no bus: harmless)" if foreign else ""
                    print(f"  OK: bus '{name}' {bus_ids} is on {hits[0]}{extra}")
            elif not hits:
                problems += 1
                print(f"  PROBLEM: bus '{name}' {bus_ids}: no port answered for it.")
            elif missing:
                problems += 1
                print(f"  PROBLEM: bus '{name}': IDs {answered} answer on {hits}, IDs {missing} do not answer.")
            else:
                problems += 1
                print(f"  PROBLEM: bus '{name}' {bus_ids} is spread over ports {hits}.")
        if not problems and len(ports_of) == len(table):
            print("\nWiring matches the table. buses.yaml with the ports written in")
            print("(optional - without 'port:' they are found automatically):\n")
            print(f"baudrate: {baud}")
            print("buses:")
            for name, bus_ids in table.items():
                print(f"  {name}: {{ids: {bus_ids}, port: {ports_of[name]}}}")
    elif where and not problems:
        for port, found in seen.items():
            if found:
                print(f"  {port}: IDs {sorted(found)}")
    print("\nRESULT:", "OK" if not problems else f"{problems} problem(s) - fix before running the hand")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
