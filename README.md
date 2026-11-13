<p align="center">
  <img src="https://raw.githubusercontent.com/Zara-Toorox/SFML-S-INV/main/pictures/readme_header_sinv.jpg" alt="Solar Forecast S-INV — one inverter standard for Home Assistant" width="100%">
</p>

<h1 align="center">Solar Forecast S-INV</h1>

<p align="center">
  <strong>One Home Assistant integration for many inverters, batteries and meters —<br>with the same sensor names, units and signs for every manufacturer</strong>
</p>

<p align="center">
  <em>Pick your brand. Enter an IP or account. Done.<br>
  The sensors are ready for the Home Assistant Energy Dashboard — and with Solar Forecast STATS, one click takes them over.</em>
</p>

<p align="center">
  <a href="https://github.com/Zara-Toorox/SFML-S-INV"><img src="https://img.shields.io/badge/version-10.0.2-blue.svg" alt="Version"></a>
  <a href="https://github.com/Zara-Toorox/SFML-S-INV"><img src="https://img.shields.io/badge/status-Early%20BETA-orange.svg" alt="Early BETA"></a>
  <a href="https://hacs.xyz/"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Proprietary%20Non--Commercial-green.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.7.0%2B-41BDF5.svg" alt="Home Assistant">
</p>

> [!IMPORTANT]
> ### Documentation lives on the website
>
> **[solarforecastml.com](https://solarforecastml.com/en/)** is the authoritative source for installation, sensors, troubleshooting and release notes.
>
> **[Docs](https://solarforecastml.com/en/docs/)** · **[Bug tracker](https://solarforecastml.com/en/bugs/)** · **[Deutsch](https://solarforecastml.com/de/)**
>
> Please read the [Early BETA notes](#early-beta-notes) before you install.

<p align="center">
  <strong>Fuel my late-night ideas with a coffee? I'd really appreciate it — it keeps this project running.</strong>
</p>

<p align="center">
  <a href="https://ko-fi.com/Q5Q41NMZZY" target="_blank"><img height="36" style="border:0px;height:36px;" src="https://ko-fi.com/img/githubbutton_sm.svg" border="0" alt="Buy Me a Coffee"></a>
</p>

---

## Not another inverter integration

Every solar brand speaks a different language in Home Assistant. One calls solar power `pv_power`, another `solar_production`, a third something with Modbus registers and odd units. If you want the Energy Dashboard, a card, an automation — or later STATS / Solar Forecast ML — you first spend hours asking: *“Which sensor do I need?”*

S-INV ends that.

You choose the manufacturer, pick how it connects (local network or, for Anker, your account), enter the details — and S-INV creates **one clear set of sensors** that look the same on every supported system. Solar power is always `sensor.sinv_power_solar`. Battery charge is always `sensor.sinv_battery_soc`. Grid import is always positive the same way.

That is the difference. Not one more brand app inside Home Assistant — a **shared language** for solar hardware.

**What no other inverter integration offers today:**

- **One name for the same thing, on every brand.** `power_solar_mppt_01` means the same on Anker, Fronius, Sungrow and the rest. Cards, YAML and automations become shareable.
- **Setup that matches how people think.** Manufacturer → connection → credentials. No hunting through entity lists for “the right DC power.”
- **An open data contract.** Other integrations and developers can rely on [CONTRACT.md](CONTRACT.md) without knowing your hardware.
- **Built for Home Assistant first.** S-INV creates the right solar, grid and battery sensors for the Energy Dashboard so you can take them over directly — no helper recipes.
- **One click with Solar Forecast STATS.** With STATS installed, assignment is a single click (compare, tick, undo). Solar Forecast ML is optional; S-INV does not depend on it.

---

## A real day with S-INV

Take a mixed home setup — Fronius with battery and smart meter, or several Anker Solarbanks, or Sigenergy next to a balcony box. Without S-INV you open every brand integration, hunt for the right entity among dozens of names, build helpers or YAML for house consumption and daily totals, then type those sensors one by one into the energy dashboard, SFML and STATS. Testers described that as hours of fiddling.

With S-INV you choose the manufacturer and connection, enter an IP or login — and the sensors are there under one vocabulary (`sensor.sinv_…`). House consumption, daily counters and energy flows come with the package. Those sensors are meant for the **Home Assistant Energy Dashboard** itself: you take them over directly. If you also run **Solar Forecast STATS**, the mapping is literally one click — compare, tick, undo. Solar Forecast ML can use the same roles later; it is optional. Neighbours with a different inverter can still reuse your automation, because `sensor.sinv_energy_solar_total` means the same thing everywhere.

That story is what users kept asking for in the [simon42 S-INV thread](https://community.simon42.com/t/solar-forecast-ml-wechselrichter-integration-solar-forecast-ml-s-inv/93929): *which sensor do I need?* — and what early testers praised as “IP, save, done.” S-INV is Early BETA; some brands still need value checks, and Home Assistant history stays on the old sensor until you migrate carefully.

---

## What it does

S-INV is a Home Assistant integration (domain `solar_forecast_sinv`). For each system you add, it:

1. Talks to the device the way that manufacturer expects (local Modbus/API for most brands; Anker via cloud + MQTT).
2. Publishes **contract roles** — the same ids, units and signs for every vendor ([CONTRACT.md](CONTRACT.md)).
3. Publishes useful **vendor-specific** extras under a clear prefix (for example `sinv_anker_…`) when the brand has more to offer.
4. Builds a device **“S-INV Anlage”** that sums all your S-INV systems into one set of totals for the energy dashboard.

Most connections are **local and read-only**. Anker is the exception that needs an account; its control entities come from the upstream Solix integration.

Voltage and current per MPPT, where the device provides them, are gold for tools like Solar Forecast ML — shade, string health, temperature effects — without you wiring those sensors by hand.

---

## Why it is special (in plain words)

| | Usual brand integration | S-INV |
|---|---|---|
| **Sensor names** | Different every time | Same roles for every manufacturer |
| **Missing everyday values** | You build helpers yourself | House load, daily counters and flows included (derived values marked) |
| **Several devices** | Separate worlds | One **S-INV Anlage** for totals, plus each device |
| **Your job** | Guess which entity is solar / battery / grid | Choose brand and connect |
| **Home Assistant Energy Dashboard** | Manual hunt per brand | Correct sensors ready to take over directly |
| **Solar Forecast STATS** | Manual sensor quiz | One-click assignment (compare, tick, undo) |
| **Solar Forecast ML** | Long sensor setup | Optional — can detect S-INV when you use it |
| **Wrong data** | Silent zeros and odd signs | Prefer missing over wrong where the contract is unclear |
| **Other integrations** | Hard-code brand quirks | Open [CONTRACT.md](CONTRACT.md) |

You are not locking yourself into SFML. You are getting a **neutral solar vocabulary** in Home Assistant. The suite is optional; the standard is the point.

---

## Highlights

| | What it does for you |
|---|---|
| **One standard** | Identical entity ids, units and signs (grid power positive = import, battery power positive = charging). Full rules in [CONTRACT.md](CONTRACT.md). |
| **Mostly local** | Apart from Anker, systems are read on your LAN — no cloud account required. |
| **Read only (local brands)** | Local connections only read values; S-INV does not change inverter settings there. |
| **S-INV Anlage** | Combines every S-INV entry into one set of totals — ready for the energy dashboard. |
| **Mix brands** | Fronius on the roof, Hoymiles on the balcony, Zendure in the shed — one vocabulary. |
| **Heat pumps (S-INV HP)** | Optional aggregate beside the inverter installation (e.g. Bosch/Buderus via EMS-ESP, Stiebel via ISG, M-TEC via Modbus TCP, or a bridge to an existing HP integration). |
| **Energy Dashboard ready** | Creates the solar / grid / battery sensors Home Assistant expects so you can adopt them straight away. |
| **One click with STATS** | Solar Forecast STATS can assign S-INV roles in one click (compare, tick, undo). SFML remains optional. |
| **Honest values** | Prefer a missing reading over a fake zero or unclear battery sign; derived flows are labelled as derived. |

---

## Is it right for you?

**Good fit if:** you want clean solar / battery / grid sensors for the Home Assistant Energy Dashboard, you are tired of brand-specific entity chaos, or you use STATS (one-click takeover) — with or without Solar Forecast ML.

**Required:** a supported inverter, battery or meter connection (see table below), Home Assistant **2026.7.0** or newer, and a bit of patience while Early BETA settles.

**Not ideal yet if:** you need a finished, frozen API for safety-critical automations, or your exact device is still marked *protocol* and you cannot compare values with the manufacturer app for the first days.

---

## Supported systems

Status: **tested** = runs on real devices; **protocol** = built from documentation / test data, waiting for tester feedback.

| Manufacturer | Connection | Status |
|---|---|---|
| **Anker Solix** (Solarbank 1–3, meters, PPS, X1, …) | Cloud + MQTT | tested |
| **Fronius** (Symo GEN24 tested; other Solar API) | Local Solar API (+ optional Modbus on GEN24) | tested (GEN24) |
| **Sungrow** hybrid SH / MG families | Modbus TCP | tested |
| **Zendure** SolarFlow family | Local zenSDK | protocol |
| **Hoymiles** via OpenDTU / AhoyDTU / DTU | Local | protocol |
| **KOSTAL** PLENTICORE G2 | Modbus TCP | protocol |
| **SolaX** Hybrid / IES / ULTRA | Modbus TCP | protocol |
| **Huawei** SUN2000 + LUNA2000 | Modbus TCP | protocol |
| **Solakon** ONE | Modbus TCP | protocol |
| **Deye** hybrid / string / micro | Solarman V5 or Modbus TCP | protocol / community maps |
| **Solplanet** | Modbus TCP or Ai-Dongle (local HTTP) | protocol / community map |
| **Enphase** IQ Gateway (local token) | Local HTTPS | protocol |
| **Sigenergy** Sigen Hybrid / SigenStor | Modbus TCP | protocol |
| **Maxxisun** MaxxiCharge | Local webhook from CCU | protocol |

Grid import/export need a meter as described in each manufacturer’s setup dialog. Missing device or odd behaviour? Report it with a diagnostics file — testers unlock new brands.

---

## What you see

<!-- Screenshots: add when ready; paths under pictures/ like SFML README -->

<p align="center"><sub>Place product screenshots here (setup flow, S-INV Anlage, energy dashboard) — same layout pattern as the SFML README.</sub></p>

---

## Installation

**Via HACS (recommended)**

1. HACS → Integrations → Custom repositories
2. Add `https://github.com/Zara-Toorox/SFML-S-INV` as category *Integration*
3. Install **Solar Forecast S-INV**
4. Restart Home Assistant
5. Settings → Devices & Services → Add **Solar Forecast S-INV**

**Manually:** copy `custom_components/solar_forecast_sinv` into `config/custom_components/` and restart.

**Setup:** choose manufacturer and connection → enter IP (or Anker account) → S-INV checks the link before it saves. Repeat for further systems; **S-INV Anlage** appears automatically.

Polling interval is in each entry’s options.

---

## Energy dashboard

S-INV creates the correct sensors for the Home Assistant Energy Dashboard. It does not overwrite your dashboard settings automatically (that would double-count). After setup, a one-time notification lists the sensors to take over under Settings → Dashboards → Energy.

With **Solar Forecast STATS**, you can assign those same roles in **one click** (compare current vs S-INV, tick what to write, undo if needed). You do not need Solar Forecast ML for that.

| In the energy dashboard | Sensor |
|---|---|
| Grid consumption | `sensor.sinv_energy_grid_import_total` |
| Return to grid | `sensor.sinv_energy_grid_export_total` |
| Solar production | `sensor.sinv_energy_solar_total` |
| Battery in / out | `sensor.sinv_energy_battery_charge_total` / `_discharge_total` |
| Grid / solar / battery power | `sensor.sinv_power_grid`, `sensor.sinv_power_solar`, charge & discharge power |
| Battery state of charge | `sensor.sinv_battery_soc` |

Use the **installation** sensors only — not each device’s counters on top. Daily counters (`*_today`) are for automations; do not add them to the energy dashboard.

---

## Early BETA notes

- Not every manufacturer has run on a real device yet. Compare values with the manufacturer app for the first days on *protocol* rows.
- Breaking changes are possible until release (entity names, contract, setup). An update may require removing and re-adding an entry.
- Do not rely on S-INV yet for safety-critical or costly automations (for example grid charging) until your setup has been stable.
- Some devices allow only a few parallel Modbus/API clients — other integrations on the same box can cause gaps.
- Anker control functions can change settings; other manufacturers stay read-only.
- Report problems at [solarforecastml.com/en/bugs](https://www.solarforecastml.com/en/bugs) with the diagnostics file (check serials before sharing publicly).

---

## Documentation and developers

- Docs: https://www.solarforecastml.com/en/docs
- Bugs: https://www.solarforecastml.com/en/bugs
- Data contract: [CONTRACT.md](CONTRACT.md) — machine-readable roles in `custom_components/solar_forecast_sinv/contract.py` (no Home Assistant imports; safe for other tools to read)

---

## Licence and credits

Proprietary Non-Commercial — free for personal and educational use. See [LICENSE](LICENSE).

**Developer:** [Zara-Toorox](https://github.com/Zara-Toorox)

Anker Solix connection based on [ha-anker-solix](https://github.com/thomluther/ha-anker-solix) by Thomas Luther (MIT) — see [LICENSE-ha-anker-solix](LICENSE-ha-anker-solix). Hoymiles DTU uses [hoymiles-wifi](https://github.com/suaveolent/hoymiles-wifi) (MIT).

S-INV is a private project. It is discussed in independent communities; none of them belongs to the project. The website is the authoritative source. Thanks to everyone testing and reporting — your feedback shapes every release.

[Help centre](https://solarforecastml.com/en/docs/) · [Bug tracker](https://solarforecastml.com/en/bugs/) · [Contact](https://solarforecastml.com/en/contact/)
