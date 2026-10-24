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
| Device class | `iv` inverter, `bt` battery, `gm` grid meter, `hp` heat pump (device entities of S-INV HP; planned: `ev` wallbox, `hr` heating rod) | `bt02` |
| Manufacturer-specific entity | `<domain>.sinv_<vendor>_<key>`, then `sinv_<vendor>_<n>_<key>` | `select.sinv_anker_led_mode` |
| unique_id (system) | `sinv:1:site:<role>` | `sinv:1:site:power_solar` |
| unique_id (device role) | `sinv:1:<device_serial_lower>:<role>` | `sinv:1:apcdjqd0g19200073:power_solar_mppt_01` |
| unique_id (vendor) | `sinv:1:<device_serial_lower>:<vendor>:<key>` | `sinv:1:apcdjqd0g19200073:anker:wifi_signal` |
| State attributes (device roles) | `sinv_contract`, `sinv_role`, `sinv_device_index`, `sinv_vendor` | `sinv_role: power_solar_mppt_01` |
| State attributes (system) | `sinv_contract`, `sinv_role`, `sinv_aggregation`, `sinv_sources`; `sinv_derived: true` when the value is calculated; continued lifetime totals also carry `sinv_source` and `sinv_source_offset` | `sinv_sources: [sensor.sinv_iv01_power_solar]` |

The device index is assigned per class in order of first discovery and never changes afterwards. One device can carry
several classes (a Solarbank is `iv01` and `bt01`).

### System aggregation

| Rule | Roles | System value |
|---|---|---|
| sum | power and energy roles of PV, inverter output, battery; `capacity_battery` | sum of all devices |
| capacity_weighted | `battery_soc` | mean weighted by `capacity_battery`, plain mean without capacities |
| single | grid roles, house balance, energy flows | value of the first device (one grid point per installation). Lifetime energy counters keep that value across a source change; see below |
| any | `state_curtailment` | on while one device curtails |
| all | `state_grid_export_allowed` | on only while every device allows export |
| house_plus_foreign_ac | `power_house` with generators outside the meter owner's system | house value of the one device that reports it, plus `power_ac_net` of every generator in another S-INV entry (see below) |
| device only | MPPT channels, grid voltage/frequency, temperatures, state of health, battery packs, `power_ac_net` | no system entity |
| derived | daily energy and house energy when no device reports that role | calculated from installation totals; `sinv_derived: true` |

A system value is unavailable while one of its device values is missing, so totals never drop. Without a signed grid
value, `power_grid` of the installation is `power_grid_import − power_grid_export` of the grid meter.

`energy_grid_import_total`, `energy_grid_export_total` and `energy_house_total` are the exception to "the first
device". They are lifetime counters (`total_increasing`). The installation keeps using one source and, when that
source changes, stores an offset equal to the last published value minus the new source value. The published value
is the new source value plus that offset, so the counter does not jump and does not start again at the other
device's smaller total. The source, the offset and the last published value are stored with the installation and
survive a restart. The first start without a stored continuation takes the last state of this
installation entity as the last published value when that state is a finite number, at least 0, and its
unit is kWh. The offset is that state minus the current source value when the source is lower, and 0 when
the source is greater or equal: the counter does not drop on update, and a higher source does not get an
extra offset on top. A missing or invalid last state uses offset 0. A continuation that is already stored
is not seeded again. The published value never falls below the stored last published value. Home Assistant
treats a `total_increasing` drop to less than 90% of the previous state as a counter reset
(`reset_detected` in `homeassistant/components/sensor/recorder.py`); a smaller dip is only a warning.
This counter publishes neither. A lower reading of the same source stays at the last published value, and
the next higher reading continues from there. With no source value the counter is unavailable.

Anker grid energy prefers a Solarbank over a smart meter. A Solarbank is recognized by the device type
`solarbank`, which S-INV stores as an extra device identifier when it creates the device, or, if that identifier
is not there yet, by the part number (`model_id`) of the Solarbank family (A17C, A17E2, AE103, AE111). The
display name is not used. The Solarbank publishes the counters continuously; the
smart meter publishes them only after a realtime trigger. The meter is adopted only after the Solarbank value has
been missing for 15 minutes. A meter reading that appears while the Solarbank is reporting does not take over.
Power roles stay on the first device and are not reordered. Derived day counters and the derived house day read
these continued totals, so a source change does not dent the day. Each source change is logged once. The sensor
keeps `sinv_sources` and adds `sinv_source` (the entity in use) and `sinv_source_offset`.

House balance and energy flows (`power_house`, `energy_house_*`, `power_*_to_*`) are meaningful for the installation
only: the providing device keeps a hidden device entity as source, the visible entity is the system entity.

House consumption is never summed over devices: every device that reports it already includes the whole grid point,
so a sum would count the grid import twice. The device reporting `power_house` (the owner of the grid meter) only
knows its own system, e.g. a Fronius GEN24 does not know a second Symo on its own Datamanager. When exactly one device
reports `power_house` and generators (devices with `power_solar`, `power_inverter_ac_output` or `power_battery`) of other
S-INV entries exist, the installation adds their `power_ac_net` (rule `house_plus_foreign_ac`). This requires an owner
whose `power_house` is an energy balance of grid and its own AC power (Fronius, Huawei, SolaX, Sungrow, Solakon; not
KOSTAL flow sums or Anker cloud values). If any such generator has no `power_ac_net`, the owner is not a balance
vendor, or more than one device reports `power_house`, the rule stays `single`. While a foreign value is missing
(device offline), the owner's value is used alone for that moment. Device `power_house` values are not clamped; the
installation never reports a negative house consumption. The attribute `sinv_aggregation` names the rule in use,
`sinv_sources` lists every entity used. Not detected: an owner that already includes a foreign generator through its
own secondary meter (Fronius external generator meter) – such a generator must not be added as a separate S-INV entry.

### Derived installation energy

A measured device value always wins. The installation publishes a derived entity only when no device
reports that role and every input exists. The entity then carries `sinv_derived: true` and
`sinv_aggregation: derived`. A missing input is unavailable, never 0.

`energy_solar_today`, `energy_grid_import_today`, `energy_grid_export_today`,
`energy_battery_charge_today` and `energy_battery_discharge_today` use the device value when one exists.
Otherwise each is the installation total now minus that total at local midnight. The day is the local
calendar day from `homeassistant.util.dt`, not a fixed 24 h, so a summer-time day and a winter-time day
both roll at local midnight. Each derived day counter schedules the next local midnight
(`homeassistant.helpers.event.async_track_point_in_utc_time`), writes its state again when that fires,
and schedules the following midnight. The listener is removed with the entity. A quiet total, such as
`energy_solar_total` overnight, therefore does not leave yesterday's day value up until the next source
update. The midnight baseline is stored with the installation and survives a restart. On the first day,
and after a restart that has no baseline for the current local day, the value stays unavailable until
the next local midnight, so a partial day is not shown as a full day. A total that falls (meter replaced
or counter reset) keeps the energy counted so far and continues from the new value. A step of more than
100 kWh in one update is not added; later readings count from the new total. The value is never negative.

`energy_house_today` uses the device value when one exists. When a device reports `energy_house_total`
but not the day, the day is the rise of that device counter since local midnight. When no device reports
either role, the day is solar today plus grid import today plus battery discharge today, minus grid
export today, minus battery charge today, and at least 0. The battery terms are 0 when the installation
has no battery. A battery whose charge or discharge total is missing, or any other input without a day
value, makes the day unavailable. The inputs are the day values above, not the lifetime counters, so an
older export counter than the solar counter does not freeze the day at 0, and a short dip while one
device polls before another is not stored as a counter reset. When the day is that sum, the
published value is the highest sum of the local day. A later lower sum is not published. The
mark is `last_today` on the same house accumulator the derived house total already uses, so
the total grows only when the day reaches a new high and a restart keeps the mark. The next
local day starts again at 0 or at that day's first sum. A missing input stays unavailable:
the stored mark is not written as a fresh measurement, because statistics omit an unavailable
state and would otherwise record the old high as if it had been measured again.

`energy_house_total`, when a device reports it (Anker and KOSTAL do), is that device value. Otherwise it
is the persisted sum of the positive rises of the derived house day. It starts at 0 on the first local
day that has a baseline, stays unavailable until then, and never falls: a dip of the day value adds
nothing, and the next local midnight does not add the day a second time. The sum survives a restart.

**Derived installation power flows.** `power_solar_to_house`, `power_solar_to_battery`,
`power_grid_to_battery`, `power_battery_to_house` and `power_grid_to_house` keep a measured
device flow (aggregation `single`). When no device reports that flow, the installation derives
it from P = `power_solar`, C = `power_battery_charge`, D = `power_battery_discharge` and
H = `power_house`. H is the installation house value after the existing house rule, including
foreign net AC when that rule adds it, and clamped at 0. Every finite input is clamped at 0
before the split. A missing input leaves every flow that needs it unavailable; it is never
published as 0.

The split gives PV to the house first, then the remaining PV to the battery, then the grid:

- `power_solar_to_house` = min(P, H)
- `power_solar_to_battery` = min(C, P - `power_solar_to_house`)
- `power_grid_to_battery` = max(0, C - `power_solar_to_battery`)
- `power_battery_to_house` = min(D, H - `power_solar_to_house`)
- `power_grid_to_house` = max(0, H - `power_solar_to_house` - `power_battery_to_house`)

Without a battery (`battery_present`, the same rule as the derived house energy) the three
battery flows are not created, and the two house flows use C = 0 and D = 0. Each flow is
derived on its own: a device that measures only some flows leaves the missing ones to be
derived. The value is recomputed on every change of an input. A derived flow carries
`sinv_derived: true`, `sinv_aggregation: derived` and `sinv_sources` listing the device
entities of those inputs, including foreign `power_ac_net` when the house rule uses it.

The split is an approximation. Devices are polled at different moments, and conversion
losses are not measured, so the parts need not match a physical meter. A measured flow
always wins over this approximation.

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
| `energy_solar_total`, `energy_solar_today` | kWh | sensor | PV energy; `energy_solar_today` is derived from the total when no device reports the day |
| `power_inverter_ac_output` | W | sensor | AC output of the inverter |
| `power_ac_net` | W | sensor | net AC power of a device: positive = delivered into the house grid, negative = drawn from it. Published only where the sign is unambiguous: Hoymiles microinverters (= AC output), Fronius inverters without battery (= PAC, 0 while asleep) and Zendure (AC output − AC input); hybrid inverters do not publish it |
| `voltage_grid`, `frequency_grid` | V, Hz | sensor | grid quality at the inverter |
| `temperature_inverter` | °C | sensor | |
| `state_grid_export_allowed` | on/off | binary_sensor, switch | grid export permitted |
| `state_curtailment` | on/off | binary_sensor | PV output is being limited |
| `battery_soc`, `battery_soh` | % | sensor | system battery |
| `power_battery` | W | sensor | signed, + charging |
| `power_battery_charge`, `power_battery_discharge` | W | sensor | |
| `power_solar_to_battery`, `power_grid_to_battery`, `power_battery_to_house` | W | sensor | battery flows; a measured device value wins, otherwise derived from installation power |
| `energy_battery_charge_total`, `energy_battery_discharge_total` | kWh | sensor | |
| `energy_battery_charge_today`, `energy_battery_discharge_today` | kWh | sensor | since local midnight; device value wins, otherwise derived from the totals |
| `capacity_battery` | kWh | sensor | usable capacity incl. expansions |
| `temperature_battery` | °C | sensor | |
| `battery_pack_soc_NN`, `battery_pack_soh_NN`, `temperature_battery_pack_NN` | %, %, °C | sensor | pack NN; `01` is the main pack |
| `power_grid` | W | sensor | signed, + import |
| `power_grid_import`, `power_grid_export` | W | sensor | |
| `energy_grid_import_total`, `energy_grid_export_total` | kWh | sensor | |
| `energy_grid_import_today`, `energy_grid_export_today` | kWh | sensor | since local midnight; device value wins, otherwise derived from the totals |
| `power_house` | W | sensor | house consumption |
| `power_solar_to_house`, `power_grid_to_house` | W | sensor | house flows; a measured device value wins, otherwise derived from installation power |
| `energy_house_today` | kWh | sensor | since local midnight; device value wins, otherwise the device house total's day, otherwise the highest sum of the derived day values on the local day |
| `energy_house_total` | kWh | sensor | lifetime counter; device value wins, otherwise the monotonic sum of derived house-today rises |

## External grid meter

An S-INV instance whose system has no grid meter of its own can publish the grid roles from a meter that is already in Home Assistant (for example Shelly 3EM, Tibber Pulse, ESPHome). It is configured in the instance options, offered only when no native grid meter exists, and for one instance per installation. S-INV normalizes unit (W/kW, Wh/kWh/MWh) and sign (+ import) and publishes `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total` and `energy_grid_export_total` on a device "External grid meter". These entities carry `sinv_vendor: external` and `sinv_source: <source entity_id>`.

## S-INV HP

Heat pumps publish on their own device **S-INV HP**, next to "S-INV Anlage". The inverter installation does not
contain these roles, and S-INV HP does not contain inverter roles. No manufacturer is connected yet; the roles,
ids and aggregation are the contract. A heat-pump instance creates the aggregate entry automatically and the
last one removes it, the same way "S-INV Anlage" follows inverter instances.

| Item | Rule | Example |
|---|---|---|
| Aggregate entity ID | `<domain>.sinv_hp_<role without the leading hp_>` | `sensor.sinv_hp_power_electric` |
| Device entity ID | `<domain>.sinv_hp<nn>_<role without the leading hp_>` | `sensor.sinv_hp01_power_electric` |
| unique_id (aggregate) | `sinv:1:hp:<role>` (the role key keeps its `hp_` prefix) | `sinv:1:hp:hp_power_electric` |
| unique_id (device) | `sinv:1:<device_serial_lower>:<role>` | `sinv:1:cs6800i:hp_power_electric` |
| State attributes | same as the installation: `sinv_contract`, `sinv_role`, `sinv_aggregation`, `sinv_sources`; `sinv_derived: true` when calculated | |

Serials `site` and `hp` are reserved, so a device cannot take the aggregate id.

### Aggregation (cascade)

| Rule | Roles | Why |
|---|---|---|
| sum | electric and thermal power; electric, thermal and auxiliary energy (total, today, heating, hot water); compressor starts; runtime total / heating / hot water | a cascade adds power, energy, starts and hours |
| derived | `hp_cop_live`, `hp_cop_total` | cascade COP is the sum of heat divided by the sum of electricity, not the first unit and not omitted. Marked `sinv_derived: true` |
| any | `hp_compressor_running`, `hp_aux_heater_active` | on while one heat pump reports on; a missing device value leaves the aggregate unavailable |
| single | `hp_operating_mode`; every temperature (outdoor, flow, return, hot water, storage, source, indoor, target); `hp_volume_flow` | the aggregate publishes the first heat pump in device-index order, so one heat pump (the usual case) exposes every normalized sensor STATS/EAI reads, including outdoor temperature. A cascade shows that first device; each heat pump still keeps its own device entity. The value is unavailable while the first device's value is missing. The next device is not used in its place |

`hp_cop_live` = `hp_power_thermal` / `hp_power_electric` of the aggregate (the sums). `hp_cop_total` =
`hp_energy_thermal_total` / `hp_energy_electric_total`. Both stay unavailable unless the two inputs exist and
the electric value is strictly above 1 W (live) or 0.001 kWh (total). Zero and values at or below that
threshold are not a COP. A negative thermal value is unavailable.

`*_today` roles use a device value when one exists (summed). Otherwise they are the rise of the matching
aggregate total since local midnight, with the same tracker, baseline store and midnight listener as the
inverter installation (`site_daily`). The first local day without a baseline stays unavailable. The value is
marked `sinv_derived: true`.

| Role | Unit | Domain | device_class | state_class |
|---|---|---|---|---|
| `hp_power_electric`, `hp_power_thermal` | W | sensor | power | measurement |
| `hp_energy_electric_total`, `_today`, `_heating_total`, `_heating_today`, `_dhw_total`, `_dhw_today` | kWh | sensor | energy | total_increasing |
| `hp_energy_thermal_total`, `_today`, `_heating_total`, `_heating_today`, `_dhw_total`, `_dhw_today` | kWh | sensor | energy | total_increasing |
| `hp_cop_live`, `hp_cop_total` | — | sensor | — | measurement |
| `hp_temperature_outdoor`, `_flow`, `_return`, `_dhw`, `_storage`, `_source`, `_indoor`, `_target` | °C | sensor | temperature | measurement |
| `hp_operating_mode` | — | sensor | enum | — |
| `hp_compressor_running` | on/off | binary_sensor | running | — |
| `hp_compressor_starts` | — | sensor | — | total_increasing |
| `hp_runtime_total`, `hp_runtime_heating`, `hp_runtime_dhw` | h | sensor | duration | total_increasing |
| `hp_aux_heater_active` | on/off | binary_sensor | heat | — |
| `hp_aux_heater_energy_total`, `hp_aux_heater_energy_today` | kWh | sensor | energy | total_increasing |
| `hp_volume_flow` | L/h | sensor | — | measurement |

Heating and hot-water rows are the split of the electric and thermal energy counters (compressor heating
versus hot water, and supplied heat versus hot water). The auxiliary heater is a separate electric counter.
Names are shipped in German, English and French.

### Bosch/Buderus via EMS-ESP

Read only. S-INV sends GET and never a token. The scheme is always `http`. The host is a hostname or an IP
address with an optional port; a scheme, userinfo, path or query is rejected. Redirects are not followed.
Each response is capped (256 KiB) and must be a JSON object. The poll reads `/api/boiler/values`,
`/api/thermostat/values` and `/api/heatpump/values` (HTTP 400/404 means that device is absent). EMS-ESP
never drops a detected device at runtime, so an absent path is skipped by later polls and read again after
30 min, after a reload or restart, or on the next poll when boiler and heatpump are both empty. A timeout or
a 429 never marks a path absent.
`/api/boiler/hppower` is read once at setup for the thermal-power unit.

The device serial and the config-entry unique_id are a short ASCII id derived from the config entry id, not
the host. A DHCP address change or a host edit in the options keeps the entities. A second entry for the
same host is rejected by comparing hosts. Scan interval default 30 s, minimum 15 s: EMS-ESP is an ESP32 on
the EMS bus. Each cycle is three GETs with 1 s between them. EMS-ESP 3.8.6 returned HTTP 429 on
`/api/thermostat/values` 0.21 s after the previous GET (tester 2026-10-23); one second stays above that
gap, and the two gaps plus the reads fit in the 15 s minimum. A 429 waits for `Retry-After` (at most 10 s,
otherwise 2 s) and is retried at most twice. The poll stops at 12 s instead of hanging. Setup that still
sees 429 is `emsesp_busy`. On a later poll a throttled thermostat or heatpump is omitted for that cycle and
the boiler values are kept; a throttled boiler fails the cycle. No missing value is stored as 0.

Setup distinguishes connection or timeout (`emsesp_unreachable`), HTTP 401/403 (`emsesp_forbidden`), HTTP 429
(`emsesp_busy`), boiler and heatpump absent or empty (`emsesp_no_heat_pump`), and a redirect, a non-object,
an oversized body or any other status (`emsesp_bad_response`). The log records the code and the host once,
not the response body.

Booleans and `hpactivity` follow the EMS-ESP locale words (English, German, Dutch, Swedish, Polish,
Norwegian, French, Turkish, Italian, Slovak, Czech) plus `true`/`false` and `1`/`0`. Comparison ignores case
and surrounding space. An unrecognized boolean stays unavailable. An unrecognized activity is `unknown`.
`hp_aux_heater_active` is on only for a recognized on-value or an active status (heating, cooling, hot
water, pool, defrost). Off in every language is false. Anything else, including compressor alarm, stays
unavailable.

### Other heat pump (bridge)

An existing Home Assistant integration can fill the same roles. The user picks one entity per role. At
least `hp_power_electric` or `hp_energy_electric_total` is required: power is the live value, and the
electric total is enough for the aggregate to derive today's electric energy. S-INV only reads. It rejects
its own entities, a unit or device class that does not convert, a `*_total` whose state class is not
`total` or `total_increasing`, and the same entity on two roles. Values are converted into the contract
units (W, kWh, °C, h, L/h). Updates are push, not a poll. Unavailable stays unavailable. Day counters the
user does not map are still derived from the matching total. Operating-mode text is matched by known words
and is otherwise `unknown`.

| Role | EMS-ESP key | Evidence |
|---|---|---|
| `hp_energy_electric_total` | `metertotal` (kWh) | tester 2026-10-23: 4310.56 |
| — | `metercomp`, `metereheat` | compressor and electric-heater parts of `metertotal` (4076.02 + 234.53). Not heating/hot-water roles |
| `hp_energy_electric_heating_total` | `meterheat` (kWh) | electrical heating meter, not thermal |
| `hp_energy_electric_dhw_total` | `dhw.meter` (kWh) | electrical hot-water meter; tester 1160.73 |
| `hp_energy_thermal_total` | `nrgtotal` (kWh) | tester 12628.86 |
| `hp_energy_thermal_heating_total` | `nrgheat` (kWh) | tester 9545.21 |
| `hp_energy_thermal_dhw_total` | `dhw.nrg` (kWh) | tester 3083.65 |
| `hp_power_electric` | `hpcurrpower` (W) | tester 420 |
| `hp_power_thermal` | `hppower` | kW on boiler, W on the heatpump device; converted to W. Tester 2.1 kW = 2100 W |
| `hp_temperature_outdoor` | `outdoortemp` | tester 9.7 |
| `hp_temperature_flow` / `_return` | `curflowtemp` / `rettemp` | tester 30.1 / 26.1 |
| `hp_temperature_dhw` | `dhw.curtemp` | tester 55.8 |
| `hp_temperature_storage` | `dhw.storagetemp1` | only when the key is present |
| `hp_temperature_source` | air `hptl2`, brine `hpbrinein` | air/water reports `hpbrinein` 0; that 0 is not published |
| `hp_volume_flow` | `pc1flow` (l/h) | `-1` means not installed. Tester 801 |
| `hp_operating_mode` | `hpactivity` | locale words for off, heating, cooling, hot water → dhw, pool / pool heating → pool, defrost; anything else `unknown` |
| `hp_compressor_running` | `hpcompon` | locale on/off, `true`/`false`, `1`/`0`; anything else unavailable |
| `hp_compressor_starts` | `totalcompstarts` | tester 476 |
| `hp_runtime_total` / `_heating` / `_dhw` | `uptimetotal` / `uptimecompheating` / `dhw.uptimecomp` | minutes → hours |
| `hp_aux_heater_active` | `auxheaterstatus` | on only for a recognized on-value or an active status; off is false; unknown stays unavailable |
| `hp_aux_heater_energy_total` | `auxelecheatnrgconstotal` (kWh) | |
| `hp_temperature_indoor` / `_target` | `hcN.currtemp` / `hcN.seltemp` | the heating circuit chosen at setup. No circuit → both absent |
| `hp_cop_live`, `hp_cop_total`, `*_today` | derived on S-INV HP | not read from EMS-ESP |

`metercomp` and `metereheat` are documented above and are not published. A missing key stays missing; it is
never stored as 0. Values outside the plausibility bounds (temperature −40…120 °C, power 0…100 kW, energy
0…10 GWh, flow 0…100000 l/h) are dropped.

### Stiebel Eltron via ISG Modbus

Read only. S-INV uses Modbus function 04 (input registers) and never 03, 06 or 16. Block 2 is a
read/write holding block and is not read. TCP port 502 and unit id 1 are the ISG defaults
(`ste_isg_modbus_DM0000040850-fts.txt:1160`). Table addresses are 1-based
(`faa.txt:226`, `fts.txt:233`, `fts.txt:1252`). The PDU address is the table address minus one. The
example that reads register 30501 as address 501 (`fts.txt:1165`) names that 1-based address, so the
request uses 500. Outdoor temperature 507 is requested as 506, the status block starts at 2500 and the
energy block at 3500. The same shift is what the tester's ISG library uses (outside temperature at 506,
where the table lists 507).

Type 2 is a signed value times 0.1 (`fts.txt:98`, example `fts.txt:111`). Type 6 is an integer
(`fts.txt:100`). The substitute value 32768 (`0x8000`) means the object is absent (`fts.txt:232`). It is
tested on the raw word before any signed scaling, so it is never published as 0 or as −3276.8 °C.

One plant device is published from the "all heat pumps" registers. Per-heat-pump blocks (WP 1–6, from
3523) are separable, but the S-INV HP aggregate sums device energy. Publishing a plant total and a WP 1
total would count the same heat twice. The WPM already sums every heat pump. A single WPL is that sum.
Compressor and NHZ bits of register 2503 still feed the plant binary roles.

There is no live electric-power register. `hp_power_electric` and `hp_power_thermal` are not published,
so `hp_cop_live` is not derived. `hp_cop_total` is derived on the aggregate when both energy totals are
present. Electric power for this machine comes from the bridge or from a meter.

Lifetime runtime is not published. Register 535 is an unlabeled hour counter (`fts.txt:274`). Registers
3517–3522 are capped at 999 h (`fts.txt:1508`) and wrap, so they are not a lifetime total. NHZ heat
amounts (3507–3510) are not added to the compressor heat totals.

A total is the MWh register times 1000 plus the kWh register. The pair shares one object name; the kWh
register stops at 999 and the next register is MWh (`fts.txt:1493`–`1494`). Both words are in the single
read 3501–3516. A new total lower than the last accepted total is dropped for that cycle and is not
stored as 0. A combined heating-plus-hot-water total is published only when both parts are present.

The device serial and the config-entry unique_id come from the config entry id, not from the host. A
second entry for the same host, port and unit is rejected. Scan interval default 60 s, minimum 30 s. The
WPM energy counters move slowly, and another integration may poll the same ISG. Three short reads and a
0.2 s gap finish in about a second; 30 s stays above the 20 s cycle timeout and leaves the ISG idle.

| Role | Register | Evidence |
|---|---|---|
| `hp_temperature_outdoor` | 507, type 2, −60…80 °C | `fts.txt:246` |
| `hp_temperature_flow` | 513, type 2, plant flow | `fts.txt:252` |
| `hp_temperature_return` | 516, type 2, 0…90 °C | `fts.txt:255` |
| `hp_temperature_storage` | 518 buffer, type 2, 0…90 °C. 529 is solar and is not used | `fts.txt:257` |
| `hp_temperature_dhw` | 522, type 2, 10…65 °C | `fts.txt:261` |
| `hp_temperature_source` | 536, type 2 | `fts.txt:275` |
| `hp_volume_flow` | 521, type 2, l/min × 60 = L/h | `fts.txt:260` |
| `hp_compressor_running` | 2501 B6, or 2503 B0–B5 | `fts.txt:1442`, `fts.txt:1455` |
| `hp_operating_mode` | 2501 B9 defrost, B8 cooling, B5 hot water, B4 heating, else off. Summer (B7) is off | `fts.txt:1440`–`1445` |
| `hp_aux_heater_active` | 2501 B3, or 2503 B12–B13 | `fts.txt:1439`, `fts.txt:1467` |
| `hp_energy_thermal_heating_today` / `_total` | 3501 day; 3502 kWh + 3503 MWh | `fts.txt:1492`–`1494` |
| `hp_energy_thermal_dhw_today` / `_total` | 3504 day; 3505 kWh + 3506 MWh | `fts.txt:1495`–`1497` |
| `hp_energy_electric_heating_today` / `_total` | 3511 day; 3512 kWh + 3513 MWh | `fts.txt:1502`–`1504` |
| `hp_energy_electric_dhw_today` / `_total` | 3514 day; 3515 kWh + 3516 MWh | `fts.txt:1505`–`1507` |
| `hp_energy_thermal_total` / `_today` and `hp_energy_electric_total` / `_today` | heating + hot water, only when both parts exist | derived from the rows above |

## Planned

Wallboxes (e.g. Fronius Wattpilot) as further S-INV instances. Heat-pump manufacturers connected so far are
Bosch/Buderus via EMS-ESP, Stiebel Eltron via the ISG, and any other heat pump through the bridge. Further
manufacturers fill the same role family.

## Versioning

The major version is part of every unique_id (`sinv:1:`) and of the `sinv_contract` attribute. New roles are added
without a version change. Renaming or removing a role or changing a unit or sign requires a new major version with a
transition period in which both versions are published.

## Manufacturer coverage

| Manufacturer | Connection | Roles published |
|---|---|---|
| Anker Solix | Cloud (account + MQTT) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN` (Solarbank 3), `power_inverter_ac_output`, `voltage_grid`, `frequency_grid` (Solarbank 3), `state_grid_export_allowed`, `state_curtailment`, `battery_soc`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `power_grid_to_battery`, `power_solar_to_battery` (derived where the device does not report it), `power_grid_to_house`, `power_battery_to_house`, `power_solar_to_house` (derived, solarbanks), `battery_pack_soc_NN`, `temperature_battery_pack_NN`, `power_grid_import`, `power_grid_export` (smart meter; `power_grid` of the installation is derived from both), `power_house`, `energy_solar_total`, `energy_battery_charge_total`, `energy_battery_discharge_total`, `energy_grid_import_total`, `energy_grid_export_total`, `energy_house_total`, `energy_solar_today`, `energy_house_today` |
| Fronius | Local network (Solar API v1, IP address only; optional SunSpec Modbus TCP on GEN24, read only) | `power_solar`, `power_solar_mppt_NN` (derived V×I), `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `power_house`, `battery_soc`, `capacity_battery`, `temperature_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total` (meter at the grid point); with Modbus TCP: `energy_solar_total`, measured `power_solar_mppt_NN`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Zendure SolarFlow (zenSDK) | Local network (zenSDK HTTP API, IP address only) | `power_solar`, `power_solar_mppt_NN`, `power_inverter_ac_output`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `battery_soc`, `battery_pack_soc_NN`, `temperature_battery_pack_NN`, `temperature_inverter` |
| Hoymiles via OpenDTU | Local network (OpenDTU REST API) | per inverter: `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_today`, `energy_solar_total` |
| Hoymiles DTU / HMS-W | Local network (DTU protobuf, hoymiles-wifi) | per inverter: `power_solar` (sum of ports), `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_today`, `energy_solar_total` |
| Hoymiles via AhoyDTU | Local network (AhoyDTU REST API, read without password) | per inverter: `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_today`, `energy_solar_total` |
| KOSTAL PLENTICORE G2 | Local network (Modbus TCP, port 1502, unit 71, read only) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `power_house`, `power_solar_to_house`, `power_grid_to_house`, `power_battery_to_house`, `energy_house_total`, `energy_solar_total`, `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| SolaX Hybrid / IES | Local network (Modbus TCP of the Pocket WiFi+LAN module, port 502, unit 1, read only) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house` (derived), `energy_solar_total`, `energy_solar_today`, `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Sungrow Hybrid (SH) | Local network (Modbus TCP of the LAN port or WiNet-S/WiNet-S2 Ethernet, port 502, unit 1, read only) | `power_solar`, `power_solar_mppt_NN` (derived), `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house`, `energy_solar_total`, `energy_solar_today`, `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Huawei SUN2000 | Local network (Modbus TCP of the SDongle, port 502, unit 1, or the inverter's access point, port 6607, unit 0; read only) | `power_solar`, `power_solar_mppt_NN` (derived), `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today` (without battery), `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house` (derived), `battery_soc`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Solakon ONE | Local network (Modbus TCP, port 502, unit 1, read only) | `power_solar`, `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `power_house` (derived), `battery_soc`, `battery_soh`, `temperature_battery`, `capacity_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total` |
| Deye three-phase hybrid | Local network (Solarman V5 port 8899 with logger serial, or Modbus TCP port 502, unit 1, read only; device types 0x0500 and 0x0600) | `power_solar` (sum of MPPT 1–4), `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_today`, `power_grid`, `power_grid_import`, `power_grid_export`, `energy_grid_import_total`, `energy_grid_export_total`, `energy_grid_import_today`, `energy_grid_export_today`, `power_house`, `energy_house_total`, `energy_house_today`, `battery_soc`, `battery_soh`, `temperature_battery`, `power_battery`, `power_battery_charge`, `power_battery_discharge`, `energy_battery_charge_total`, `energy_battery_discharge_total`, `energy_battery_charge_today`, `energy_battery_discharge_today` |
| Deye single-phase hybrid | Same transports; device type 0x0300; reads of at most 16 registers | `power_solar` (sum of MPPT 1–2), `power_solar_mppt_NN`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today`, `energy_grid_export_total`, `energy_grid_import_today`, `energy_grid_export_today`, `battery_soc`, `temperature_battery`, `energy_battery_charge_total`, `energy_battery_discharge_total`, `energy_battery_charge_today`, `energy_battery_discharge_today` |
| Deye string | Same transports; device type 0x0200 | `power_solar`, `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today`, `energy_grid_import_total`, `energy_grid_export_total`, `energy_grid_import_today`, `energy_grid_export_today`, `energy_house_total`, `energy_house_today` |
| Deye microinverter | Same transports; device type 0x0400 | `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today` |
| Solplanet | Local network (Modbus TCP, port 502 or Ai-logger 9999, unit 3 or 239, input registers, read only) | `power_solar` (sum of MPPT V×I), `power_solar_mppt_NN` (derived), `voltage_solar_mppt_NN`, `current_solar_mppt_NN`, `power_inverter_ac_output`, `voltage_grid`, `frequency_grid`, `temperature_inverter`, `energy_solar_total`, `energy_solar_today`, `battery_soc`, `battery_soh`, `temperature_battery` (battery roles only while battery status is not "not available") |
| maxxisun MaxxiCharge | Local webhook (CCU pushes JSON, firmware .44 to .48, read only) | `power_solar`, `power_solar_mppt_NN`, `power_inverter_ac_output`, `power_grid`, `power_grid_import`, `power_grid_export`, `power_house` (derived), `power_battery`, `power_battery_charge`, `power_battery_discharge` (derived), `battery_soc`, `battery_pack_soc_NN`, `temperature_inverter` |
| Bosch/Buderus | Local EMS-ESP HTTP, read only, no token | every S-INV HP role the gateway reports; see the EMS-ESP table under S-INV HP. COP and day counters are derived |
| Stiebel Eltron | Local ISG Modbus TCP, function 04 only, port 502, unit 1 | the plant roles in the Stiebel table under S-INV HP. No electric power, so live COP is absent; `hp_cop_total` is derived from the energy totals. Day counters come from the ISG |
| Other heat pump | Bridge to an existing Home Assistant integration, read only | the roles the user maps; units converted to the contract. COP and unmapped day counters are derived |

Fronius: one S-INV instance per inverter (IP address). Sign conventions of the Solar API are converted: `power_battery` = −`P_Akku`, `power_house` = −`P_Load`; the inverter AC energy `TOTAL_ENERGY` includes battery discharge on hybrid inverters and is therefore published as `sinv_fronius_inverter_energy_total`, not as `energy_solar_total`. A meter outside the grid point never provides grid roles.

Fronius Modbus TCP (option, on by default): S-INV walks the SunSpec model chain from the "SunS" marker at 40000 and reads model 160 (multiple MPPT, int + scale factor) from unit 1, port 502, function 0x03 only. Trackers labelled "MPPT n" give the PV lifetime energy (`energy_solar_total`, sum of their DCWH) and measured per-MPPT power; the GEN24 battery port ("StCha 3", "StDisCha 4") gives the battery energy counters, published only while both count (firmware up to 1.30 zeroes the inactive one). A model 160 without energy counters (Symo/Primo behind a Datamanager report zeros) or a closed port changes nothing and is asked again after an hour. Symo/Primo/Galvo behind a Datamanager report only `UDC`/`IDC` in `CommonInverterData`, where `UDC` is the voltage of string 1 and `IDC` the total DC current of all strings; for these devices `voltage_solar_mppt_NN`, `current_solar_mppt_NN` and `power_solar_mppt_NN` (derived) come from the Solar API archive (`Voltage_DC_String_n`/`Current_DC_String_n`, one sample per 5 minutes, requested at most every 5 minutes, samples older than 15 minutes ignored), and strings seen before read 0 W while the PV power is 0.

Zendure: one S-INV instance per device (IP address); the local zenSDK API must be switched on in the Zendure app ("Add HEMS"). `power_battery` = `outputPackPower` − `packInputPower` (+ charging), pack temperature = (`maxTemp` − 2731) / 10 °C. `temperature_inverter` = (`hyperTmp` − 2731) / 10 °C, published between −30 and 90 °C; the battery voltage `BatVolt` / 100 V (vendor value, 36–60 V) and the target and minimum state of charge (`socSet`, `minSoc` / 10 %) are vendor values; ranges guard against other scalings on other models. The AC input power stays a vendor value. Zendure reports no grid values and no energy counters; use the external grid meter for the grid roles.

Hoymiles: one S-INV instance per OpenDTU or per DTU; every microinverter behind it is its own device. A microinverter has no battery, so its AC energy is its solar energy. Inverters that are off at night read 0 W (energy counters kept) so installation totals stay available; an unreadable DTU answer is an error, never 0 W. The DTU is polled every 35 s (minimum 30 s) because DTUs suffer from frequent requests. On the DTU protobuf path a whole answer is discarded (UpdateFailed, entities unavailable for that cycle, reason logged once per consecutive series) when every inverter grid voltage is 0 or missing and every DC voltage is 0, or when one device's lifetime solar energy is below the last value accepted for that device in this session. The tolerance is 0.0005 kWh, half of the 0.001 kWh rounding step, because the source is integer Wh published to 3 decimals. A lower lifetime total becomes the new baseline only after three consecutive answers whose value does not fall below the previous discarded reading of that device; one info line records that the counter reset was accepted. A single low answer stays discarded, and a null frame does not count toward the three and breaks the series. Those last values are kept in coordinator memory only. The next valid answer is published as usual. An inverter that produces 0 W and still reports grid voltage (evening) is kept.

AhoyDTU: one S-INV instance per AhoyDTU; every enabled inverter is its own device. S-INV reads `GET /api/inverter/list` and `GET /api/inverter/id/<id>` (no password needed). Values come as lists in AhoyDTU's fixed field order; `YieldDay` is converted from Wh to kWh. Before an inverter's first answer AhoyDTU reports zeros, which are not published; an inverter that is not producing reads 0 W, energy counters kept.

KOSTAL: register map from the KOSTAL Modbus interface description rev. 2.9; float word order follows register 5. `power_battery` = −(battery current × battery voltage) (register 200 is negative while charging). House flows come from the inverter's energy manager; the powermeter total depends on the sensor position, which Modbus does not report, so it stays a vendor value. S-INV only sends read requests (function 0x03).

SolaX: register map from the SolaX Energy Storage Inverter MODBUS protocol V001.02; real-time values are input registers (function 0x04), 32-bit values low word first, at least 1 s between requests. `power_grid` = −FeedinPower (meter/CT at the grid point, positive = to grid); grid roles are hidden while the meter reports a communication error. `power_battery` = BatPowerSum (positive while charging). `power_house` = inverter on-grid output − feed-in + off-grid (EPS) output. S-INV only sends read requests (functions 0x03 and 0x04).

Sungrow: register map from the Sungrow communication protocol of residential and small industrial hybrid inverters V1.1.17; all values are input registers (function 0x04) at the documented register minus one, 32-bit values low word first, unavailable registers (0xFFFF, 0x7FFF, 0xFFFFFFFF, 0x7FFFFFFF) are skipped, at least 1 s between requests. `power_grid` = meter active power 5601 (positive = from grid); grid roles and `power_house` (load power 13008) are only valid with a smart meter connected directly to the inverter; without a meter the inverter reports them as 0, so they are published only once the meter shows power or a non-zero energy counter. Behind an iHomeManager the grid values describe the whole house (installation rule `single`). `voltage_grid` is published only in the phase-voltage range 180–280 V; line voltages are dropped, not converted. `power_battery` = −battery power 5214 (5214 is negative while charging); firmware without 5214 uses the unsigned 13022 with the direction from the charge/discharge bits of the power flow status 13001. `power_solar_mppt_NN` = MPPT voltage × current. The total output energy 5004 includes battery discharge and is therefore a vendor value, not `energy_solar_total`. S-INV only sends read requests (function 0x04).

Huawei: register map from the Huawei SUN2000MA V100R001C20 Modbus Interface Definitions; holding registers (function 0x03) at the documented address, 32-bit values high word first, at least 1 s between requests and 1 s after connecting. `power_grid` = −meter active power 37113 (positive = feeding the grid); grid roles need the meter status 37100 = normal. Register 30071 is the PV string count and 30072 the MPP tracker count. When 30072 is at least 1, lower than the string count, and the string count divides evenly, consecutive inputs share one MPPT (strings/trackers inputs each: 1+2 on MPPT 1, 3+4 on MPPT 2, and so on). The MPPT voltage is the voltage of the first input in the group, or the highest input voltage when the first reads 0 V and another input is above 0 V; the MPPT current is the sum of the input currents; `power_solar_mppt_NN` is the sum of each input's voltage times current. Those inputs are also published as vendor values `pv_input_NN_voltage` and `pv_input_NN_current`. Otherwise each string is one MPPT and no input vendor values are added. `power_solar` stays register 32064. With a LUNA2000 battery the inverter yield 32106/32114 includes battery discharge and is therefore published as `sinv_huawei_inverter_energy_total`/`_today`, not as `energy_solar_*`. Battery registers (37758 capacity, 37760 SOC, 37765 power positive while charging, 37780/37782 energy) follow the residential SUN2000 interface definitions and are read only when present. `power_house` = inverter active power − meter feed-in. S-INV only sends read requests (function 0x03).

maxxisun: one S-INV instance per CCU webhook (firmware .44 to .48). The CCU pushes JSON; S-INV never writes to the CCU. `power_grid` = `Pr` (positive = import). `power_house` = `Pccu + Pr`, unclamped. `power_battery` = `PV_power_total - Pccu` (positive while charging). `battery_soc` is the top-level `SOC`, otherwise the plain mean of pack `batterySOC`. `temperature_inverter` is `convertersInfo[0].ccuTemperature`, published between -30 and 100 C. `batteryCapacity` is the current stored energy (state of energy) and is not published as a capacity. No `power_ac_net` and no energy counters.

Deye: register map from the Deye three-phase storage Modbus protocol V105.4; holding registers (function 0x03) at the documented address. Device type 0 selects the family. 0x0500 and 0x0600 are the three-phase hybrids described here. 0x0200, 0x0300 and 0x0400 are the community-map families in the next paragraph. Any other type publishes nothing. V104 AC values are 32-bit, low word first (the original register is the low word, the high word is in 687–709). PV power 672–675 and battery output power 590 stay 16-bit, 1 W on 0x0500 and 10 W on 0x0600. `power_battery` = −590 (590 is battery output power, positive while discharging). `power_grid` = meter/CT total 625/690; the protocol does not print the sign, and the community map treats positive as import. `power_house` is the load-side total 653/659 and is not treated as a meter balance. `power_ac_net` is not published. Total PV energy 534/535 is marked reserved and is not `energy_solar_total`; daily PV 529 is `energy_solar_today`. The inverter's own grid-side generation 501/504 stays a vendor value. S-INV only sends read requests (function 0x03), over Modbus TCP or a Solarman V5 frame. The logger serial is required for Solarman V5 and is redacted in diagnostics.

Deye single-phase hybrid (0x0300), string (0x0200) and microinverter (0x0400) use community register maps, still holding registers and function 0x03. The single-phase hybrid is read in blocks of at most 16 registers. `power_grid` and `power_battery` are not published: register 169 is signed but the tables disagree on the scale (1 versus 10) and do not state the sign, and register 190 is only described as usually negative while charging. `power_house` is not derived from either value. Total grid import is not published because its high word is not the same register in every table. String and micro grid power is unsigned or marked computed, so it stays unpublished; string load power has no stated direction, so `power_house` stays unpublished there too. String `power_solar` is the DC total. Micro PV power is marked computed and is not published. No `power_ac_net`, and none of these families is a balance-house vendor.

Solplanet: register map from AISWEI MB001 V2.1.3, input registers (function 0x04). The documented address drops the 3xxxx prefix and then one (31001 is PDU address 1000). Real value = gain times the raw value; NaN values in section 3.2 are missing. 32-bit values use the lower address as the high word, following the high-then-low order of every multi-byte field in section 3.6. `energy_solar_*` is PV energy 31603/31605; the inverter counters 31303/31305 stay vendor values. `power_inverter_ac_output` is active power 31371 and is not treated as grid power, because that register states no sign. Battery voltage, temperature, SOC and SOH (31617, 31621–31623) are published only while battery status 31608 is not "not available". Battery power 31619, the smart-meter power and the grid-energy registers state no sign, so `power_grid`, `power_battery` and `power_house` are not published. Solplanet is not a balance-house vendor. S-INV only sends read requests (function 0x04). The Ai-Dongle on port 8484 is not supported.

Solakon: register map from the Solakon ONE Modbus Protokoll v.02/26; holding registers (function 0x03) at the documented address, 32-bit values high word first, the documented factor divides the raw value. `power_grid` = −meter collection active power 39168 (positive = feeding the grid) while meter/CT 1 is connected (38801 = 1); grid energy = 39617 (import) and 39613 (export). The four PV inputs come from the string registers (voltage/current 39070 ff., power 39279 ff.), because the MPPT count register 39052 reports fewer trackers than there are inputs. `power_battery` = −Battery 1 power 39230 (negative while charging; not in the PDF, verified on an MQ2200-M-H against Solakon's integration and V × I); the "[Energy storage module 1]" register 39162 is not the battery of the Solakon ONE. BMS1 counts as present when 37002 reports online or when it reports a design energy and a state of health. Battery capacity and state of charge combine BMS1 and an online BMS2 (design energy, capacity-weighted SoC); without design energy the SoC of BMS1 is used and no capacity is published; with no BMS online, the device SoC register 39424 (used by Solakon's own integration) marks and describes the battery. The device's own AC output/input counters 39621/39625 stay vendor values. `power_house` = inverter active power − meter feed-in. S-INV only sends read requests (function 0x03).

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
