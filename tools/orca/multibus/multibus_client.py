# ==============================================================================
# Local addition (not part of upstream orca_core).
#
# Several motor buses presented to OrcaHand as one MotorClient.
#
# One bridge board (for example one KM1M7C) drives one finger and shows up on
# the PC as one COM port. OrcaHand only knows how to talk to a single motor
# client, so this file puts a "switchboard" in between: it looks up which bus
# a motor ID lives on, sends each bus its share of the request, and puts the
# answers back together in the order OrcaHand expects.
#
# Switched on by writing ``port: multibus`` in config.yaml. The routing table
# is ``buses.yaml`` in the same folder as that config.yaml.
#
# All messages in this file are plain ASCII on purpose: a Windows console in
# a non-UTF-8 code page cannot print anything else.
# ==============================================================================
"""Several motor buses presented as one :class:`MotorClient`."""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import yaml

from ..constants import MOTOR_PORT_CLOSE_SETTLE_S
from .motor_client import MotionTimeoutError, MotorClient, MotorRead

logger = logging.getLogger(__name__)

MULTIBUS_PORT = "multibus"
"""The value of ``port:`` in config.yaml that switches this client on."""

BUSES_FILE = "buses.yaml"
"""Routing table, looked up beside config.yaml."""


class MultiBusConfigError(ValueError):
    """buses.yaml is missing, malformed, or contradicts what is plugged in."""


def is_multibus_port(port: Any) -> bool:
    """True when ``port`` is the ``multibus`` keyword rather than a real port."""
    return isinstance(port, str) and port.strip().lower() == MULTIBUS_PORT


# ------------------------------------------------------------------------------
# buses.yaml
# ------------------------------------------------------------------------------

@dataclass(frozen=True)
class BusSpec:
    """One bus: a name, the motor IDs wired to it, and optionally its port."""
    name: str
    motor_ids: Tuple[int, ...]
    port: Optional[str] = None


@dataclass(frozen=True)
class MultiBusSpec:
    """Everything buses.yaml says."""
    buses: Tuple[BusSpec, ...]
    baudrate: Optional[int] = None
    motor_type: Optional[str] = None
    parallel: bool = False
    path: str = ""

    @property
    def routed_ids(self) -> List[int]:
        return [mid for bus in self.buses for mid in bus.motor_ids]


def buses_path_for(config_path: str) -> str:
    """Where buses.yaml is expected for the hand configured at ``config_path``."""
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), BUSES_FILE)


def load_buses(path: str) -> MultiBusSpec:
    """Read and check buses.yaml.

    Accepted shapes for one bus::

        index: [7, 8, 9]                       # port found automatically
        index: {ids: [7, 8, 9], port: COM5}    # port written down
    """
    if not os.path.isfile(path):
        raise MultiBusConfigError(
            f"port is '{MULTIBUS_PORT}' but the routing table was not found: "
            f"{path}. Create it next to config.yaml.")
    # utf-8-sig: explicit so a non-UTF-8 Windows locale cannot misread the
    # file, and tolerant of the BOM Notepad may add.
    with open(path, "r", encoding="utf-8-sig") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise MultiBusConfigError(f"{path}: the file must be a mapping.")

    raw_buses = raw.get("buses")
    if not isinstance(raw_buses, dict) or not raw_buses:
        raise MultiBusConfigError(
            f"{path}: needs a 'buses:' section with at least one bus.")

    buses: List[BusSpec] = []
    owner: Dict[int, str] = {}
    ports: Dict[str, str] = {}
    for name, entry in raw_buses.items():
        name = str(name)
        port = None
        ids = entry
        if isinstance(entry, dict):
            ids = entry.get("ids")
            port = entry.get("port")
            if port is not None:
                port = str(port).strip() or None
        if not isinstance(ids, (list, tuple)) or not ids:
            raise MultiBusConfigError(
                f"{path}: bus '{name}' needs a list of motor IDs, e.g. [7, 8, 9].")
        try:
            ids = tuple(int(mid) for mid in ids)
        except (TypeError, ValueError):
            raise MultiBusConfigError(
                f"{path}: bus '{name}' has a motor ID that is not a number.") from None
        if len(set(ids)) != len(ids):
            raise MultiBusConfigError(
                f"{path}: bus '{name}' lists the same motor ID twice.")
        for mid in ids:
            if mid in owner:
                raise MultiBusConfigError(
                    f"{path}: motor ID {mid} is listed on both '{owner[mid]}' "
                    f"and '{name}'. One motor can only be on one bus.")
            owner[mid] = name
        if port is not None:
            key = port.upper()
            if key in ports:
                raise MultiBusConfigError(
                    f"{path}: port {port} is given to both '{ports[key]}' "
                    f"and '{name}'.")
            ports[key] = name
        buses.append(BusSpec(name=name, motor_ids=ids, port=port))

    baudrate = raw.get("baudrate")
    if baudrate is not None:
        try:
            baudrate = int(baudrate)
        except (TypeError, ValueError):
            raise MultiBusConfigError(f"{path}: 'baudrate' must be a number.") from None
    motor_type = raw.get("motor_type")
    return MultiBusSpec(
        buses=tuple(buses),
        baudrate=baudrate,
        motor_type=str(motor_type) if motor_type else None,
        parallel=bool(raw.get("parallel", False)),
        path=path,
    )


# ------------------------------------------------------------------------------
# Finding which COM port is which bus
# ------------------------------------------------------------------------------

def _candidate_ports() -> List[str]:
    """USB serial ports worth probing.

    Ports without a USB vendor ID (Bluetooth serial links, legacy COM1) are
    left out: they are never a bridge board and opening them can block for
    seconds.
    """
    import serial.tools.list_ports

    return [p.device for p in serial.tools.list_ports.comports()
            if p.vid is not None]


def _ping_ids(port: str, baudrate: int, motor_ids: Sequence[int]) -> List[int]:
    """Motor IDs out of ``motor_ids`` that answer a ping on ``port``.

    Dynamixel Protocol 2.0 only. Never enables torque or writes anything.
    A port that cannot be opened (in use, unplugged) answers nothing.
    """
    import dynamixel_sdk

    handler = dynamixel_sdk.PortHandler(port)
    found: List[int] = []
    try:
        if not handler.openPort() or not handler.setBaudRate(baudrate):
            return []
        packet = dynamixel_sdk.PacketHandler(2.0)
        for motor_id in motor_ids:
            _, comm, _ = packet.ping(handler, int(motor_id))
            if comm == dynamixel_sdk.COMM_SUCCESS:
                found.append(int(motor_id))
    except Exception as exc:  # serial.SerialException and friends
        logger.debug("multibus: could not probe %s: %s", port, exc)
        return []
    finally:
        try:
            handler.closePort()
        except Exception:
            pass
        # The same pause the hand takes after closing a port: the bus client
        # reopens this port right after, and a USB serial port needs a moment.
        time.sleep(MOTOR_PORT_CLOSE_SETTLE_S)
    return found


def resolve_bus_ports(
    spec: MultiBusSpec,
    baudrate: int,
    ping: Optional[Callable[[str, int, Sequence[int]], List[int]]] = None,
    candidates: Optional[Callable[[], List[str]]] = None,
) -> Dict[str, str]:
    """Work out the port of every bus in ``spec``; returns ``{bus name: port}``.

    A bus with ``port:`` written in buses.yaml keeps it. Every other bus is
    found by pinging: each USB serial port is asked which of the still
    unplaced motor IDs it carries, and the answer names the bus. COM numbers
    move when a cable changes socket, motor IDs do not, so the IDs decide.

    Refuses (raises) rather than guesses when what is plugged in does not
    match the table: a port carrying motors of two buses, two ports claiming
    one bus, or a bus that no port answers for.
    """
    ports: Dict[str, str] = {b.name: b.port for b in spec.buses if b.port}
    pending = [b for b in spec.buses if not b.port]
    if not pending:
        return ports

    ping = ping or _ping_ids
    taken = {p.upper() for p in ports.values()}
    listed = (candidates or _candidate_ports)()
    to_probe = [p for p in listed if p.upper() not in taken]
    wanted = [mid for bus in pending for mid in bus.motor_ids]
    owner = {mid: bus.name for bus in pending for mid in bus.motor_ids}

    seen: Dict[str, List[int]] = {}
    for port in to_probe:
        answered = ping(port, baudrate, wanted)
        seen[port] = answered
        if not answered:
            continue
        names = sorted({owner[mid] for mid in answered})
        if len(names) > 1:
            raise MultiBusConfigError(
                f"{port} answers for motor IDs {answered}, which {spec.path} "
                f"splits over buses {names}. Check the wiring or the table.")
        name = names[0]
        if name in ports:
            raise MultiBusConfigError(
                f"bus '{name}' answers on both {ports[name]} and {port}. "
                f"Two boards are wired to the same finger, or the table is wrong.")
        ports[name] = port
        logger.info("multibus: bus '%s' is on %s (motor IDs %s answered)",
                    name, port, answered)

    missing = [b for b in pending if b.name not in ports]
    if missing:
        detail = "; ".join(
            f"'{b.name}' (motor IDs {list(b.motor_ids)})" for b in missing)
        probed = ", ".join(
            f"{p}: {seen[p] or 'no answer'}" for p in to_probe) or "none found"
        raise MultiBusConfigError(
            f"no port answered for bus {detail} at {baudrate} baud. "
            f"Ports probed -> {probed}. Check power, the USB cable, that no "
            f"other program has the port open, and 'baudrate' in {spec.path}; "
            f"or write the port into {spec.path}.")
    return ports


# ------------------------------------------------------------------------------
# The combined client
# ------------------------------------------------------------------------------

class _Bus:
    """One live bus: its name, port and the single-bus client driving it."""

    def __init__(self, name: str, port: str, client: MotorClient):
        self.name = name
        self.port = port
        self.client = client
        self.motor_ids = [int(m) for m in client.motor_ids]


class MultiBusClient(MotorClient):
    """N single-bus clients behind the interface of one.

    Never instantiated directly: :func:`multibus_class_for` builds a subclass
    that also inherits from the single-bus client class of the motor family,
    so every family constant (current scales, supported modes, error bits...)
    is the family's own. Every method that touches the bus is defined here and
    routed; one inherited from the single-bus client would look for a serial
    port this object does not have and fail loudly (see ``__getattr__``).

    Call types and what happens to them:

    * read everything     -> every bus is read, answers are put back in the
                             order of ``motor_ids``
    * write to listed IDs -> the list is split per bus
    * one motor           -> sent to the bus that motor is on
    * whole-client state  -> all buses; "ok" means every bus is ok

    Motor IDs that no bus carries behave like motors that are not plugged in.
    """

    def __init__(
        self,
        motor_ids: Sequence[int],
        spec: MultiBusSpec,
        baudrate: int,
        client_factory: Callable[[Sequence[int], str, int], MotorClient],
        port_resolver: Optional[Callable[[MultiBusSpec, int], Dict[str, str]]] = None,
    ):
        """
        Args:
            motor_ids: Every motor ID of the hand, in config.yaml order.
                Reads come back in this order.
            spec: The parsed buses.yaml.
            baudrate: Baud rate shared by all buses.
            client_factory: ``(motor_ids, port, baudrate) -> MotorClient`` for
                one bus. Not connected yet.
            port_resolver: ``(spec, baudrate) -> {bus name: port}``; defaults
                to :func:`resolve_bus_ports`.
        """
        self.motor_ids = [int(m) for m in motor_ids]
        self.baudrate = int(baudrate)
        self.port_name = MULTIBUS_PORT
        self._spec = spec
        self._client_factory = client_factory
        self._port_resolver = port_resolver or resolve_bus_ports
        self._parallel = bool(spec.parallel)
        self._buses: List[_Bus] = []
        self._bus_of: Dict[int, _Bus] = {}
        self._index = {mid: i for i, mid in enumerate(self.motor_ids)}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._last_read_ok = True
        size = len(self.motor_ids)
        self._pos = np.zeros(size, dtype=np.float32)
        self._vel = np.zeros(size, dtype=np.float32)
        self._cur = np.zeros(size, dtype=np.float32)
        self._temp = np.zeros(size, dtype=np.float32)

        unknown = [m for m in spec.routed_ids if m not in self._index]
        if unknown:
            raise MultiBusConfigError(
                f"{spec.path}: motor IDs {unknown} are not in config.yaml "
                f"motor_ids {self.motor_ids}.")
        unrouted = [m for m in self.motor_ids if m not in set(spec.routed_ids)]
        if unrouted:
            logger.warning(
                "multibus: motor IDs %s are on no bus in %s; they are treated "
                "as not plugged in", unrouted, spec.path)

    def __getattr__(self, name: str):
        # Reached only when normal lookup fails, i.e. something asked for
        # state a single-bus client keeps (port_handler, _bus_lock, ...).
        raise AttributeError(
            f"{type(self).__name__} has no '{name}': it combines several buses "
            f"and has no serial port of its own. A method that needs '{name}' "
            f"is not routed in multibus_client.py.")

    # ----- helpers ---------------------------------------------------------

    def _each(self, fn: Callable[[_Bus], Any],
              buses: Optional[Sequence[_Bus]] = None) -> List[Any]:
        """Run ``fn`` on every bus (or on ``buses``); results in bus order.

        One after another by default. With ``parallel: true`` each bus runs in
        its own thread, so the time is that of the slowest bus instead of the
        sum. Every bus is always attempted; the first error is raised after.
        """
        buses = list(self._buses if buses is None else buses)
        results: List[Any] = [None] * len(buses)
        errors: List[BaseException] = []
        if self._parallel and len(buses) > 1 and self._executor is not None:
            futures = [self._executor.submit(fn, bus) for bus in buses]
            for i, future in enumerate(futures):
                try:
                    results[i] = future.result()
                except Exception as exc:
                    errors.append(exc)
        else:
            for i, bus in enumerate(buses):
                try:
                    results[i] = fn(bus)
                except Exception as exc:
                    errors.append(exc)
        if errors:
            raise errors[0]
        return results

    def _split(self, motor_ids: Sequence[int],
               values: Optional[Sequence[Any]] = None
               ) -> List[Tuple[_Bus, List[int], Optional[List[Any]]]]:
        """Group ``motor_ids`` (and matching ``values``) by bus, order kept.

        IDs that are on no bus are dropped, the way a single-bus client skips
        motors that never answered.
        """
        if values is not None and len(values) != len(motor_ids):
            raise ValueError("motor_ids and values must have the same length")
        groups: Dict[int, Tuple[_Bus, List[int], List[Any]]] = {}
        for i, motor_id in enumerate(motor_ids):
            bus = self._bus_of.get(int(motor_id))
            if bus is None:
                continue
            group = groups.setdefault(id(bus), (bus, [], []))
            group[1].append(int(motor_id))
            if values is not None:
                group[2].append(values[i])
        return [(bus, ids, vals if values is not None else None)
                for bus, ids, vals in groups.values()]

    def _fan_ids(self, motor_ids: Sequence[int],
                 fn: Callable[[MotorClient, List[int]], Any]) -> List[Any]:
        """Call ``fn(client, ids_on_that_bus)`` per bus; results in bus order."""
        parts = {id(bus): ids for bus, ids, _ in self._split(motor_ids)}
        buses = [bus for bus in self._buses if id(bus) in parts]
        return self._each(lambda bus: fn(bus.client, parts[id(bus)]), buses)

    def _fan_values(self, motor_ids: Sequence[int], values: Sequence[Any],
                    fn: Callable[[MotorClient, List[int], np.ndarray], Any]) -> List[Any]:
        """Like :meth:`_fan_ids`, with each bus's share of ``values``."""
        parts = {id(bus): (ids, np.asarray(vals))
                 for bus, ids, vals in self._split(motor_ids, values)}
        buses = [bus for bus in self._buses if id(bus) in parts]
        return self._each(lambda bus: fn(bus.client, *parts[id(bus)]), buses)

    def _merge_dicts(self, parts: Sequence[Optional[dict]]) -> dict:
        merged: dict = {}
        for part in parts:
            merged.update(part or {})
        return merged

    def _client_of(self, motor_id: int) -> Optional[MotorClient]:
        bus = self._bus_of.get(int(motor_id))
        return bus.client if bus is not None else None

    # ----- lifecycle -------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        # "Any", not "all": after one bus drops, the hand must still see a
        # live client so that disconnect() runs and closes the others.
        return any(bus.client.is_connected for bus in self._buses)

    def connect(self) -> None:
        """Find every bus's port, then open them all. All or nothing."""
        if self.is_connected:
            raise RuntimeError("Client is already connected.")
        ports = self._port_resolver(self._spec, self.baudrate)
        buses: List[_Bus] = []
        try:
            for spec in self._spec.buses:
                port = ports[spec.name]
                client = self._client_factory(list(spec.motor_ids), port, self.baudrate)
                bus = _Bus(spec.name, port, client)
                buses.append(bus)
                try:
                    client.connect()
                except Exception as exc:
                    raise ConnectionError(
                        f"bus '{spec.name}' on {port}: {exc}") from exc
                answered = list(client.responding_motor_ids())
                if not answered:
                    raise ConnectionError(
                        f"bus '{spec.name}' on {port}: none of motor IDs "
                        f"{list(spec.motor_ids)} answered at {self.baudrate} baud "
                        f"(check power, wiring and the baud rate)")
                missing = [m for m in spec.motor_ids if m not in answered]
                if missing:
                    logger.warning(
                        "multibus: bus '%s' on %s: motor IDs %s did not answer",
                        spec.name, port, missing)
        except Exception:
            for bus in buses:
                try:
                    bus.client.disconnect()
                except Exception:
                    pass
            raise
        self._buses = buses
        self._bus_of = {mid: bus for bus in buses for mid in bus.motor_ids}
        self.port_name = "{}({})".format(
            MULTIBUS_PORT, ", ".join(f"{b.name}={b.port}" for b in buses))
        if self._parallel and len(buses) > 1:
            self._executor = ThreadPoolExecutor(
                max_workers=len(buses), thread_name_prefix="multibus")
        # Printed, not logged: most scripts never raise the log level, and
        # which port became which finger is the first thing to check.
        print("multibus: " + ", ".join(
            f"{b.name}={b.port} {list(b.client.responding_motor_ids())}"
            for b in buses) + (" (parallel)" if self._executor else ""))

    def _close(self, how: str) -> None:
        buses = [bus for bus in self.__dict__.get("_buses", [])]
        error: Optional[BaseException] = None
        for bus in buses:
            try:
                closer = getattr(bus.client, how, None) or bus.client.disconnect
                closer()
            except Exception as exc:  # keep closing the others
                error = error or exc
        executor = self.__dict__.get("_executor")
        if executor is not None:
            executor.shutdown(wait=False)
            self._executor = None
        if error is not None:
            raise error

    def disconnect(self) -> None:
        """Torque off and close every bus; a failing bus does not stop the rest."""
        self._close("disconnect")

    def disconnect_fixed_lock_order(self) -> None:
        self._close("disconnect_fixed_lock_order")

    # ----- which motors are there -----------------------------------------

    def responding_motor_ids(self) -> List[int]:
        answered = set()
        for bus in self._buses:
            answered.update(int(m) for m in bus.client.responding_motor_ids())
        return [m for m in self.motor_ids if m in answered]

    def absent_motor_ids(self) -> List[int]:
        answered = set(self.responding_motor_ids())
        return [m for m in self.motor_ids if m not in answered]

    def motors_unable_to_move(self) -> "set[int]":
        unable: set = set()
        for bus in self._buses:
            unable |= set(bus.client.motors_unable_to_move())
        return unable

    def take_hardware_alerts(self) -> "dict[int, int]":
        return self._merge_dicts([bus.client.take_hardware_alerts()
                                  for bus in self._buses])

    def transport_baud_rates(self) -> "tuple[int, ...] | None":
        common: Optional[set] = None
        for bus in self._buses:
            rates = bus.client.transport_baud_rates()
            if rates is None:
                continue
            common = set(rates) if common is None else common & set(rates)
        return None if common is None else tuple(sorted(common, reverse=True))

    # ----- reads of every motor -------------------------------------------

    def _scatter(self, target: np.ndarray, bus: _Bus, values: Sequence[float]) -> None:
        for motor_id, value in zip(bus.motor_ids, values):
            target[self._index[motor_id]] = value

    def read_position_velocity_current(self) -> MotorRead:
        def read(bus: _Bus):
            # The freshness flag describes the read just made on that bus, so
            # it is taken in the same step, before anything else can read.
            return bus.client.read_position_velocity_current(), bool(bus.client.last_read_ok)

        ok = bool(self._buses)
        try:
            results = self._each(read)
        except Exception:
            self._last_read_ok = False
            raise
        for bus, (snapshot, fresh) in zip(self._buses, results):
            ok = ok and fresh
            self._scatter(self._pos, bus, snapshot.position)
            self._scatter(self._vel, bus, snapshot.velocity)
            self._scatter(self._cur, bus, snapshot.current)
        self._last_read_ok = ok
        return MotorRead(position=self._pos.copy(), velocity=self._vel.copy(),
                         current=self._cur.copy())

    @property
    def last_read_ok(self) -> bool:
        """False as soon as one bus failed its share of the last full read."""
        return self._last_read_ok

    def read_temperature(self) -> np.ndarray:
        results = self._each(lambda bus: bus.client.read_temperature())
        for bus, values in zip(self._buses, results):
            self._scatter(self._temp, bus, values)
        return self._temp.copy()

    def read_current_limits(self) -> "dict[int, float | None]":
        merged = self._merge_dicts(
            self._each(lambda bus: bus.client.read_current_limits()))
        return {m: merged.get(m) for m in self.motor_ids}

    def read_temperature_limits(self) -> "dict[int, float | None]":
        return self._merge_dicts(
            self._each(lambda bus: bus.client.read_temperature_limits()))

    def read_stop_mask(self) -> "dict[int, int | None]":
        return self._merge_dicts(
            self._each(lambda bus: bus.client.read_stop_mask()))

    # ----- reads and writes of listed motors ------------------------------

    def set_torque_enabled(self, motor_ids: Sequence[int], enabled: bool,
                           *args, **kwargs) -> List[int]:
        failed: List[int] = []
        for part in self._fan_ids(
                motor_ids,
                lambda c, ids: c.set_torque_enabled(ids, enabled, *args, **kwargs)):
            failed.extend(part or [])
        return failed

    def set_operating_mode(self, motor_ids: Sequence[int], mode: int) -> None:
        self._fan_ids(motor_ids, lambda c, ids: c.set_operating_mode(ids, mode))

    def write_pwm_fraction(self, motor_ids: Sequence[int], fraction: float) -> None:
        self._fan_ids(motor_ids, lambda c, ids: c.write_pwm_fraction(ids, fraction))

    def write_desired_pos(self, motor_ids: Sequence[int], positions: np.ndarray) -> None:
        assert len(motor_ids) == len(positions)
        self._fan_values(motor_ids, positions,
                         lambda c, ids, vals: c.write_desired_pos(ids, vals))

    def write_desired_current(self, motor_ids: Sequence[int], current: np.ndarray) -> None:
        if len(motor_ids) != len(current):
            raise ValueError("motor_ids and currents must have the same length")
        self._fan_values(motor_ids, current,
                         lambda c, ids, vals: c.write_desired_current(ids, vals))

    def read_goal_currents(
        self, motor_ids: "Sequence[int] | None" = None
    ) -> "dict[int, float | None]":
        requested = list(self.motor_ids if motor_ids is None else motor_ids)
        merged = self._merge_dicts(
            self._fan_ids(requested, lambda c, ids: c.read_goal_currents(ids)))
        return {int(m): merged.get(int(m)) for m in requested}

    def read_hardware_errors(self, motor_ids: Sequence[int]) -> "dict[int, int | None]":
        merged = self._merge_dicts(
            self._fan_ids(motor_ids, lambda c, ids: c.read_hardware_errors(ids)))
        return {int(m): merged.get(int(m)) for m in motor_ids}

    def read_servo_gains(self, motor_ids: Sequence[int]) -> dict:
        merged = self._merge_dicts(
            self._fan_ids(motor_ids, lambda c, ids: c.read_servo_gains(ids)))
        return {int(m): merged.get(int(m)) for m in motor_ids}

    def read_servo_profile(self, motor_ids: Sequence[int]) -> dict:
        merged = self._merge_dicts(
            self._fan_ids(motor_ids, lambda c, ids: c.read_servo_profile(ids)))
        return {int(m): merged.get(int(m)) for m in motor_ids}

    def read_profile_limits(self, motor_ids: Sequence[int]) -> dict:
        merged = self._merge_dicts(
            self._fan_ids(motor_ids, lambda c, ids: c.read_profile_limits(ids)))
        unrouted = [int(m) for m in motor_ids if int(m) not in merged]
        if unrouted:
            # No bus to ask: fall back to the family's datasheet figures.
            merged.update(MotorClient.read_profile_limits(self, unrouted))
        return {int(m): merged[int(m)] for m in motor_ids}

    def write_servo_gains(self, gains: dict) -> None:
        ids = list(gains)
        self._fan_ids(ids, lambda c, part: c.write_servo_gains(
            {m: gains[m] for m in part}))

    def write_servo_profile(self, profiles: dict) -> None:
        ids = list(profiles)
        self._fan_ids(ids, lambda c, part: c.write_servo_profile(
            {m: profiles[m] for m in part}))

    def check_overload_and_reboot(self, motor_ids: Sequence[int]) -> list:
        rebooted: list = []
        for part in self._fan_ids(
                motor_ids, lambda c, ids: c.check_overload_and_reboot(ids)):
            rebooted.extend(part or [])
        return rebooted

    def write_byte(self, motor_ids: Sequence[int], value: int, address: int) -> List[int]:
        failed: List[int] = []
        for part in self._fan_ids(
                motor_ids, lambda c, ids: c.write_byte(ids, value, address)):
            failed.extend(part or [])
        return failed

    def sync_write(self, motor_ids: Sequence[int], values, address: int, size: int) -> None:
        self._fan_values(motor_ids, values,
                         lambda c, ids, vals: c.sync_write(ids, vals, address, size))

    def wait_for_motion_complete(self, timeout: float = 5.0, **kwargs) -> None:
        """Wait until the motors on every bus have settled, or raise.

        ``timeout`` is for the whole hand: buses waited on one after another
        share one deadline.
        """
        self.check_connected()
        deadline = time.time() + timeout
        problems: List[str] = []

        def wait(bus: _Bus) -> None:
            remaining = timeout if self._executor else max(deadline - time.time(), 0.0)
            try:
                bus.client.wait_for_motion_complete(timeout=remaining, **kwargs)
            except MotionTimeoutError as exc:
                problems.append(f"bus '{bus.name}': {exc}")

        self._each(wait)
        if problems:
            raise MotionTimeoutError("; ".join(problems))

    # ----- one motor -------------------------------------------------------

    def read_hardware_error(self, motor_id: int) -> "int | None":
        client = self._client_of(motor_id)
        return None if client is None else client.read_hardware_error(motor_id)

    def _current_ceiling_ma(self, motor_id: int) -> "float | None":
        client = self._client_of(motor_id)
        return None if client is None else client._current_ceiling_ma(motor_id)

    def hold_motor_off(self, motor_id: int) -> bool:
        client = self._client_of(motor_id)
        return False if client is None else client.hold_motor_off(motor_id)

    def release_motor(self, motor_id: int) -> bool:
        client = self._client_of(motor_id)
        return False if client is None else client.release_motor(motor_id)

    def reboot_motor(self, motor_id: int) -> None:
        client = self._client_of(motor_id)
        if client is None:
            raise ValueError(f"motor ID {motor_id} is on no bus; cannot reboot it")
        client.reboot_motor(motor_id)

    def read_config_register(self, motor_id: int, key: str) -> "int | None":
        client = self._client_of(motor_id)
        return None if client is None else client.read_config_register(motor_id, key)

    def write_config_register(self, motor_id: int, key: str, value: int) -> "int | None":
        client = self._client_of(motor_id)
        return None if client is None else client.write_config_register(motor_id, key, value)

    @property
    def requires_offset_calibration(self) -> bool:
        return any(bus.client.requires_offset_calibration for bus in self._buses)

    def calibrate_offset(self, motor_id: int, upper: bool = True) -> bool:
        client = self._client_of(motor_id)
        return False if client is None else client.calibrate_offset(motor_id, upper)

    # ----- not available on the combined client ---------------------------

    def _single_bus_only(self, what: str):
        raise NotImplementedError(
            f"{what} works on one bus at a time. Put that bus's real port in "
            f"config.yaml (instead of '{MULTIBUS_PORT}') to do it.")

    def scan_for_motors(self, port: str, id_range: tuple, baud_rates=None) -> list:
        self._single_bus_only("Scanning for motors")

    def change_motor_id(self, current_id: int, new_id: int) -> bool:
        self._single_bus_only("Changing a motor ID")

    def change_motor_baudrate(self, motor_id: int, new_baud_rate: int) -> bool:
        self._single_bus_only("Changing a motor baud rate")

    def change_return_delay_time(self, motor_id: int, delay_us: int) -> bool:
        self._single_bus_only("Changing the return delay time")


# ------------------------------------------------------------------------------
# Glue used by hardware_hand.py
# ------------------------------------------------------------------------------

_CLASS_CACHE: Dict[type, type] = {}


def multibus_class_for(bus_client_cls: type) -> type:
    """The combined-client class for buses driven by ``bus_client_cls``.

    Inherits from both, :class:`MultiBusClient` first: routed methods come
    from it, family constants and classmethods from ``bus_client_cls``.
    """
    cls = _CLASS_CACHE.get(bus_client_cls)
    if cls is None:
        cls = type(f"MultiBus{bus_client_cls.__name__}",
                   (MultiBusClient, bus_client_cls), {})
        _CLASS_CACHE[bus_client_cls] = cls
    return cls


def _spec_for(config) -> MultiBusSpec:
    return load_buses(buses_path_for(config.config_path))


def resolve_multibus_driver(config, default_motor_type: str = "dynamixel"
                            ) -> "tuple[str, int]":
    """``(motor_type, baudrate)`` for a multibus hand, without touching a port.

    Stands in for the stock connect-time probe, which pings only the first
    and last motor ID of the hand on one port: a finger bus carrying neither
    would be reported as "no motor responded".

    buses.yaml wins over config.yaml for both values.
    """
    spec = _spec_for(config)
    motor_type = spec.motor_type or config.motor_type or default_motor_type
    baudrate = spec.baudrate or config.baudrate
    if not baudrate:
        raise MultiBusConfigError(
            f"no baud rate for the multibus hand: add 'baudrate: 1000000' "
            f"(or the rate your boards use) to {spec.path}.")
    return motor_type, int(baudrate)


def create_multibus_client(config, client_factory=None) -> MultiBusClient:
    """Build (but do not connect) the combined client for ``config``.

    ``config.motor_type`` and ``config.baudrate`` are expected to be resolved
    already, which :func:`resolve_multibus_driver` does during connect.
    """
    from .motor_factory import motor_client_class

    spec = _spec_for(config)
    motor_type, baudrate = resolve_multibus_driver(config)
    bus_cls = motor_client_class(motor_type)
    if client_factory is None:
        client_factory = bus_cls
    return multibus_class_for(bus_cls)(
        config.motor_ids, spec, baudrate, client_factory)
