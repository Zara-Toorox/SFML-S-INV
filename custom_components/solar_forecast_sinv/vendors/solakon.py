# ******************************************************************************
# @copyright (C) 2026 Zara-Toorox - Solar Forecast S-INV
# * This program is protected by a Proprietary Non-Commercial License.
# 1. Personal and Educational use only.
# 2. COMMERCIAL USE AND AI TRAINING ARE STRICTLY PROHIBITED.
# 3. Clear attribution to "Zara-Toorox" is required.
# * Full license terms: https://www.solarforecastml.com/license
# ******************************************************************************

"""Solakon ONE adapter for the S-INV contract (Modbus TCP, read only). @zara

Register map: Solakon ONE Modbus Protokoll v.02/26. Modbus TCP is on by default as
soon as the device is in the network (LAN before WLAN), port 502, unit 1. All
values are holding registers (function 0x03) at the documented address; 32-bit
values are high word first. "Faktor" is the divisor of the raw value.

Documented signs used directly:
- [Meter collection] active power 39168: positive = feeding the grid ->
  contract ``power_grid`` (positive import) = -39168
- [Energy storage module 1] charge/discharge power 39162: positive = charging
  -> contract ``power_battery``
Grid roles need a meter or CT connected to the Solakon ONE (38801 = 1). The house
consumption is derived: inverter active power minus the meter's feed-in. The
energy counters 39621/39625 ("output"/"enter") are the device's own AC output and
input, not the grid point, and stay vendor values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Any

from ..contract import indexed_role

VENDOR = "solakon"
NAME = "Solakon"
CONNECTION_LOCAL = "local_modbus_solakon"
DEFAULT_SCAN_SECONDS = 10
MIN_SCAN_SECONDS = 5
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
REQUEST_GAP_SECONDS = 0.1
IDENTITY_BLOCKS: tuple[tuple[int, int], ...] = ((30000, 32), (39050, 3))
INPUT_BLOCKS: tuple[tuple[int, int], ...] = (
    (39118, 24),  # PV total, grid voltage, inverter power, frequency, temperature
    (39149, 21),  # yield, battery power, meter power
    (39225, 2),  # load power
    (39601, 28),  # energy counters
    (37002, 1),  # BMS1 online
    (37609, 27),  # BMS1 values
    (38801, 1),  # meter 1 / CT 1 connected
)
OPTIONAL_BLOCKS: tuple[tuple[int, int], ...] = (
    (37700, 1),  # BMS2 online
    (38307, 27),  # BMS2 values
)
MPPT_BASE = 39327  # voltage, current, power (I32) per MPPT, 4 registers each
MAX_MPPTS = 4
ONLINE = 1


@dataclass(frozen=True)
class VendorSpec:
    """Display and unit definition of a value without a contract role. @zara"""

    unit: str | None
    device_class: str | None
    state_class: str | None
    name_en: str
    name_de: str


VENDOR_SPECS: dict[str, VendorSpec] = {
    "load_power": VendorSpec(
        "W", "power", "measurement", "Load power (device)", "Lastleistung (Gerät)"
    ),
    "ac_output_energy_total": VendorSpec(
        "kWh", "energy", "total_increasing", "AC output total", "AC-Ausgabe gesamt"
    ),
    "ac_input_energy_total": VendorSpec(
        "kWh", "energy", "total_increasing", "AC input total", "AC-Aufnahme gesamt"
    ),
}


@dataclass
class SolakonDevice:
    """One Solakon ONE with its battery. @zara"""

    serial: str
    kind: str
    name: str
    manufacturer: str
    model: str
    roles: dict[str, Any] = field(default_factory=dict)
    vendor: dict[str, Any] = field(default_factory=dict)
    derived: set[str] = field(default_factory=set)


def u16(regs: dict[int, int], address: int) -> int | None:
    """Unsigned 16-bit register. @zara"""
    return regs.get(address)


def s16(regs: dict[int, int], address: int) -> int | None:
    """Signed 16-bit register. @zara"""
    value = regs.get(address)
    return None if value is None else struct.unpack(">h", struct.pack(">H", value))[0]


def u32(regs: dict[int, int], address: int) -> int | None:
    """Unsigned 32-bit value, high word first. @zara"""
    high, low = regs.get(address), regs.get(address + 1)
    if high is None or low is None:
        return None
    return (high << 16) | low


def s32(regs: dict[int, int], address: int) -> int | None:
    """Signed 32-bit value, high word first. @zara"""
    value = u32(regs, address)
    return None if value is None else struct.unpack(">i", struct.pack(">I", value))[0]


def text(regs: dict[int, int], address: int, count: int) -> str:
    """ASCII string, two characters per register, zero padded. @zara"""
    data = b"".join(
        struct.pack(">H", regs[address + offset])
        for offset in range(count)
        if address + offset in regs
    )
    return data.split(b"\x00", 1)[0].decode("ascii", "ignore").strip()


def mppt_count(regs: dict[int, int]) -> int:
    """Return the number of MPPTs the device reports, at most four. @zara"""
    return max(0, min(u16(regs, 39052) or 0, MAX_MPPTS))


def mppt_blocks(count: int) -> tuple[tuple[int, int], ...]:
    """Register block of the MPPT values. @zara"""
    return ((MPPT_BASE, 4 * count),) if count else ()


def identity(regs: dict[int, int]) -> dict[str, str] | None:
    """Return serial and model from the identity registers, or None. @zara"""
    # the serial ends up in unique ids and logs: keep plain ASCII letters and digits
    serial = "".join(c for c in text(regs, 30016, 16) if c.isascii() and c.isalnum())
    if not serial:
        return None
    model = "".join(c for c in text(regs, 30000, 16) if c.isprintable())
    model = (
        model if model.upper().startswith(NAME.upper()) else f"{NAME} {model or 'ONE'}"
    )
    return {"serial": serial, "name": model, "model": model}


def _set(
    device: SolakonDevice, role: str, value: float | None, digits: int = 1
) -> None:
    if value is not None:
        device.roles[role] = round(value, digits)


def _scaled(value: int | None, divisor: float) -> float | None:
    return None if value is None else value / divisor


def _battery(
    regs: dict[int, int], base: int
) -> tuple[float, float, float | None] | None:
    """(capacity kWh, SoC %, SoH %) of one BMS, or None when it is empty. @zara"""
    design = u16(regs, base + 26)  # Wh, factor 0.1
    soc = u16(regs, base + 3)
    if not design or soc is None:
        return None
    soh = u16(regs, base + 15)
    return design * 10 / 1000, float(soc), float(soh) if soh else None


def build_devices(regs: dict[int, int]) -> dict[str, SolakonDevice]:
    """Parse identity and running registers into the Solakon ONE device. @zara"""
    ident = identity(regs)
    if ident is None:
        return {}
    device = SolakonDevice(
        serial=ident["serial"],
        kind="inverter",
        name=ident["name"],
        manufacturer=NAME,
        model=ident["model"],
    )
    for index in range(1, mppt_count(regs) + 1):
        base = MPPT_BASE + 4 * (index - 1)
        _set(
            device,
            indexed_role("voltage_solar_mppt", index),
            _scaled(s16(regs, base), 10),
        )
        _set(
            device,
            indexed_role("current_solar_mppt", index),
            _scaled(s16(regs, base + 1), 100),
            2,
        )
        _set(device, indexed_role("power_solar_mppt", index), s32(regs, base + 2), 0)
    _set(device, "power_solar", s32(regs, 39118), 0)  # kW x1000 = W
    active = s32(regs, 39134)
    _set(device, "power_inverter_ac_output", active, 0)
    _set(device, "voltage_grid", _scaled(s16(regs, 39123), 10))
    _set(device, "frequency_grid", _scaled(s16(regs, 39139), 100), 2)
    _set(device, "temperature_inverter", _scaled(s16(regs, 39141), 10))
    _set(device, "energy_solar_total", _scaled(u32(regs, 39601), 100), 2)
    _set(device, "energy_solar_today", _scaled(u32(regs, 39603), 100), 2)

    meter = s32(regs, 39168)
    if meter is not None and u16(regs, 38801) == ONLINE:
        grid = -meter
        _set(device, "power_grid", grid, 0)
        _set(device, "power_grid_import", max(0, grid), 0)
        _set(device, "power_grid_export", max(0, -grid), 0)
        _set(device, "energy_grid_export_total", _scaled(u32(regs, 39613), 100), 2)
        _set(device, "energy_grid_import_total", _scaled(u32(regs, 39617), 100), 2)
        if active is not None:
            _set(device, "power_house", max(0, active - meter), 0)
            device.derived.add("power_house")

    packs = [
        pack
        for online, base in ((37002, 37609), (37700, 38307))
        if u16(regs, online) == ONLINE and (pack := _battery(regs, base)) is not None
    ]
    if packs:
        capacity = sum(pack[0] for pack in packs)
        _set(device, "capacity_battery", capacity, 2)
        _set(
            device,
            "battery_soc",
            sum(pack[0] * pack[1] for pack in packs) / capacity,
            1,
        )
        health = [
            pack[2] for pack in packs if pack[2] is not None and 0 < pack[2] <= 100
        ]
        if len(health) == len(packs):
            _set(device, "battery_soh", min(health), 0)
        # highest cell temperature of BMS1
        _set(device, "temperature_battery", _scaled(s16(regs, 37617), 10))
        battery = s32(regs, 39162)
        if battery is not None:
            _set(device, "power_battery", battery, 0)
            _set(device, "power_battery_charge", max(0, battery), 0)
            _set(device, "power_battery_discharge", max(0, -battery), 0)
        _set(device, "energy_battery_charge_total", _scaled(u32(regs, 39605), 100), 2)
        _set(
            device,
            "energy_battery_discharge_total",
            _scaled(u32(regs, 39609), 100),
            2,
        )

    load = s32(regs, 39225)
    if load is not None:
        device.vendor["load_power"] = load
    for key, address in (
        ("ac_output_energy_total", 39621),
        ("ac_input_energy_total", 39625),
    ):
        value = _scaled(u32(regs, address), 100)
        if value is not None:
            device.vendor[key] = round(value, 2)
    return {device.serial: device}
