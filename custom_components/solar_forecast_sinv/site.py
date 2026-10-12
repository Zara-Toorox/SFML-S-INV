# ******************************************************************************
# @copyright (C) 2026 Zara-Toorox - Solar Forecast S-INV
# * This program is protected by a Proprietary Non-Commercial License.
# 1. Personal and Educational use only.
# 2. COMMERCIAL USE AND AI TRAINING ARE STRICTLY PROHIBITED.
# 3. Clear attribution to "Zara-Toorox" is required.
# * Full license terms: https://www.solarforecastml.com/license
# ******************************************************************************

"""S-INV installation ("S-INV Anlage"): system entities sinv_<role> over all devices. @zara

One config entry of its own owns the system entities, so they survive adding or
removing inverter instances. Each system entity follows the device entities of its
role (found through the entity registry by unique_id) and combines them by the
aggregation rule of the contract. A missing device value makes the system value
unavailable, so totals never drop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import SOURCE_SYSTEM, ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import contract
from .const import CONF_VENDOR, DOMAIN
from .entity import async_convert_draft_system_entries, async_reclaim_system_ids

VENDOR_SITE = "site"
SITE_UNIQUE_ID = "sinv_site"
SITE_TITLE = "S-INV Anlage"
SOURCES_ATTR = "sinv_sources"
AGGREGATION_ATTR = "sinv_aggregation"
_FLOW_STARTED = f"{DOMAIN}_site_flow_started"
_INDEX = re.compile(r"^sinv_[a-z]{2}(\d\d)_")


@dataclass(frozen=True)
class Source:
    """A device entity feeding a system entity. @zara"""

    entity_id: str
    serial: str
    index: int


def aggregate(
    rule: str, values: list[float | None], weights: list[float | None] | None = None
) -> float | None:
    """Combine device values by rule; any missing value gives None. @zara"""
    if not values:
        return None
    if rule == contract.AGG_SINGLE:
        return values[0]
    if any(value is None for value in values):
        return None
    if rule == contract.AGG_SUM:
        return sum(values)
    if rule == contract.AGG_SOC:
        if (
            weights
            and len(weights) == len(values)
            and all(w is not None and w > 0 for w in weights)
        ):
            return sum(v * w for v, w in zip(values, weights, strict=True)) / sum(
                weights
            )
        return sum(values) / len(values)
    return None


def aggregate_state(rule: str, states: list[bool | None]) -> bool | None:
    """Combine on/off device states: any (curtailment) or all (export allowed). @zara"""
    if not states or any(state is None for state in states):
        return None
    return any(states) if rule == contract.AGG_ANY else all(states)


def collect_sources(entities) -> dict[str, list[Source]]:
    """Device entities per role with a system entity, ordered by device index. @zara"""
    sources: dict[str, list[Source]] = {}
    for entry in entities:
        if entry.platform != DOMAIN or entry.disabled_by is not None:
            continue
        parsed = contract.parse_unique_id(entry.unique_id)
        if (
            not parsed
            or not parsed.get("role")
            or parsed["serial"] == contract.SITE_SERIAL
        ):
            continue
        role = parsed["role"]
        if not contract.has_system_entity(role):
            continue
        match = _INDEX.match(entry.entity_id.split(".", 1)[1])
        index = int(match.group(1)) if match else 99
        sources.setdefault(role, []).append(
            Source(entry.entity_id, parsed["serial"], index)
        )
    for items in sources.values():
        items.sort(key=lambda source: (source.index, source.entity_id))
    if (
        "power_grid" not in sources
        and "power_grid_import" in sources
        and "power_grid_export" in sources
    ):
        sources["power_grid"] = [
            *sources.get("power_grid_import", [])[:1],
            *sources.get("power_grid_export", [])[:1],
        ]
    return sources


def _float(state: Any) -> float | None:
    try:
        return float(state.state)
    except (AttributeError, TypeError, ValueError):
        return None


def _onoff(state: Any) -> bool | None:
    value = getattr(state, "state", None)
    if value == "on":
        return True
    if value == "off":
        return False
    return None


@callback
def async_ensure_site_entry(hass: HomeAssistant) -> None:
    """Create the installation entry once, when the first device instance starts. @zara"""
    if any(
        entry.unique_id == SITE_UNIQUE_ID
        for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=True)
    ) or hass.data.get(_FLOW_STARTED):
        return
    hass.data[_FLOW_STARTED] = True
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_SYSTEM}, data={CONF_VENDOR: VENDOR_SITE}
        )
    )


def site_device_info() -> DeviceInfo:
    """Device of the installation. @zara"""
    return DeviceInfo(
        identifiers={(DOMAIN, contract.SITE_SERIAL)},
        translation_key="site",
        manufacturer="S-INV",
        model="Installation",
    )


async def async_setup_site_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    domain: str,
) -> None:
    """Create system entities for roles with device sources, now and when new ones appear. @zara"""
    async_convert_draft_system_entries(hass)
    async_reclaim_system_ids(hass)
    registry = er.async_get(hass)
    known: set[str] = set()

    @callback
    def refresh(_event: Event | None = None) -> None:
        roles = set(collect_sources(registry.entities.values()))
        # system entries converted from first-draft ids still belong to the device
        # entry until this entry adopts them, so the whole registry is scanned
        for item in registry.entities.values():
            parsed = (
                contract.parse_unique_id(item.unique_id)
                if item.platform == DOMAIN
                else None
            )
            if (
                parsed
                and parsed.get("role")
                and parsed["serial"] == contract.SITE_SERIAL
            ):
                roles.add(parsed["role"])
        new = [
            (SiteBinarySensor if domain == "binary_sensor" else SiteSensor)(role)
            for role in sorted(roles)
            if role not in known
            and contract.system_domain(role) == domain
            and contract.has_system_entity(role)
        ]
        known.update(entity.role for entity in new)
        if new:
            async_add_entities(new)

    refresh()
    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, refresh)
    )


class _SiteEntity:
    """Shared behaviour of system entities. @zara"""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, role: str) -> None:
        """Bind to a role. @zara"""
        spec, channel = contract.split_role(role)
        self.role = role
        self._rule = contract.aggregation(role)
        self._sources: list[Source] = []
        self._capacity: dict[str, str] = {}
        self._unsub_states = None
        self._attr_unique_id = contract.system_unique_id(role)
        self._attr_translation_key = f"sinv_{spec.base}"
        self._attr_translation_placeholders = (
            {"nn": f"{channel:02d}"} if channel is not None else {}
        )
        self._attr_device_info = site_device_info()

    def add_to_platform_start(self, hass, platform, parallel_updates) -> None:
        """Suggest sinv_<role> before core registers the entity. @zara"""
        registry = er.async_get(hass)
        if (
            registry.async_get_entity_id(platform.domain, DOMAIN, self.unique_id)
            is None
        ):
            self.entity_id = f"{platform.domain}.{contract.system_object_id(self.role)}"
        super().add_to_platform_start(hass, platform, parallel_updates)

    async def async_added_to_hass(self) -> None:
        """Follow the device entities of the role. @zara"""
        self._resubscribe()
        self.async_on_remove(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed
            )
        )
        self.async_on_remove(self._unsubscribe)

    @callback
    def _registry_changed(self, _event: Event) -> None:
        self._resubscribe()
        self.async_write_ha_state()

    @callback
    def _unsubscribe(self) -> None:
        if self._unsub_states is not None:
            self._unsub_states()
            self._unsub_states = None

    @callback
    def _resubscribe(self) -> None:
        registry = er.async_get(self.hass)
        all_sources = collect_sources(registry.entities.values())
        self._sources = all_sources.get(self.role, [])
        self._capacity = {
            source.serial: source.entity_id
            for source in all_sources.get("capacity_battery", [])
        }
        self._unsubscribe()
        tracked = [source.entity_id for source in self._sources]
        if self.role == "battery_soc":
            tracked.extend(self._capacity.values())
        if tracked:

            @callback
            def changed(_event: Event) -> None:
                self.async_write_ha_state()

            self._unsub_states = async_track_state_change_event(
                self.hass, tracked, changed
            )

    @property
    def available(self) -> bool:
        """Available while every source reports a value. @zara"""
        return self._current() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Contract attributes plus the device entities combined. @zara"""
        return {
            contract.ATTR_CONTRACT: contract.CONTRACT_VERSION,
            contract.ATTR_ROLE: self.role,
            AGGREGATION_ATTR: self._rule,
            SOURCES_ATTR: [source.entity_id for source in self._sources],
        }

    def _current(self):
        raise NotImplementedError


class SiteSensor(_SiteEntity, SensorEntity):
    """Numeric system value of the installation. @zara"""

    def __init__(self, role: str) -> None:
        """Set unit and classes from the contract. @zara"""
        super().__init__(role)
        spec, _channel = contract.split_role(role)
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = (
            SensorDeviceClass(spec.device_class) if spec.device_class else None
        )
        self._attr_state_class = (
            SensorStateClass(spec.state_class) if spec.state_class else None
        )

    def _current(self) -> float | None:
        if not self._sources:
            return None
        get = self.hass.states.get
        if self.role == "power_grid" and self._derived_grid():
            # no signed grid meter value: import minus export of the grid meter
            imported, exported = (
                _float(get(source.entity_id)) for source in self._sources
            )
            if imported is None or exported is None:
                return None
            return imported - exported
        values = [_float(get(source.entity_id)) for source in self._sources]
        weights = None
        if self.role == "battery_soc":
            weights = [
                _float(get(self._capacity[source.serial]))
                if source.serial in self._capacity
                else None
                for source in self._sources
            ]
        return aggregate(self._rule, values, weights)

    def _derived_grid(self) -> bool:
        registry = er.async_get(self.hass)
        roles = []
        for source in self._sources:
            entry = registry.async_get(source.entity_id)
            parsed = contract.parse_unique_id(entry.unique_id) if entry else None
            roles.append(parsed.get("role") if parsed else None)
        return roles == ["power_grid_import", "power_grid_export"]

    @property
    def native_value(self) -> float | None:
        """Aggregated value. @zara"""
        value = self._current()
        if value is None:
            return None
        return round(value, 3 if self.role.startswith(("energy", "capacity")) else 1)


class SiteBinarySensor(_SiteEntity, BinarySensorEntity):
    """On/off system state of the installation. @zara"""

    def _current(self) -> bool | None:
        if not self._sources:
            return None
        states = [
            _onoff(self.hass.states.get(source.entity_id)) for source in self._sources
        ]
        return aggregate_state(self._rule, states)

    @property
    def is_on(self) -> bool | None:
        """Aggregated state. @zara"""
        return self._current()
