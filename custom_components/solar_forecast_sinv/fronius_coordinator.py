# ******************************************************************************
# @copyright (C) 2026 Zara-Toorox - Solar Forecast S-INV
# * This program is protected by a Proprietary Non-Commercial License.
# 1. Personal and Educational use only.
# 2. COMMERCIAL USE AND AI TRAINING ARE STRICTLY PROHIBITED.
# 3. Clear attribution to "Zara-Toorox" is required.
# * Full license terms: https://www.solarforecastml.com/license
# ******************************************************************************

"""Polling coordinator for Fronius inverters on the local Solar API v1. @zara"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import LOGGER
from .vendors import fronius

REQUEST_TIMEOUT = ClientTimeout(total=10)


def base_url(host: str) -> str:
    """Return the http base URL for a host or URL the user entered. @zara"""
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host


async def fetch_json(session: ClientSession, url: str) -> dict[str, Any]:
    """GET one Solar API resource and decode its JSON body. @zara"""
    async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        data = await response.json(content_type=None)
    if not isinstance(data, dict):
        raise TypeError(f"unexpected response from {url}")
    return data


async def async_probe(session: ClientSession, host: str) -> dict[str, str]:
    """Check that host speaks Solar API v1 and return the inverter identity. @zara"""
    root = base_url(host)
    version = await fetch_json(session, f"{root}{fronius.API_VERSION_PATH}")
    if version.get("APIVersion") != 1:
        raise ValueError("not a Fronius Solar API v1 device")
    api = f"{root}{version.get('BaseURL') or '/solar_api/v1/'}"
    identity = fronius.inverter_identity(
        await fetch_json(session, f"{api}{fronius.REQUESTS['inverter_info']}")
    )
    if identity is None:
        raise ValueError("no inverter reported")
    return identity


class FroniusCoordinator(DataUpdateCoordinator[dict[str, fronius.FroniusDevice]]):
    """Fetch power flow, inverter, meter and storage data in one cycle. @zara"""

    vendor = fronius

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize from the config entry. @zara"""
        seconds = entry.options.get(CONF_SCAN_INTERVAL, fronius.DEFAULT_SCAN_SECONDS)
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"S-INV Fronius {entry.data[CONF_HOST]}",
            update_interval=timedelta(seconds=seconds),
        )
        self.host: str = entry.data[CONF_HOST]
        self._session = async_get_clientsession(hass)
        self._api: str | None = None

    async def _async_update_data(self) -> dict[str, fronius.FroniusDevice]:
        try:
            if self._api is None:
                root = base_url(self.host)
                version = await fetch_json(
                    self._session, f"{root}{fronius.API_VERSION_PATH}"
                )
                self._api = f"{root}{version.get('BaseURL') or '/solar_api/v1/'}"
            info = await fetch_json(
                self._session, f"{self._api}{fronius.REQUESTS['inverter_info']}"
            )
        except (ClientError, TimeoutError, ValueError, TypeError) as err:
            raise UpdateFailed(f"Fronius at {self.host} not reachable: {err}") from err
        identity = fronius.inverter_identity(info)
        if identity is None:
            raise UpdateFailed(f"Fronius at {self.host} reported no inverter")
        keys = ("powerflow", "inverter", "meter", "storage")
        results = await asyncio.gather(
            *(
                fetch_json(
                    self._session,
                    self._api
                    + fronius.REQUESTS[key].format(device_id=identity["device_id"]),
                )
                for key in keys
            ),
            return_exceptions=True,
        )
        responses: dict[str, Any] = {"inverter_info": info}
        for key, result in zip(keys, results, strict=True):
            if isinstance(result, Exception):
                LOGGER.debug("Fronius %s request failed: %s", key, result)
                continue
            responses[key] = result
        if "powerflow" not in responses and "inverter" not in responses:
            raise UpdateFailed(f"Fronius at {self.host} returned no realtime data")
        return fronius.build_devices(responses)
