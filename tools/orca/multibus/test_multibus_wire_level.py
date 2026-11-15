"""The multibus client driven through the real Dynamixel driver (local addition).

``test_multibus_client.py`` puts mock clients under the combined client. Here
the buses are the real ``DynamixelClient`` and the real DynamixelSDK, and only
the serial port is replaced: ``FakeSerial`` answers Protocol 2.0 packets byte
for byte the way a chain of servos would. That reaches the code a real hand
runs and a mock never does: pinging, sync reads and writes, register access.

No hardware and no real serial port are touched.
"""
import os
import runpy
import sys

import dynamixel_sdk
import numpy as np
import pytest
import serial

from orca_core import OrcaHand
from orca_core.hardware import multibus_client as mb
from orca_core.hardware.dynamixel_client import DynamixelClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEFT_CONFIG = os.path.join(
    REPO_ROOT, "orca_core", "models", "v2", "orcahand-left", "config.yaml")

INDEX, MIDDLE = [7, 8, 9], [6, 17, 2]
OTHERS = [1, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16]

PING, READ, WRITE, REBOOT = 0x01, 0x02, 0x03, 0x08
SYNC_READ, SYNC_WRITE, STATUS = 0x82, 0x83, 0x55
BROADCAST = 0xFE
ADDR_TORQUE, ADDR_GOAL_POS, ADDR_PRESENT_POS = 64, 116, 132

_CRC = dynamixel_sdk.PacketHandler(2.0)


def _status(motor_id, params=(), error=0):
    """One Protocol 2.0 status packet, byte stuffing and CRC included."""
    body = [0xFF, 0xFF, 0xFD, 0x00, motor_id, 0, 0, STATUS, error, *params, 0, 0]
    length = len(params) + 4
    body[5], body[6] = length & 0xFF, length >> 8
    _CRC.addStuffing(body)
    total = (body[5] | (body[6] << 8)) + 7
    crc = _CRC.updateCRC(0, body, total - 2)
    body[total - 2], body[total - 1] = crc & 0xFF, crc >> 8
    return bytes(body[:total])


class Servo:
    """An XC330-T288-T as far as its control table goes."""

    def __init__(self, motor_id):
        self.id = motor_id
        self.table = bytearray(256)
        self.table[0:2] = (1220).to_bytes(2, "little")   # model number
        self.table[6] = 52                                 # firmware version
        self.table[7] = motor_id
        self.table[8] = 3                                  # 1 Mbps
        self.table[9] = 10                                 # return delay, 20 us
        self.table[11] = 3                                 # position mode
        self.table[31] = 70                                # temperature limit
        self.table[38:40] = (1750).to_bytes(2, "little")   # current limit
        self.table[63] = 0x35                              # shutdown mask
        self.table[ADDR_PRESENT_POS:ADDR_PRESENT_POS + 4] = (2048).to_bytes(4, "little")
        self.table[146] = 31                               # temperature
        self.writes = []

    def write(self, address, data):
        """Returns the status error byte (0 = fine)."""
        if address < 64 and self.table[ADDR_TORQUE]:
            return 0x07  # EEPROM is locked while torque is on
        self.table[address:address + len(data)] = data
        self.writes.append(address)
        if address <= ADDR_GOAL_POS < address + len(data) and self.table[ADDR_TORQUE]:
            # An ideal servo: it is where it was told to be.
            self.table[ADDR_PRESENT_POS:ADDR_PRESENT_POS + 4] = \
                self.table[ADDR_GOAL_POS:ADDR_GOAL_POS + 4]
        return 0


class Wire:
    """One half-duplex data line with servos on it."""

    def __init__(self, motor_ids):
        self.servos = {m: Servo(m) for m in motor_ids}
        self.cut = False       # True = cable pulled: nothing answers
        self.instructions = []

    def answer(self, motor_id, instruction, params):
        if self.cut:
            return b""
        self.instructions.append((motor_id, instruction))
        out = b""
        if instruction == PING and motor_id in self.servos:
            table = self.servos[motor_id].table
            out = _status(motor_id, [table[0], table[1], table[6]])
        elif instruction == READ and motor_id in self.servos:
            address = params[0] | (params[1] << 8)
            size = params[2] | (params[3] << 8)
            out = _status(motor_id, self.servos[motor_id].table[address:address + size])
        elif instruction == WRITE and motor_id in self.servos:
            address = params[0] | (params[1] << 8)
            out = _status(motor_id, error=self.servos[motor_id].write(address, params[2:]))
        elif instruction == REBOOT and motor_id in self.servos:
            self.servos[motor_id].table[ADDR_TORQUE] = 0
            out = _status(motor_id)
        elif instruction == SYNC_READ and motor_id == BROADCAST:
            address = params[0] | (params[1] << 8)
            size = params[2] | (params[3] << 8)
            for target in params[4:]:
                if target in self.servos:
                    out += _status(target, self.servos[target].table[address:address + size])
        elif instruction == SYNC_WRITE and motor_id == BROADCAST:
            address = params[0] | (params[1] << 8)
            size = params[2] | (params[3] << 8)
            step = size + 1
            for at in range(4, len(params), step):
                target = params[at]
                if target in self.servos:
                    self.servos[target].write(address, params[at + 1:at + step])
        # Anything else (fast sync read, unknown IDs) goes unanswered, as on
        # servo firmware without it.
        return out


class FakeSerial:
    """Stands in for ``serial.Serial``; ``wiring`` maps port name -> Wire."""

    wiring = {}
    opened = []

    def __init__(self, port=None, baudrate=None, **kwargs):
        if port not in self.wiring:
            raise serial.SerialException(f"could not open port {port!r}")
        self.port, self.baudrate = port, baudrate
        self.wire = self.wiring[port]
        self.is_open = True
        self._tx = bytearray()
        self._rx = bytearray()
        FakeSerial.opened.append(port)

    def write(self, data):
        self._tx += bytes(data)
        while True:
            start = self._tx.find(b"\xff\xff\xfd\x00")
            if start < 0 or len(self._tx) - start < 7:
                break
            length = self._tx[start + 5] | (self._tx[start + 6] << 8)
            total = length + 7
            if len(self._tx) - start < total:
                break
            packet = list(self._tx[start:start + total])
            del self._tx[:start + total]
            packet = _CRC.removeStuffing(packet)
            length = packet[5] | (packet[6] << 8)
            params = bytes(packet[8:8 + length - 3])
            if self.baudrate == 1000000:  # servos only hear their own rate
                self._rx += self.wire.answer(packet[4], packet[7], params)
        return len(data)

    def read(self, size=1):
        out = bytes(self._rx[:size])
        del self._rx[:size]
        return out

    @property
    def in_waiting(self):
        return len(self._rx)

    def reset_input_buffer(self):
        self._rx.clear()

    def reset_output_buffer(self):
        pass

    def flush(self):
        pass

    def close(self):
        self.is_open = False


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """Returns ``plug(wiring, buses_yaml)`` -> config path of a multibus hand."""
    monkeypatch.setattr(serial, "Serial", FakeSerial)
    monkeypatch.setattr(mb, "MOTOR_PORT_CLOSE_SETTLE_S", 0.0)
    monkeypatch.setattr(OrcaHand, "_port_close_settle_s", 0.0)
    FakeSerial.opened = []
    text = open(LEFT_CONFIG, encoding="utf-8").read()
    (tmp_path / "config.yaml").write_text(
        text.replace("port: auto", "port: multibus"), encoding="utf-8")

    def plug(wiring, buses_yaml):
        FakeSerial.wiring = wiring
        monkeypatch.setattr(mb, "_candidate_ports", lambda: list(wiring))
        (tmp_path / mb.BUSES_FILE).write_text(buses_yaml, encoding="utf-8")
        return str(tmp_path / "config.yaml")

    return plug


TWO_FINGERS = ("baudrate: 1000000\nbuses:\n"
               "  index: [7, 8, 9]\n  middle: [6, 17, 2]\n")
TWO_FINGERS_PORTS = ("baudrate: 1000000\nbuses:\n"
                     "  index: {ids: [7, 8, 9], port: COM5}\n"
                     "  middle: {ids: [6, 17, 2], port: COM6}\n")


def connected_hand(config_path):
    hand = OrcaHand(config_path=config_path)
    ok, message = hand.connect(interactive=False)
    assert ok, message
    return hand


@pytest.mark.parametrize("buses_yaml", [TWO_FINGERS, TWO_FINGERS_PORTS])
def test_two_fingers_on_two_boards_end_to_end(bench, buses_yaml):
    index, middle = Wire(INDEX), Wire(MIDDLE)
    hand = connected_hand(bench({"COM5": index, "COM6": middle}, buses_yaml))
    try:
        client = hand.motor_client
        assert isinstance(client, mb.MultiBusClient)
        assert isinstance(client, DynamixelClient)
        assert client.responding_motor_ids() == sorted(INDEX + MIDDLE)
        assert sorted(hand.absent_motor_ids) == OTHERS
        assert "index=COM5" in client.port_name and "middle=COM6" in client.port_name

        # Reads: 17 slots in config order, fresh.
        position = hand.get_motor_pos()
        assert len(position) == 17
        assert client.last_read_ok is True
        assert len(hand.get_motor_temp()) == 17

        # Torque on reaches both boards, and nothing else.
        hand.enable_torque()
        assert all(s.table[ADDR_TORQUE] == 1 for s in index.servos.values())
        assert all(s.table[ADDR_TORQUE] == 1 for s in middle.servos.values())

        # A goal for one motor on each board lands on the right servo.
        ids = hand.config.motor_ids
        target = client.read_position_velocity_current().position.copy()
        target[ids.index(8)] += 0.30
        target[ids.index(17)] -= 0.20
        client.write_desired_pos(ids, target)
        after = client.read_position_velocity_current().position
        assert after[ids.index(8)] == pytest.approx(target[ids.index(8)], abs=2e-3)
        assert after[ids.index(17)] == pytest.approx(target[ids.index(17)], abs=2e-3)
        untouched = [m for m in INDEX + MIDDLE if m not in (8, 17)]
        for motor_id in untouched:
            assert after[ids.index(motor_id)] == pytest.approx(
                position[ids.index(motor_id)], abs=2e-3)

        # Registers and status, one motor at a time.
        assert client.read_config_register(9, "return_delay_time") is not None
        assert client.read_config_register(1, "return_delay_time") is None
        assert client.read_hardware_error(6) == 0
        assert set(client.read_hardware_errors(ids)) == set(ids)
        assert client.read_current_limits()[7] is not None
        assert client.read_current_limits()[1] is None

        # Each wire only ever carried packets for its own motors.
        assert {m for m, _ in index.instructions} <= set(INDEX) | {BROADCAST} | set(MIDDLE)
        addressed_after_search = {m for m, _ in middle.instructions[len(INDEX + MIDDLE):]}
        assert addressed_after_search <= set(MIDDLE) | {BROADCAST}

        hand.disable_torque()
        assert all(s.table[ADDR_TORQUE] == 0 for s in index.servos.values())
    finally:
        ok, message = hand.disconnect()
    assert ok, message


def test_swapped_usb_sockets_still_put_each_finger_on_its_own_board(bench):
    index, middle = Wire(INDEX), Wire(MIDDLE)
    hand = connected_hand(bench({"COM5": middle, "COM6": index}, TWO_FINGERS))
    try:
        assert "index=COM6" in hand.motor_client.port_name
        hand.enable_torque()
        ids = hand.config.motor_ids
        target = hand.motor_client.read_position_velocity_current().position.copy()
        target[ids.index(7)] += 0.25
        hand.motor_client.write_desired_pos(ids, target)
        moved = int.from_bytes(index.servos[7].table[132:136], "little")
        assert moved != 2048
        for servo in middle.servos.values():
            assert int.from_bytes(servo.table[132:136], "little") == 2048
    finally:
        hand.disconnect()


def test_written_ports_swapped_is_caught_not_obeyed(bench):
    """COM numbers written the wrong way round: refuse, do not move the wrong finger."""
    index, middle = Wire(INDEX), Wire(MIDDLE)
    hand = OrcaHand(config_path=bench({"COM5": middle, "COM6": index}, TWO_FINGERS_PORTS))
    ok, message = hand.connect(interactive=False)
    assert ok is False
    assert "index" in message and "COM5" in message and "swap" in message
    assert all(s.table[ADDR_TORQUE] == 0 for w in (index, middle) for s in w.servos.values())


def test_data_lines_joined_through_the_power_board_are_refused(bench):
    """Both boards on one data line: each port answers for all six motors."""
    joined = Wire(INDEX + MIDDLE)
    hand = OrcaHand(config_path=bench({"COM5": joined, "COM6": joined}, TWO_FINGERS))
    ok, message = hand.connect(interactive=False)
    assert ok is False
    assert "splits over buses" in message


def test_other_motors_sharing_a_finger_s_data_line_do_not_matter(bench):
    """The eleven idle motors hang on the index board's line: still fine."""
    index, middle = Wire(INDEX + OTHERS), Wire(MIDDLE)
    hand = connected_hand(bench({"COM5": index, "COM6": middle}, TWO_FINGERS))
    try:
        assert hand.motor_client.responding_motor_ids() == sorted(INDEX + MIDDLE)
        hand.enable_torque()
        assert all(index.servos[m].table[ADDR_TORQUE] == 0 for m in OTHERS)
    finally:
        hand.disconnect()


def test_unpowered_servos_give_a_clear_message(bench):
    index, middle = Wire(INDEX), Wire(MIDDLE)
    index.cut = middle.cut = True
    hand = OrcaHand(config_path=bench({"COM5": index, "COM6": middle}, TWO_FINGERS))
    ok, message = hand.connect(interactive=False)
    assert ok is False
    assert "no port answered" in message and "COM5: no answer" in message


def test_wrong_baud_rate_in_the_table_gives_a_clear_message(bench):
    index, middle = Wire(INDEX), Wire(MIDDLE)
    slow = TWO_FINGERS.replace("1000000", "57600")
    hand = OrcaHand(config_path=bench({"COM5": index, "COM6": middle}, slow))
    ok, message = hand.connect(interactive=False)
    assert ok is False and "57600 baud" in message


def test_one_board_unplugged_mid_run_marks_reads_stale_and_keeps_the_other(bench):
    index, middle = Wire(INDEX), Wire(MIDDLE)
    hand = connected_hand(bench({"COM5": index, "COM6": middle}, TWO_FINGERS))
    try:
        client = hand.motor_client
        client.read_position_velocity_current()
        assert client.last_read_ok is True
        middle.cut = True
        client.read_position_velocity_current()
        assert client.last_read_ok is False
        # The board that is still there keeps working.
        hand.enable_torque()
        assert all(s.table[ADDR_TORQUE] == 1 for s in index.servos.values())
    finally:
        ok, message = hand.disconnect()
    # Disconnect closes both ports, lets go of the finger it can still reach,
    # and names the motors it could not reach.
    assert ok is False and "[2, 6, 17]" in message
    assert all(s.table[ADDR_TORQUE] == 0 for s in index.servos.values())
    assert hand.is_connected() is False


def test_a_third_serial_device_is_probed_but_left_alone(bench):
    index, middle, other = Wire(INDEX), Wire(MIDDLE), Wire([])
    hand = connected_hand(bench(
        {"COM3": other, "COM5": index, "COM6": middle}, TWO_FINGERS))
    try:
        assert {m for m, i in other.instructions} <= set(INDEX + MIDDLE)
        assert {i for m, i in other.instructions} == {PING}
    finally:
        hand.disconnect()
    # With the ports written down, it is not opened at all.
    FakeSerial.opened = []
    hand = connected_hand(bench(
        {"COM3": other, "COM5": index, "COM6": middle}, TWO_FINGERS_PORTS))
    hand.disconnect()
    assert "COM3" not in FakeSerial.opened


def test_parallel_buses_give_the_same_answers(bench):
    index, middle = Wire(INDEX), Wire(MIDDLE)
    hand = connected_hand(bench(
        {"COM5": index, "COM6": middle}, "parallel: true\n" + TWO_FINGERS))
    try:
        hand.enable_torque()
        for _ in range(20):
            assert len(hand.get_motor_pos()) == 17
            assert hand.motor_client.last_read_ok is True
    finally:
        hand.disconnect()
