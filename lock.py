"""
Configuration:

To use the aptus_home component you will need to add the following to your
configuration.yaml file.

lock:
- aptus_home:
    host: <host>
    username: <username>
    password: <password>
"""
from __future__ import annotations

from typing import Any
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
import asyncio

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.exceptions import ConfigEntryAuthFailed

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from homeassistant.components.lock import LockEntity, PLATFORM_SCHEMA
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, CONF_HOST
from datetime import timedelta

from . import door

# The domain of your component. Should be equal to the name of your component.
_LOGGER = logging.getLogger(__name__)

DOMAIN = "aptus_home"
SCAN_INTERVAL = timedelta(seconds=120)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST): cv.string,
    vol.Optional(CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD): cv.string,
})


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
    ):

    host : str = config[CONF_HOST]
    username : str = config[CONF_USERNAME]
    password : str = config[CONF_PASSWORD]

    coordinator = Coordinator(hass, host, username, password)
    await coordinator.reset()
    await coordinator.async_config_entry_first_refresh()
    # _LOGGER.warn(f"Aptus door inital status: {coordinator.data}")

    async_add_entities([
        AptusHomeLock(coordinator),
        AptusEntry(coordinator)
        ])
    return

class Coordinator(DataUpdateCoordinator):
    client: door.DoorClient

    def __init__(self, hass: HomeAssistant, host: str, username: str, password: str):
        super().__init__(
            hass,
            _LOGGER,
            name="Aptus Home",
            update_interval=timedelta(seconds=30)
        )
        self.client = door.DoorClient(host, username, password)

    async def _async_update_data(self):
        door, battery =  await self.client.status_update()
        self._attr_state = door
        return (door, battery)

    async def reset(self):
        ok, msg = await self.client.login()
        if not ok:
            _LOGGER.fatal(f"Could not login: {msg}")
            raise ConfigEntryAuthFailed

class AptusHomeLock(CoordinatorEntity, LockEntity):
    """Representation of an apartment door lock"""
    _attr_has_entity_name = True
    _attr_translation_key = "aptus_lock"


    def __init__(self, coordinator: Coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = 'apartment_door'
        self._attr_low_battery = door.BatteryStatus.NORMAL
        self._attr_state = door.DoorStatus.UNKNOWN


    @callback
    def _handle_coordinator_update(self) -> None:
        match self.coordinator.data[1]:
            case door.BatteryStatus.LOW:
                self._attr_low_battery = True
            case door.BatteryStatus.NORMAL:
                self._attr_low_battery = False

        match self.coordinator.data[0]:
            case door.DoorStatus.UNLOCKED:
                self._attr_door_open = True
                self._attr_is_locked = False
                self._attr_is_jammed = False
                pass
            case door.DoorStatus.LOCKED:
                self._attr_door_open = False
                self._attr_is_locked = True
                self._attr_is_jammed = False
                pass
            case door.DoorStatus.JAMMED:
                self._attr_is_jammed = True
                pass
            case door.DoorStatus.UNKNOWN:
                pass
        self.async_write_ha_state()



    async def async_lock(self, **kwargs: Any) -> None:
        self._attr_is_locking = True
        self.async_write_ha_state()
        resp = await self.coordinator.client.lock()
        self._attr_is_locking = False
        self.async_write_ha_state()
        match resp:
            case door.DoorStatus.JAMMED:
                self._attr_is_jammed = True
                self._attr_is_locked = False
                pass
            case door.DoorStatus.LOCKED:
                self._attr_is_jammed = False
                self._attr_is_locked = True
            case _:
                _LOGGER.error(f"Unexpected outcome while locking: {resp}")
                pass
        self.async_write_ha_state()


    async def async_unlock(self, **kwargs: Any) -> None:
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        resp = await self.coordinator.client.unlock()
        self._attr_is_unlocking = False
        self.async_write_ha_state()
        match resp:
            case door.DoorStatus.JAMMED:
                self._attr_is_jammed = True
                self._attr_is_locked = False
                pass
            case door.DoorStatus.UNLOCKED:
                self._attr_is_locked = False
                self._attr_is_jammed = False
            case _:
                _LOGGER.error(f"Unexpected outcome while unlocking: {resp}")
                pass
        self.async_write_ha_state()


class AptusEntry(LockEntity, CoordinatorEntity):
    """Representation of entry door lock"""

    def __init__(self, coordinator: Coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = 'entry_door'
        self._attr_is_locked = True
        self._attr_is_unlocking = False
        self.door_id = '468'

    async def async_unlock(self, **kwargs: Any) -> None:
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        success = await self.coordinator.client.unlock_frontdoor()
        self._attr_is_unlocking = False
        self.async_write_ha_state()
        if success:
            _LOGGER.error("Could not unlock entry door")
            return
        self._attr_is_locked = False
        self.async_write_ha_state()
        await asyncio.sleep(3)
        self._attr_is_locking = True
        self.async_write_ha_state()
        await asyncio.sleep(2)
        self._attr_is_locking = False
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_lock(self, **kwargs: Any) -> None:
        # we can't lock this door,
        # so we just ignore it.
        pass
