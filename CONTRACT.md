# S-INV Data Contract v1

S-INV (Solar Inverter) publishes every supported manufacturer's data under one set of standardized entities. Any
integration, automation, card or dashboard can rely on these names, units and signs without knowing the manufacturer.

The machine-readable source of this contract is
[`custom_components/solar_forecast_sinv/contract.py`](custom_components/solar_forecast_sinv/contract.py). It has no
Home Assistant imports and can be read by other integrations and tools.

## Identity

S-INV publishes two levels:

- **System entities** describe the whole installation. They belong to the device "S-INV Anlage" (config entry created
  automatically with the first S-INV instance) and combine all devices of their role. This is the level other
  integrations and dashboards use.
- **Device entities** describe one inverter, battery or meter and always carry the device class and a two-digit index.

| Item | Rule | Example |
|---|---|---|
| Role key | `snake_case`, quantity first, then subject, then two-digit channel | `power_solar_mppt_01` |
| System entity ID | `<domain>.sinv_<role>` | `sensor.sinv_power_solar` |
| Device entity ID | `<domain>.sinv_<class><nn>_<role>` | `sensor.sinv_iv01_power_solar_mppt_01` |
| Device class | `iv` inverter, `bt` battery, `gm` grid meter (planned: `ev` wallbox, `hp` heat pump, `hr` heating rod) | `bt02` |
| Manufacturer-specific entity | `<domain>.sinv_<vendor>_<key>`, then `sinv_<vendor>_<n>_<key>` | `select.sinv_anker_led_mode` |
| unique_id (system) | `sinv:1:site:<role>` | `sinv:1:site:power_solar` |
| unique_id (device role) | `sinv:1:<device_serial_lower>:<role>` | `sinv:1:apcdjqd0g19200073:power_solar_mppt_01` |
| unique_id (vendor) | `sinv:1:<device_serial_lower>:<vendor>:<key>` | `sinv:1:apcdjqd0g19200073:anker:wifi_signal` |
| State attributes (device roles) | `sinv_contract`, `sinv_role`, `sinv_device_index`, `sinv_vendor` | `sinv_role: power_solar_mppt_01` |
| State attributes (system) | `sinv_contract`, `sinv_role`, `sinv_aggregation`, `sinv_sources` | `sinv_sources: [sensor.sinv_iv01_power_solar]` |

The device index is assigned per class in order of first discovery and never changes afterwards. One device can carry
several classes (a Solarbank is `iv01` and `bt01`).

### System aggregation

| Rule | Roles | System value |
|---|---|---|
| sum | power and energy roles of PV, inverter output, battery; `capacity_battery` | sum of all devices |
| capacity_weighted | `battery_soc` | mean weighted by `capacity_battery`, plain mean without capacities |
| single | grid roles, house balance, energy flows | value of the first device (one grid point per installation) |
| any | `state_curtailment` | on while one device curtails |
| all | `state_grid_export_allowed` | on only while every device allows export |
| device only | MPPT channels, grid voltage/frequency, temperatures, state of health, battery packs | no system entity |

A system value is unavailable while one of its device values is missing, so totals never drop. Without a signed grid
value, `power_grid` of the installation is `power_grid_import − power_grid_export` of the grid meter.

House balance and energy flows (`power_house`, `energy_house_*`, `power_*_to_*`) are meaningful for the installation
only: the providing device keeps a hidden device entity as source, the visible entity is the system entity.

**How consumers find a role:** read the entity registry (`platform == "solar_forecast_sinv"`, unique_id prefix
`sinv:1:site:` for the installation, `sinv:1:` for devices) or the `sinv_role` attribute. Never rely on the entity ID
alone – users may rename entities.

### Transition from the first draft

The first draft named device entities `sinv_<role>` and `sinv_<n>_<role>`. On the first start of this version an
existing `sinv_<role>` of a role with a system entity becomes the system entity and keeps its history; all other draft
IDs are renamed to `sinv_<class><nn>_<role>`. Entity IDs chosen by the user are never changed.

## Units and signs

| Quantity | Unit | Rule |
|---|---|---|
| Power | W | flow values (`*_import`, `*_export`, `*_to_*`, `*_charge`, `*_discharge`) are ≥ 0 |
| Energy | kWh | `total_increasing`; `_today` values reset at local midnight |
| Voltage / current / frequency | V / A / Hz | |
| Temperature | °C | |
| State of charge / health | % | 0–100 |
| `power_battery` | W | **positive while charging**, negative while discharging |
| `power_grid` | W | **positive while importing**, negative while exporting |

## Roles

`NN` is a two-digit channel (`01` … `16`). A manufacturer publishes only the roles it can deliver.

| Role | Unit | Domain | Meaning |
|---|---|---|---|
| `power_solar` | W | sensor | total PV power |
| `power_solar_mppt_NN` | W | sensor | PV power of input NN |
| `voltage_solar_mppt_NN` | V | sensor | PV voltage of input NN |
| `current_solar_mppt_NN` | A | sensor | PV current of input NN |
| `energy_solar_total`, `energy_solar_today` | kWh | sensor | PV energy |
| `power_inverter_ac_output` | W | sensor | AC output of the inverter |
| `voltage_grid`, `frequency_grid` | V, Hz | sensor | grid quality at the inverter |
| `temperature_inverter` | °C | sensor | |
| `state_grid_export_allowed` | on/off | binary_sensor, switch | grid export permitted |
| `state_curtailment` | on/off | binary_sensor | PV output is being limited |
| `battery_soc`, `battery_soh` | % | sensor | system battery |
| `power_battery` | W | sensor | signed, + charging |
| `power_battery_charge`, `power_battery_discharge` | W | sensor | |
| `power_solar_to_battery`, `power_grid_to_battery`, `power_battery_to_house` | W | sensor | energy flows |
| `energy_battery_charge_total`, `energy_battery_discharge_total` | kWh | sensor | |
| `capacity_battery` | kWh | sensor | usable capacity incl. expansions |
| `temperature_battery` | °C | sensor | |
| `battery_pack_soc_NN`, `battery_pack_soh_NN`, `temperature_battery_pack_NN` | %, %, °C | sensor | pack NN; `01` is the main pack |
| `power_grid` | W | sensor | signed, + import |
| `power_grid_import`, `power_grid_export` | W | sensor | |
| `energy_grid_import_total`, `energy_grid_export_total` | kWh | sensor | |
| `power_house` | W | sensor | house consumption |
| `power_solar_to_house`, `power_grid_to_house` | W | sensor | energy flows |
| `energy_house_today` | kWh | sensor | resets at local midnight |
| `energy_house_total` | kWh | sensor | lifetime counter |

## External grid meter

An S-INV instance whose system has no grid meter of its own can publish the grid roles from a meter that is already in Home Assistant (for example Shelly 3EM, Tibber Pulse, ESPHome). It is configured in the instance options, offered only when no native grid meter exists, and for one instance per installation. S-INV normalizes unit (W/kW, Wh/kWh/MWh) and sign (+ import) and publishes `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total` and `energy_grid_export_total` on a device "External grid meter". These entities carry `sinv_vendor: external` and `sinv_source: <source entity_id>`.

## Planned

Wallboxes (e.g. Fronius Wattpilot) and heat pumps as further S-INV instances with their own role families.

## Versioning

The major version is part of every unique_id (`sinv:1:`) and of the `sinv_contract` attribute. New roles are added
without a version change. Renaming or removing a role or changing a unit or sign requires a new major version with a
transition period in which both versions are published.

## Manufacturer coverage

| Manufacturer | Connection | Roles published |
|---|---|---|
| Anker Solix | Cloud (account + MQTT) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN` (Solarbank 3), `power_inverter_ac_output`, `voltage_grid`, `frequency_grid` (Solarbank 3), `state_grid_export_allowed`, `state_curtailment`, `battery_soc`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `power_grid_to_battery`, `power_solar_to_battery` (derived where the device does not report it), `power_grid_to_house`, `power_battery_to_house`, `power_solar_to_house` (derived, solarbanks), `battery_pack_soc_NN`, `temperature_battery_pack_NN`, `power_grid_import`, `power_grid_export` (smart meter; `power_grid` of the installation is derived from both), `power_house`, `energy_solar_total`, `energy_battery_charge_total`, `energy_battery_discharge_total`, `energy_grid_import_total`, `energy_grid_export_total`, `energy_house_total`, `energy_solar_today`, `energy_house_today` |
| Fronius | Local network (Solar API v1, IP address only) | `power_solar`, `power_solar_mppt_NN` (derived V×I), `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `power_house`, `battery_soc`, `capacity_battery`, `temperature_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total` (meter at the grid point) |
| Zendure SolarFlow (zenSDK) | Local network (zenSDK HTTP API, IP address only) | `power_solar`, `power_solar_mppt_NN`, `power_inverter_ac_output`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `battery_soc`, `battery_pack_soc_NN`, `temperature_battery_pack_NN` |
| Hoymiles via OpenDTU | Local network (OpenDTU REST API) | per inverter: `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_today`, `energy_solar_total` |
| Hoymiles DTU / HMS-W | Local network (DTU protobuf, hoymiles-wifi) | per inverter: `power_solar` (sum of ports), `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_today`, `energy_solar_total` |
| Hoymiles via AhoyDTU | Local network (AhoyDTU REST API, read without password) | per inverter: `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_today`, `energy_solar_total` |
| KOSTAL PLENTICORE G2 | Local network (Modbus TCP, port 1502, unit 71, read only) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `power_house`, `power_solar_to_house`, `power_grid_to_house`, `power_battery_to_house`, `energy_house_total`, `energy_solar_total`, `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| SolaX Hybrid / IES | Local network (Modbus TCP of the Pocket WiFi+LAN module, port 502, unit 1, read only) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house` (derived), `energy_solar_total`, `energy_solar_today`, `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Sungrow Hybrid (SH) | Local network (Modbus TCP of the LAN port or WiNet-S/WiNet-S2 Ethernet, port 502, unit 1, read only) | `power_solar`, `power_solar_mppt_NN` (derived), `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house`, `energy_solar_total`, `energy_solar_today`, `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Huawei SUN2000 | Local network (Modbus TCP of the SDongle, port 502, unit 1, or the inverter's access point, port 6607, unit 0; read only) | `power_solar`, `power_solar_mppt_NN` (derived), `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today` (without battery), `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house` (derived), `battery_soc`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Solakon ONE | Local network (Modbus TCP, port 502, unit 1, read only) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house` (derived), `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |

Fronius: one S-INV instance per inverter (IP address). Sign conventions of the Solar API are converted: `power_battery` = −`P_Akku`, `power_house` = −`P_Load`; the inverter AC energy `TOTAL_ENERGY` includes battery discharge on hybrid inverters and is therefore published as `sinv_fronius_inverter_energy_total`, not as `energy_solar_total`. A meter outside the grid point never provides grid roles.

Zendure: one S-INV instance per device (IP address); the local zenSDK API must be switched on in the Zendure app ("Add HEMS"). `power_battery` = `outputPackPower` − `packInputPower` (+ charging), pack temperature = (`maxTemp` − 2731) / 10 °C. Voltages, the enclosure temperature and the AC input power are published as vendor values or not at all until their scaling is verified on a device. Zendure reports no grid values and no energy counters; use the external grid meter for the grid roles.

Hoymiles: one S-INV instance per OpenDTU or per DTU; every microinverter behind it is its own device. A microinverter has no battery, so its AC energy is its solar energy. Inverters that are off at night read 0 W (energy counters kept) so installation totals stay available; an unreadable DTU answer is an error, never 0 W. The DTU is polled every 35 s (minimum 30 s) because DTUs suffer from frequent requests.

AhoyDTU: one S-INV instance per AhoyDTU; every enabled inverter is its own device. S-INV reads `GET /api/inverter/list` and `GET /api/inverter/id/<id>` (no password needed). Values come as lists in AhoyDTU's fixed field order; `YieldDay` is converted from Wh to kWh. Before an inverter's first answer AhoyDTU reports zeros, which are not published; an inverter that is not producing reads 0 W, energy counters kept.

KOSTAL: register map from the KOSTAL Modbus interface description rev. 2.9; float word order follows register 5. `power_battery` = −(battery current × battery voltage) (register 200 is negative while charging). House flows come from the inverter's energy manager; the powermeter total depends on the sensor position, which Modbus does not report, so it stays a vendor value. S-INV only sends read requests (function 0x03).

SolaX: register map from the SolaX Energy Storage Inverter MODBUS protocol V001.02; real-time values are input registers (function 0x04), 32-bit values low word first, at least 1 s between requests. `power_grid` = −FeedinPower (meter/CT at the grid point, positive = to grid); grid roles are hidden while the meter reports a communication error. `power_battery` = BatPowerSum (positive while charging). `power_house` = inverter on-grid output − feed-in + off-grid (EPS) output. S-INV only sends read requests (functions 0x03 and 0x04).

Sungrow: register map from the Sungrow communication protocol of residential and small industrial hybrid inverters V1.1.17; all values are input registers (function 0x04) at the documented register minus one, 32-bit values low word first, unavailable registers (0xFFFF, 0x7FFF, 0xFFFFFFFF, 0x7FFFFFFF) are skipped, at least 1 s between requests. `power_grid` = meter active power 5601 (positive = from grid); grid roles and `power_house` (load power 13008) are only valid with a smart meter connected directly to the inverter. `power_battery` = −battery power 5214 (5214 is negative while charging); firmware without 5214 uses the unsigned 13022 with the direction from the charge/discharge bits of the power flow status 13001. `power_solar_mppt_NN` = MPPT voltage × current. The total output energy 5004 includes battery discharge and is therefore a vendor value, not `energy_solar_total`. S-INV only sends read requests (function 0x04).

Huawei: register map from the Huawei SUN2000MA V100R001C20 Modbus Interface Definitions; holding registers (function 0x03) at the documented address, 32-bit values high word first, at least 1 s between requests and 1 s after connecting. `power_grid` = −meter active power 37113 (positive = feeding the grid); grid roles need the meter status 37100 = normal. The PV string inputs PVn are published as `*_solar_mppt_NN`. With a LUNA2000 battery the inverter yield 32106/32114 includes battery discharge and is therefore published as `sinv_huawei_inverter_energy_total`/`_today`, not as `energy_solar_*`. Battery registers (37758 capacity, 37760 SOC, 37765 power positive while charging, 37780/37782 energy) follow the residential SUN2000 interface definitions and are read only when present. `power_house` = inverter active power − meter feed-in. S-INV only sends read requests (function 0x03).

Solakon: register map from the Solakon ONE Modbus Protokoll v.02/26; holding registers (function 0x03) at the documented address, 32-bit values high word first, the documented factor divides the raw value. `power_grid` = −meter collection active power 39168 (positive = feeding the grid) while meter/CT 1 is connected (38801 = 1); grid energy = 39617 (import) and 39613 (export). `power_battery` = 39162 (positive while charging). Battery capacity and state of charge combine BMS1 and an online BMS2 (design energy, capacity-weighted SoC). The device's own AC output/input counters 39621/39625 stay vendor values. `power_house` = inverter active power − meter feed-in. S-INV only sends read requests (function 0x03).

Anker energy counters from MQTT (`energy_solar_total`, `energy_battery_charge_total`, `energy_battery_discharge_total`, `energy_grid_import_total`, `energy_grid_export_total`, `energy_house_total`) are always created. The daily cloud statistics (`energy_solar_today`, `energy_house_today`) require the device's energy category to be enabled in the S-INV options, because they cost additional cloud requests.

Anker house flows (derived for solarbanks, attribute `sinv_derived: true`):

```
grid_to_house    = min(max(0, grid_power − grid_to_battery), house)
battery_to_house = min(discharge, ac_output, house)
solar_to_house   = max(0, min(ac_output − battery_to_house, house − battery_to_house − grid_to_house))
```

`grid_power` is the signed solarbank grid power (cloud grid usage as fallback; published as the vendor value `sinv_anker_grid_power_signed`, not as `power_grid`, because the smart meter is the grid point), `ac_output` the solarbank AC output to the house.

Anker `power_solar_to_battery` (derived): battery charge power minus grid-to-battery power, bounded to 0 W … PV power.

Known limitation: Anker fills grid-to-battery power in the operating state "AC charging" (seen 2026-10-11: 1191 W) but reports 0 W in the state "protection charging" although the battery charges from the grid. S-INV publishes `power_grid_to_battery` as reported; the bound on `power_solar_to_battery` keeps that role correct in both states.

Anker `state_curtailment` rule (the device reports no curtailment flag): on while the battery is full (state of
charge ≥ 99 %), grid export is not allowed and PV power is above 0 W.

## Credits

The Anker Solix connection is based on [ha-anker-solix](https://github.com/thomluther/ha-anker-solix) by Thomas Luther
(MIT license).
