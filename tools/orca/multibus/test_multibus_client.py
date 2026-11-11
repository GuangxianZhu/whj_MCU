"""Several motor buses behind one client (local addition, not upstream).

Nothing here touches a serial port: buses are in-memory mock clients and the
port search is fed a scripted answer.
"""
import inspect
import os
import shutil

import numpy as np
import pytest

from orca_core import OrcaHand
from orca_core.hardware import multibus_client as mb
from orca_core.hardware.dynamixel_client import DynamixelClient
from orca_core.hardware.mock_dynamixel_client import MockDynamixelClient
from orca_core.hardware.motor_client import MotorClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEFT_CONFIG = os.path.join(
    REPO_ROOT, "orca_core", "models", "v2", "orcahand-left", "config.yaml")

ALL_IDS = list(range(1, 18))
TWO_BUSES = {"index": [7, 8, 9], "middle": [6, 17, 2]}
SIX_BUSES = {
    "index": [7, 8, 9],
    "middle": [6, 17, 2],
    "ring": [5, 4, 3],
    "pinky": [14, 15, 16],
    "thumb": [13, 12, 11],
    "wrist_cmc": [1, 10],
}


def write_buses(folder, buses, baudrate=1000000, parallel=False):
    lines = [f"baudrate: {baudrate}", f"parallel: {str(parallel).lower()}", "buses:"]
    for name, ids in buses.items():
        lines.append(f"  {name}: {ids}")
    path = os.path.join(str(folder), mb.BUSES_FILE)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def fake_wiring(buses, extra_ports=()):
    """``(ping, candidates)`` as if each bus sat on its own COM port."""
    on_port = {f"COM{10 + i}": set(ids) for i, ids in enumerate(buses.values())}
    for port in extra_ports:
        on_port[port] = set()

    def ping(port, baudrate, motor_ids):
        return [m for m in motor_ids if m in on_port.get(port, ())]

    return ping, (lambda: list(on_port))


def make_client(tmp_path, buses, parallel=False, motor_ids=ALL_IDS):
    spec = mb.load_buses(write_buses(tmp_path, buses, parallel=parallel))
    ping, candidates = fake_wiring(buses)
    created = {}

    def factory(ids, port, baudrate):
        created[port] = MockDynamixelClient(ids, port, baudrate)
        return created[port]

    client = mb.multibus_class_for(MockDynamixelClient)(
        motor_ids, spec, 1000000, factory,
        port_resolver=lambda s, b: mb.resolve_bus_ports(s, b, ping, candidates))
    return client, created


# ----- buses.yaml --------------------------------------------------------------

def test_buses_file_accepts_both_shapes(tmp_path):
    path = tmp_path / mb.BUSES_FILE
    path.write_text(
        "baudrate: 1000000\n"
        "buses:\n"
        "  index: [7, 8, 9]\n"
        "  middle: {ids: [6, 17, 2], port: COM7}\n", encoding="utf-8")
    spec = mb.load_buses(str(path))
    assert [(b.name, b.motor_ids, b.port) for b in spec.buses] == [
        ("index", (7, 8, 9), None), ("middle", (6, 17, 2), "COM7")]
    assert spec.baudrate == 1000000 and spec.parallel is False


def test_buses_file_survives_a_bom_and_non_ascii_comments(tmp_path):
    path = tmp_path / mb.BUSES_FILE
    path.write_bytes("﻿# 食指和中指\nbuses:\n  index: [7, 8, 9]\n".encode("utf-8"))
    assert mb.load_buses(str(path)).buses[0].motor_ids == (7, 8, 9)


@pytest.mark.parametrize("body, fragment", [
    ("buses:\n  a: [7, 8]\n  b: [8, 9]\n", "both"),
    ("buses:\n  a: [7, 7]\n", "twice"),
    ("buses:\n  a: []\n", "list of motor IDs"),
    ("baudrate: 1000000\n", "buses"),
    ("buses:\n  a: {ids: [1], port: COM3}\n  b: {ids: [2], port: com3}\n", "port"),
])
def test_buses_file_mistakes_are_refused(tmp_path, body, fragment):
    path = tmp_path / mb.BUSES_FILE
    path.write_text(body, encoding="utf-8")
    with pytest.raises(mb.MultiBusConfigError, match=fragment):
        mb.load_buses(str(path))


def test_missing_buses_file_says_where_it_looked(tmp_path):
    with pytest.raises(mb.MultiBusConfigError, match="not found"):
        mb.load_buses(str(tmp_path / mb.BUSES_FILE))


# ----- which port is which bus -------------------------------------------------

def test_ports_are_matched_by_the_motor_ids_that_answer(tmp_path):
    spec = mb.load_buses(write_buses(tmp_path, TWO_BUSES))
    ping, candidates = fake_wiring(TWO_BUSES, extra_ports=["COM3"])
    assert mb.resolve_bus_ports(spec, 1000000, ping, candidates) == {
        "index": "COM10", "middle": "COM11"}


def test_swapping_usb_sockets_does_not_swap_fingers(tmp_path):
    spec = mb.load_buses(write_buses(tmp_path, TWO_BUSES))
    swapped = {"middle": TWO_BUSES["middle"], "index": TWO_BUSES["index"]}
    ping, candidates = fake_wiring(swapped)
    assert mb.resolve_bus_ports(spec, 1000000, ping, candidates) == {
        "middle": "COM10", "index": "COM11"}


def test_a_port_carrying_two_fingers_is_refused(tmp_path):
    spec = mb.load_buses(write_buses(tmp_path, TWO_BUSES))
    with pytest.raises(mb.MultiBusConfigError, match="splits over buses"):
        mb.resolve_bus_ports(spec, 1000000,
                             lambda port, baud, ids: [7, 6], lambda: ["COM5"])


def test_two_ports_for_one_finger_are_refused(tmp_path):
    spec = mb.load_buses(write_buses(tmp_path, TWO_BUSES))
    with pytest.raises(mb.MultiBusConfigError, match="answers on both"):
        mb.resolve_bus_ports(spec, 1000000,
                             lambda port, baud, ids: [7], lambda: ["COM5", "COM6"])


def test_a_bus_nobody_answers_for_is_refused_and_named(tmp_path):
    spec = mb.load_buses(write_buses(tmp_path, TWO_BUSES))
    ping, candidates = fake_wiring({"index": [7, 8, 9]})
    with pytest.raises(mb.MultiBusConfigError, match="'middle'"):
        mb.resolve_bus_ports(spec, 1000000, ping, candidates)


def test_written_ports_are_kept_and_not_probed(tmp_path):
    path = tmp_path / mb.BUSES_FILE
    path.write_text("buses:\n  index: {ids: [7, 8, 9], port: COM5}\n", encoding="utf-8")
    spec = mb.load_buses(str(path))

    def no_ping(*args):
        raise AssertionError("a written port must not be probed")

    assert mb.resolve_bus_ports(spec, 1000000, no_ping, lambda: ["COM5"]) == {
        "index": "COM5"}


# ----- the combined client -----------------------------------------------------

@pytest.mark.parametrize("parallel", [False, True])
def test_writes_are_split_and_reads_come_back_in_config_order(tmp_path, parallel):
    client, created = make_client(tmp_path, SIX_BUSES, parallel=parallel)
    client.connect()
    try:
        client.set_torque_enabled(ALL_IDS, True)
        targets = np.array([0.01 * m for m in ALL_IDS], dtype=np.float32)
        client.write_desired_pos(ALL_IDS, targets)

        snapshot = client.read_position_velocity_current()
        np.testing.assert_allclose(snapshot.position, targets, atol=1e-6)
        assert client.last_read_ok is True

        # Each bus was only ever told about its own motors.
        index_bus = created["COM10"]
        assert index_bus.motor_ids == [7, 8, 9]
        np.testing.assert_allclose(
            index_bus.read_position_velocity_current().position,
            [0.07, 0.08, 0.09], atol=1e-6)
    finally:
        client.disconnect()
    assert client.is_connected is False
    assert all(not bus.is_connected for bus in created.values())


def test_a_partial_write_reaches_only_the_bus_it_names(tmp_path):
    client, created = make_client(tmp_path, TWO_BUSES)
    client.connect()
    client.set_torque_enabled([7, 8, 9, 6, 17, 2], True)
    client.write_desired_pos([17, 9], np.array([0.5, -0.5]))
    position = client.read_position_velocity_current().position
    by_id = dict(zip(ALL_IDS, position))
    assert by_id[17] == pytest.approx(0.5) and by_id[9] == pytest.approx(-0.5)
    assert all(by_id[m] == 0.0 for m in ALL_IDS if m not in (17, 9))
    client.disconnect()


def test_motors_on_no_bus_look_unplugged(tmp_path):
    client, _ = make_client(tmp_path, TWO_BUSES)
    client.connect()
    assert client.responding_motor_ids() == [2, 6, 7, 8, 9, 17]
    assert client.absent_motor_ids() == [1, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16]
    # Commands naming them are dropped, not errors.
    assert client.set_torque_enabled(ALL_IDS, True) == []
    client.write_desired_pos(ALL_IDS, np.zeros(17))
    assert client.read_hardware_error(1) is None
    assert client.read_goal_currents([1, 7])[1] is None
    assert len(client.read_temperature()) == 17
    client.disconnect()


def test_one_stale_bus_makes_the_whole_read_stale(tmp_path):
    client, created = make_client(tmp_path, TWO_BUSES)
    client.connect()
    client.read_position_velocity_current()
    assert client.last_read_ok is True
    created["COM11"].last_read_ok = False
    client.read_position_velocity_current()
    assert client.last_read_ok is False
    client.disconnect()


def test_failed_connect_closes_the_buses_already_opened(tmp_path):
    spec = mb.load_buses(write_buses(tmp_path, TWO_BUSES))
    ping, candidates = fake_wiring(TWO_BUSES)
    made = []

    def factory(ids, port, baudrate):
        bus = MockDynamixelClient(ids, port, baudrate)
        if port == "COM11":
            bus.connect = lambda: (_ for _ in ()).throw(OSError("unplugged"))
        made.append(bus)
        return bus

    client = mb.multibus_class_for(MockDynamixelClient)(
        ALL_IDS, spec, 1000000, factory,
        port_resolver=lambda s, b: mb.resolve_bus_ports(s, b, ping, candidates))
    with pytest.raises(ConnectionError, match="middle"):
        client.connect()
    assert client.is_connected is False
    assert made[0].is_connected is False


def test_a_bus_where_nothing_answers_fails_the_connect(tmp_path):
    spec = mb.load_buses(write_buses(tmp_path, TWO_BUSES))
    ping, candidates = fake_wiring(TWO_BUSES)

    def factory(ids, port, baudrate):
        bus = MockDynamixelClient(ids, port, baudrate)
        if port == "COM10":
            bus.silent_motor_ids = set(ids)
        return bus

    client = mb.multibus_class_for(MockDynamixelClient)(
        ALL_IDS, spec, 1000000, factory,
        port_resolver=lambda s, b: mb.resolve_bus_ports(s, b, ping, candidates))
    with pytest.raises(ConnectionError, match="index"):
        client.connect()


def test_table_naming_a_motor_the_hand_does_not_have_is_refused(tmp_path):
    with pytest.raises(mb.MultiBusConfigError, match="99"):
        make_client(tmp_path, {"index": [7, 8, 99]})


def test_family_constants_are_the_motor_family_s_own():
    cls = mb.multibus_class_for(DynamixelClient)
    for name in ("default_max_current_ma", "current_scale_ma", "supported_modes",
                 "waits_for_motion", "supports_reboot", "position_range_rad",
                 "sweep_current_ma", "slack_test_current_ma", "max_operating_temp_c"):
        assert getattr(cls, name) == getattr(DynamixelClient, name), name
    assert issubclass(cls, DynamixelClient)


# Inherited as they are: they read class constants only, or build on methods
# that are routed.
SAFE_TO_INHERIT = {
    "canonical_faults", "check_connected", "cleanup_open_clients",
    "decode_hardware_error", "default_profile", "probe", "scannable_baudrates",
    "servo_limits", "split_faults", "supported_baudrates",
    # Called by a single bus on itself while it handles a reply.
    "handle_packet_result",
}


def test_every_public_method_of_the_bus_client_is_routed():
    """The alarm for upstream changes.

    A method added to the single-bus client and not routed here would run
    against a combined client that has no serial port. If this fails after
    updating orca_core, add the named method to multibus_client.py.
    """
    routed = set(vars(mb.MultiBusClient))
    unrouted = sorted(
        name for name, member in inspect.getmembers(DynamixelClient)
        if not name.startswith("_")
        and (inspect.isfunction(member) or inspect.ismethod(member)
             or isinstance(inspect.getattr_static(DynamixelClient, name), property))
        and name not in routed and name not in SAFE_TO_INHERIT)
    assert unrouted == []


def test_single_bus_internals_fail_loudly(tmp_path):
    client, _ = make_client(tmp_path, TWO_BUSES)
    with pytest.raises(AttributeError, match="no serial port of its own"):
        client.port_handler
    with pytest.raises(NotImplementedError, match="one bus at a time"):
        client.change_motor_id(7, 8)


# ----- through OrcaHand, the way the scripts use it ----------------------------

@pytest.fixture
def multibus_dir(tmp_path, monkeypatch):
    """A left-hand model folder set to ``port: multibus`` with mock buses."""
    text = open(LEFT_CONFIG, encoding="utf-8").read()
    assert "port: auto" in text
    (tmp_path / "config.yaml").write_text(
        text.replace("port: auto", "port: multibus"), encoding="utf-8")

    def wire(buses, parallel=False):
        write_buses(tmp_path, buses, parallel=parallel)
        ping, candidates = fake_wiring(buses)
        monkeypatch.setattr(mb, "_ping_ids", ping)
        monkeypatch.setattr(mb, "_candidate_ports", candidates)
        monkeypatch.setattr(
            "orca_core.hardware.motor_factory.motor_client_class",
            lambda motor_type: MockDynamixelClient)
        return str(tmp_path / "config.yaml")

    return wire


@pytest.mark.parametrize("parallel", [False, True])
def test_hand_connects_calibrates_and_moves_over_six_buses(multibus_dir, parallel):
    hand = OrcaHand(config_path=multibus_dir(SIX_BUSES, parallel=parallel))
    ok, message = hand.connect(interactive=False)
    assert ok, message
    try:
        assert isinstance(hand._motor_client, mb.MultiBusClient)
        assert hand.config.baudrate == 1000000
        assert hand.absent_motor_ids == []
        hand.calibrate(persist=False)

        target = {}
        for joint in hand.config.joint_ids:
            low, high = hand.config.joint_roms_dict[joint]
            target[joint] = (low + high) / 2.0
        hand.set_joint_positions(target)
        actual = hand.get_joint_position().as_dict()
        for joint, expected in target.items():
            assert actual[joint] == pytest.approx(expected, abs=1e-4), joint
    finally:
        ok, message = hand.disconnect()
    assert ok, message
    assert hand.is_connected() is False


def test_hand_with_two_fingers_reports_the_other_joints_absent(multibus_dir):
    hand = OrcaHand(config_path=multibus_dir(TWO_BUSES))
    ok, message = hand.connect(interactive=False)
    assert ok, message
    try:
        assert sorted(hand.absent_motor_ids) == [1, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16]
        assert len(hand.get_motor_pos()) == 17
        hand.enable_torque()
        hand.disable_torque()
    finally:
        hand.disconnect()


def test_failed_multibus_connect_never_falls_back_to_one_port(multibus_dir, monkeypatch):
    config_path = multibus_dir(TWO_BUSES)
    monkeypatch.setattr(mb, "_ping_ids", lambda port, baud, ids: [])

    def no_fallback(*args, **kwargs):
        raise AssertionError("a multibus hand must not try a single port")

    monkeypatch.setattr("orca_core.hardware_hand.auto_detect_port", no_fallback)
    monkeypatch.setattr("orca_core.hardware_hand.get_and_choose_port", no_fallback)
    hand = OrcaHand(config_path=config_path)
    ok, message = hand.connect(interactive=True)
    assert ok is False
    assert "Multibus connection failed" in message and "no port answered" in message


def test_missing_table_is_reported_by_connect(tmp_path):
    text = open(LEFT_CONFIG, encoding="utf-8").read()
    (tmp_path / "config.yaml").write_text(
        text.replace("port: auto", "port: multibus"), encoding="utf-8")
    hand = OrcaHand(config_path=str(tmp_path / "config.yaml"))
    ok, message = hand.connect(interactive=False)
    assert ok is False and mb.BUSES_FILE in message


def test_ordinary_ports_are_untouched(tmp_path):
    """Without the keyword, nothing in this file is reached."""
    assert mb.is_multibus_port("multibus") and mb.is_multibus_port(" MultiBus ")
    for port in ("COM5", "auto", "/dev/ttyUSB0", None, "multibus2"):
        assert not mb.is_multibus_port(port)
