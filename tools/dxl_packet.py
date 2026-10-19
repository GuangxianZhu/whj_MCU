#!/usr/bin/env python3
"""
dxl_packet.py — make DYNAMIXEL Protocol 2.0 packets (HEX to paste into a serial
terminal) and decode replies. Same CRC and byte stuffing as firmware/dxl/dxl.c.

Make a packet:
  python tools/dxl_packet.py ping 1
  python tools/dxl_packet.py ping all                 # broadcast ping
  python tools/dxl_packet.py led 2 on
  python tools/dxl_packet.py torque 2 on
  python tools/dxl_packet.py goal 2 3072              # Goal Position, 0..4095
  python tools/dxl_packet.py setid 1 2                # ID 1 -> 2 (torque must be off)
  python tools/dxl_packet.py sync-goal 1:1024 2:3072  # both move at once
  python tools/dxl_packet.py sync-pos 1 2             # read both positions
  python tools/dxl_packet.py read 1 132 4             # any address, any length
  python tools/dxl_packet.py write 1 65 1 1           # id addr len value
  python tools/dxl_packet.py reboot 1

Decode what came back (one or several status packets in a row):
  python tools/dxl_packet.py parse "FF FF FD 00 01 08 00 55 00 A6 00 00 00 8C C0"

Check against the ROBOTIS e-Manual examples:
  python tools/dxl_packet.py selftest
"""
import sys

BROADCAST = 0xFE
ADDR = {"id": 7, "baud": 8, "return_delay": 9, "torque": 64, "led": 65,
        "hw_error": 70, "goal": 116, "present_pos": 132}
ERR_BITS = {1: "Result Fail", 2: "Instruction Error", 3: "CRC Error", 4: "Data Range Error",
            5: "Data Length Error", 6: "Data Limit Error", 7: "Access Error"}


def crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x8005) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def packet(id_: int, inst: int, params: bytes = b"") -> bytes:
    body = bytearray([inst])
    for b in params:                      # byte stuffing: FF FF FD -> FF FF FD FD
        body.append(b)
        if len(body) >= 3 and body[-3:] == b"\xff\xff\xfd":
            body.append(0xFD)
    length = len(body) + 2
    p = bytearray([0xFF, 0xFF, 0xFD, 0x00, id_, length & 0xFF, length >> 8]) + body
    c = crc16(bytes(p))
    return bytes(p + bytes([c & 0xFF, c >> 8]))


def le(value: int, n: int) -> bytes:
    return (value & ((1 << (8 * n)) - 1)).to_bytes(n, "little")


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def write(id_, addr, n, value):
    return packet(id_, 0x03, le(addr, 2) + le(value, n))


def build(args):
    cmd = args[0]
    a = args[1:]
    idv = lambda s: BROADCAST if s.lower() in ("all", "fe", "254") else int(s, 0)
    onoff = lambda s: 1 if s.lower() in ("on", "1") else 0
    if cmd == "ping":   return packet(idv(a[0]), 0x01)
    if cmd == "led":    return write(idv(a[0]), ADDR["led"], 1, onoff(a[1]))
    if cmd == "torque": return write(idv(a[0]), ADDR["torque"], 1, onoff(a[1]))
    if cmd == "goal":   return write(idv(a[0]), ADDR["goal"], 4, int(a[1], 0))
    if cmd == "setid":  return write(int(a[0], 0), ADDR["id"], 1, int(a[1], 0))
    if cmd == "reboot": return packet(idv(a[0]), 0x08)
    if cmd == "read":   return packet(idv(a[0]), 0x02, le(int(a[1], 0), 2) + le(int(a[2], 0), 2))
    if cmd == "write":  return write(idv(a[0]), int(a[1], 0), int(a[2], 0), int(a[3], 0))
    if cmd == "sync-goal":
        p = le(ADDR["goal"], 2) + le(4, 2)
        for item in a:
            i, v = item.split(":")
            p += bytes([int(i, 0)]) + le(int(v, 0), 4)
        return packet(BROADCAST, 0x83, p)
    if cmd == "sync-pos":
        return packet(BROADCAST, 0x82, le(ADDR["present_pos"], 2) + le(4, 2) + bytes(int(i, 0) for i in a))
    raise SystemExit(f"unknown command: {cmd}\n{__doc__}")


def parse(text: str):
    data = bytes(int(t, 16) for t in text.replace(",", " ").split())
    i = 0
    found = 0
    while i + 10 <= len(data) + 0:
        j = data.find(b"\xff\xff\xfd\x00", i)
        if j < 0 or j + 7 > len(data):
            break
        length = data[j + 5] | (data[j + 6] << 8)
        end = j + 7 + length
        if end > len(data):
            print(f"incomplete packet at byte {j}: need {end - j} bytes, have {len(data) - j}")
            break
        pkt = data[j:end]
        ok = crc16(pkt[:-2]) == (pkt[-2] | (pkt[-1] << 8))
        id_, inst = pkt[4], pkt[7]
        print(f"packet: {hexs(pkt)}")
        print(f"  ID {id_}, instruction 0x{inst:02X}{' (status reply)' if inst == 0x55 else ''}, CRC {'OK' if ok else 'WRONG'}")
        if inst == 0x55:
            err = pkt[8]
            params = bytearray()                      # destuff
            raw = pkt[9:-2]
            k = 0
            while k < len(raw):
                params.append(raw[k])
                if len(params) >= 3 and params[-3:] == b"\xff\xff\xfd" and k + 1 < len(raw) and raw[k + 1] == 0xFD:
                    k += 1
                k += 1
            names = [n for bit, n in ERR_BITS.items() if (err & 0x7F) == bit]
            print(f"  error byte 0x{err:02X}: {'none' if err & 0x7F == 0 else ', '.join(names) or 'code ' + str(err & 0x7F)}"
                  f"{' (hardware alert: read address 70)' if err & 0x80 else ''}")
            if params:
                print(f"  data: {hexs(params)}")
                if len(params) == 3:
                    print(f"  ping reply: model {params[0] | params[1] << 8} (1200 = XL330-M288, 1190 = XL330-M077), firmware {params[2]}")
                if len(params) == 4:
                    v = int.from_bytes(params, "little", signed=True)
                    print(f"  as a 4-byte value: {v}  (position: 0..4095 = one turn, 2048 = centre)")
        found += 1
        i = end
    if not found:
        print("no packet found (looking for FF FF FD 00)")


def selftest():
    ref = {
        "ping 1": "FF FF FD 00 01 03 00 01 19 4E",
        "ping all": "FF FF FD 00 FE 03 00 01 31 42",
        "led 1 on": "FF FF FD 00 01 06 00 03 41 00 01 CC E6",
        "reboot 1": "FF FF FD 00 01 03 00 08 2F 4E",
        "sync-goal 1:150 2:170": "FF FF FD 00 FE 11 00 83 74 00 04 00 01 96 00 00 00 02 AA 00 00 00 82 87",
        "sync-pos 1 2": "FF FF FD 00 FE 09 00 82 84 00 04 00 01 02 CE FA",
        "read 1 132 4": "FF FF FD 00 01 07 00 02 84 00 04 00 1D 15",
    }
    bad = 0
    for cmd, want in ref.items():
        got = hexs(build(cmd.split()))
        print(("ok   " if got == want else "FAIL ") + f"{cmd:24s} {got}")
        bad += got != want
    print("\nall passed" if not bad else f"\n{bad} FAILED")
    return 1 if bad else 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    if sys.argv[1] == "selftest":
        return selftest()
    if sys.argv[1] == "parse":
        parse(" ".join(sys.argv[2:]))
        return 0
    print(hexs(build(sys.argv[1:])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
