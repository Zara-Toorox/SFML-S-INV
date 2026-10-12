# ******************************************************************************
# @copyright (C) 2026 Zara-Toorox - Solar Forecast S-INV
# * This program is protected by a Proprietary Non-Commercial License.
# 1. Personal and Educational use only.
# 2. COMMERCIAL USE AND AI TRAINING ARE STRICTLY PROHIBITED.
# 3. Clear attribution to "Zara-Toorox" is required.
# * Full license terms: https://www.solarforecastml.com/license
# ******************************************************************************

"""Fronius adapter for the S-INV contract (local Solar API v1). @zara

Turns Solar API v1 responses into S-INV devices with contract roles and vendor
values. No Home Assistant imports; the coordinator fetches, this module parses.

Verified on a Symo GEN24 10.0 Plus (firmware 1.41.11-1) with BYD Battery-Box
Premium HV and Smartmeter IP at the grid point (2026-10-11):
- ``Site.P_Grid`` and meter ``PowerReal_P_Sum``: positive while importing
- ``Site.P_Akku``: negative while charging -> contract ``power_battery`` = -P_Akku
- ``Site.P_Load``: negative for consumption -> contract ``power_house`` = -P_Load
- ``UDC``/``IDC``, ``UDC_2``/``IDC_2``: per-MPPT DC voltage and current
- energies in Wh -> converted to kWh
- ``TOTAL_ENERGY``/``E_Total`` is the inverter AC energy (includes battery
  discharge on hybrids), so it is not ``energy_solar_total``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..contract import indexed_role

VENDOR = "fronius"
NAME = "Fronius"
CONNECTION_LOCAL = "local_solar_api"
DEFAULT_SCAN_SECONDS = 10

API_VERSION_PATH = "/solar_api/GetAPIVersion.cgi"
REQUESTS: dict[str, str] = {
    "powerflow": "GetPowerFlowRealtimeData.fcgi",
    "inverter": "GetInverterRealtimeData.cgi?Scope=Device&DeviceId={device_id}&DataCollection=CommonInverterData",
    "inverter_info": "GetInverterInfo.cgi",
    "meter": "GetMeterRealtimeData.cgi?Scope=System",
    "storage": "GetStorageRealtimeData.cgi?Scope=System",
}
MAX_MPPT = 4
METER_LOCATION_GRID = 0.0


@dataclass(frozen=True)
class VendorSpec:
    """Display and unit definition of a Fronius value without a contract role. @zara"""

    unit: str | None
    device_class: str | None
    state_class: str | None
    name_en: str
    name_de: str


VENDOR_SPECS: dict[str, VendorSpec] = {
    "inverter_energy_total": VendorSpec(
        "kWh",
        "energy",
        "total_increasing",
        "Inverter AC energy total",
        "Wechselrichter AC-Energie gesamt",
    ),
    "inverter_state": VendorSpec(
        None, None, None, "Inverter state", "Wechselrichter-Zustand"
    ),
    "inverter_error_code": VendorSpec(
        None, None, None, "Inverter error code", "Wechselrichter-Fehlercode"
    ),
    "battery_mode": VendorSpec(None, None, None, "Battery mode", "Akku-Modus"),
    "autonomy": VendorSpec("%", None, "measurement", "Autonomy", "Autarkie"),
    "self_consumption": VendorSpec(
        "%", None, "measurement", "Self consumption", "Eigenverbrauch"
    ),
    "battery_voltage_dc": VendorSpec(
        "V", "voltage", "measurement", "Battery DC voltage", "Akku DC-Spannung"
    ),
    "battery_current_dc": VendorSpec(
        "A", "current", "measurement", "Battery DC current", "Akku DC-Strom"
    ),
    "meter_voltage_l1": VendorSpec(
        "V", "voltage", "measurement", "Meter voltage L1", "Zähler Spannung L1"
    ),
    "meter_voltage_l2": VendorSpec(
        "V", "voltage", "measurement", "Meter voltage L2", "Zähler Spannung L2"
    ),
    "meter_voltage_l3": VendorSpec(
        "V", "voltage", "measurement", "Meter voltage L3", "Zähler Spannung L3"
    ),
    "meter_power_l1": VendorSpec(
        "W", "power", "measurement", "Meter power L1", "Zähler Leistung L1"
    ),
    "meter_power_l2": VendorSpec(
        "W", "power", "measurement", "Meter power L2", "Zähler Leistung L2"
    ),
    "meter_power_l3": VendorSpec(
        "W", "power", "measurement", "Meter power L3", "Zähler Leistung L3"
    ),
    "meter_frequency": VendorSpec(
        "Hz", "frequency", "measurement", "Meter frequency", "Zähler Frequenz"
    ),
}


@dataclass
class FroniusDevice:
    """One physical Fronius-side device with its contract and vendor values. @zara"""

    serial: str
    kind: str
    name: str
    manufacturer: str
    model: str
    roles: dict[str, Any] = field(default_factory=dict)
    vendor: dict[str, Any] = field(default_factory=dict)
    derived: set[str] = field(default_factory=set)


def _data(response: Any) -> dict[str, Any] | None:
    """Return ``Body.Data`` of a successful Solar API response. @zara"""
    if not isinstance(response, dict):
        return None
    status = ((response.get("Head") or {}).get("Status") or {}).get("Code")
    if status not in (0, None):
        return None
    data = (response.get("Body") or {}).get("Data")
    return data if isinstance(data, dict) else None


def _num(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("Value")
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _neg(value: float | None) -> float | None:
    return None if value is None else -value


def _kwh(value: float | None) -> float | None:
    return None if value is None else value / 1000.0


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _set(
    device: FroniusDevice, role: str, value: float | None, digits: int = 1
) -> None:
    if value is not None:
        device.roles[role] = _round(value, digits)


def _first_entry(data: dict[str, Any] | None) -> tuple[str, dict[str, Any]] | None:
    if not data:
        return None
    for key in sorted(data, key=str):
        if isinstance(data[key], dict):
            return str(key), data[key]
    return None


def inverter_identity(info_response: Any) -> dict[str, str] | None:
    """Return id, serial and name of the first inverter from GetInverterInfo. @zara"""
    entry = _first_entry(_data(info_response))
    if entry is None:
        return None
    device_id, info = entry
    serial = str(info.get("UniqueID") or "").strip()
    if not serial:
        return None
    return {
        "device_id": device_id,
        "serial": serial,
        "name": str(info.get("CustomName") or "").strip() or f"{NAME} {serial}",
        "dt": str(info.get("DT", "")),
    }


def build_devices(responses: dict[str, Any]) -> dict[str, FroniusDevice]:
    """Build inverter, meter and battery devices from one polling cycle. @zara"""
    devices: dict[str, FroniusDevice] = {}
    identity = inverter_identity(responses.get("inverter_info"))
    if identity is None:
        return devices
    flow = _data(responses.get("powerflow")) or {}
    site = flow.get("Site") if isinstance(flow.get("Site"), dict) else {}
    flow_inverters = (
        flow.get("Inverters") if isinstance(flow.get("Inverters"), dict) else {}
    )
    flow_inverter = flow_inverters.get(identity["device_id"]) or {}
    common = _data(responses.get("inverter")) or {}

    inverter = FroniusDevice(
        serial=identity["serial"],
        kind="inverter",
        name=identity["name"],
        manufacturer=NAME,
        model=f"Fronius inverter (DT {identity['dt']})"
        if identity["dt"]
        else "Fronius inverter",
    )
    _set(inverter, "power_solar", _num(site.get("P_PV")), 0)
    _set(inverter, "power_house", _neg(_num(site.get("P_Load"))), 0)
    _set(inverter, "power_inverter_ac_output", _num(common.get("PAC")), 0)
    _set(inverter, "voltage_grid", _num(common.get("UAC")), 1)
    _set(inverter, "frequency_grid", _num(common.get("FAC")), 2)
    for channel in range(1, MAX_MPPT + 1):
        suffix = "" if channel == 1 else f"_{channel}"
        voltage = _num(common.get(f"UDC{suffix}"))
        current = _num(common.get(f"IDC{suffix}"))
        if voltage is None or current is None:
            continue
        _set(inverter, indexed_role("voltage_solar_mppt", channel), voltage, 1)
        _set(inverter, indexed_role("current_solar_mppt", channel), current, 2)
        power_role = indexed_role("power_solar_mppt", channel)
        _set(inverter, power_role, voltage * current, 0)
        inverter.derived.add(power_role)
    total = _kwh(_num(common.get("TOTAL_ENERGY")))
    if total is None:
        total = _kwh(_num(flow_inverter.get("E_Total")))
    if total is not None:
        inverter.vendor["inverter_energy_total"] = round(total, 3)
    status = (
        common.get("DeviceStatus")
        if isinstance(common.get("DeviceStatus"), dict)
        else {}
    )
    if status.get("InverterState") is not None:
        inverter.vendor["inverter_state"] = str(status["InverterState"])
    if status.get("ErrorCode") is not None:
        inverter.vendor["inverter_error_code"] = status["ErrorCode"]
    if (autonomy := _num(site.get("rel_Autonomy"))) is not None:
        inverter.vendor["autonomy"] = round(autonomy, 1)
    if (self_use := _num(site.get("rel_SelfConsumption"))) is not None:
        inverter.vendor["self_consumption"] = round(self_use, 1)
    devices[inverter.serial] = inverter

    meter = _grid_meter(_data(responses.get("meter")))
    if meter is not None:
        devices[meter.serial] = meter
    elif (grid := _num(site.get("P_Grid"))) is not None:
        _grid_roles(inverter, grid)

    battery = _battery(_data(responses.get("storage")), site, flow_inverter)
    if battery is not None:
        devices[battery.serial] = battery
    return devices


def _grid_roles(device: FroniusDevice, grid: float) -> None:
    _set(device, "power_grid", grid, 0)
    _set(device, "power_grid_import", max(0.0, grid), 0)
    _set(device, "power_grid_export", max(0.0, -grid), 0)
    device.derived.update({"power_grid_import", "power_grid_export"})


def _grid_meter(data: dict[str, Any] | None) -> FroniusDevice | None:
    """First enabled meter at the grid point; load meters are not the grid. @zara"""
    for key in sorted(data or {}, key=str):
        meter = data[key]
        if not isinstance(meter, dict) or meter.get("Enable") == 0:
            continue
        if _num(meter.get("Meter_Location_Current")) != METER_LOCATION_GRID:
            continue
        details = meter.get("Details") if isinstance(meter.get("Details"), dict) else {}
        serial = str(details.get("Serial") or "").strip() or f"meter_{key}"
        device = FroniusDevice(
            serial=serial,
            kind="meter",
            name=str(details.get("Model") or "Fronius meter"),
            manufacturer=str(details.get("Manufacturer") or NAME),
            model=str(details.get("Model") or "Fronius meter"),
        )
        if (grid := _num(meter.get("PowerReal_P_Sum"))) is not None:
            _grid_roles(device, grid)
        _set(
            device,
            "energy_grid_import_total",
            _kwh(_num(meter.get("EnergyReal_WAC_Sum_Consumed"))),
            3,
        )
        _set(
            device,
            "energy_grid_export_total",
            _kwh(_num(meter.get("EnergyReal_WAC_Sum_Produced"))),
            3,
        )
        for phase in (1, 2, 3):
            if (voltage := _num(meter.get(f"Voltage_AC_Phase_{phase}"))) is not None:
                device.vendor[f"meter_voltage_l{phase}"] = round(voltage, 1)
            if (power := _num(meter.get(f"PowerReal_P_Phase_{phase}"))) is not None:
                device.vendor[f"meter_power_l{phase}"] = round(power, 0)
        if (frequency := _num(meter.get("Frequency_Phase_Average"))) is not None:
            device.vendor["meter_frequency"] = round(frequency, 2)
        return device
    return None


def _battery(
    data: dict[str, Any] | None, site: dict[str, Any], flow_inverter: dict[str, Any]
) -> FroniusDevice | None:
    entry = _first_entry(data)
    if entry is None:
        return None
    _key, storage = entry
    controller = (
        storage.get("Controller")
        if isinstance(storage.get("Controller"), dict)
        else None
    )
    if controller is None or controller.get("Enable") == 0:
        return None
    details = (
        controller.get("Details") if isinstance(controller.get("Details"), dict) else {}
    )
    serial = str(details.get("Serial") or "").strip()
    if not serial:
        return None
    model = str(details.get("Model") or "Battery").strip()
    device = FroniusDevice(
        serial=serial,
        kind="battery",
        name=model,
        manufacturer=str(details.get("Manufacturer") or NAME).strip(),
        model=model,
    )
    soc = _num(flow_inverter.get("SOC"))
    if soc is None:
        soc = _num(controller.get("StateOfCharge_Relative"))
    _set(device, "battery_soc", soc, 1)
    _set(device, "capacity_battery", _kwh(_num(controller.get("Capacity_Maximum"))), 2)
    _set(device, "temperature_battery", _num(controller.get("Temperature_Cell")), 1)
    if (akku := _num(site.get("P_Akku"))) is not None:
        battery_power = -akku
        _set(device, "power_battery", battery_power, 0)
        _set(device, "power_battery_charge", max(0.0, battery_power), 0)
        _set(device, "power_battery_discharge", max(0.0, -battery_power), 0)
        device.derived.update({"power_battery_charge", "power_battery_discharge"})
    if (voltage := _num(controller.get("Voltage_DC"))) is not None:
        device.vendor["battery_voltage_dc"] = round(voltage, 1)
    if (current := _num(controller.get("Current_DC"))) is not None:
        device.vendor["battery_current_dc"] = round(current, 2)
    if (mode := flow_inverter.get("Battery_Mode")) is not None:
        device.vendor["battery_mode"] = str(mode)
    return device
