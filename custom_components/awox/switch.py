"""Platform for light integration."""
from __future__ import annotations

import logging

from .awox_mesh import AwoxMesh
from typing import Any

from homeassistant.helpers.typing import StateType
from homeassistant.helpers.entity import DeviceInfo, ToggleEntity

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_MAC,

    STATE_ON,
    STATE_OFF,
    STATE_UNAVAILABLE,
)
from .const import DOMAIN, CONF_MESH_ID, CONF_MANUFACTURER, CONF_MODEL, CONF_FIRMWARE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    _LOGGER.debug('entry %s', entry.data[CONF_DEVICES])

    mesh = hass.data[DOMAIN][entry.entry_id]
    plugs = []
    for device in entry.data[CONF_DEVICES]:
        # Skip non plugs
        if 'plug' not in device['type']:
            continue
        if CONF_MANUFACTURER not in device:
            device[CONF_MANUFACTURER] = None
        if CONF_MODEL not in device:
            device[CONF_MODEL] = None
        if CONF_FIRMWARE not in device:
            device[CONF_FIRMWARE] = None

        plug = AwoxPlug(mesh, device[CONF_MAC], device[CONF_MESH_ID], device[CONF_NAME],
                          device[CONF_MANUFACTURER], device[CONF_MODEL], device[CONF_FIRMWARE])
        _LOGGER.info('Setup plug [%d] %s', device[CONF_MESH_ID], device[CONF_NAME])

        plugs.append(plug)

    async_add_entities(plugs)


class AwoxPlug(CoordinatorEntity, ToggleEntity):
    """Representation of an Awesome Light."""

    def __init__(self, coordinator: AwoxMesh, mac: str, mesh_id: int, name: str,
                 manufacturer: str, model: str, firmware: str):

        """Initialize an AwoX MESH plug."""
        super().__init__(coordinator)
        self._mesh = coordinator
        self._mac = mac
        self._mesh_id = mesh_id

        self._attr_name = name
        self._attr_unique_id = "awoxmesh-%s" % self._mesh_id

        self._manufacturer = manufacturer
        self._model = model
        self._firmware = firmware

        self._mesh.register_device(mesh_id, mac, name, self.status_callback)

        self._state = None

    @property
    def device_info(self) -> DeviceInfo:
        """Get device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=self.name,
            manufacturer=self._manufacturer,
            model=self._model.replace('_', ' '),
            sw_version=self._firmware,
            via_device=(DOMAIN, self._mesh.identifier),
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self._state is None:
            return False
        return True

    @property
    def state(self) -> StateType:
        """Return the state of the entity."""
        if self._state is None:
            return STATE_UNAVAILABLE

        return STATE_ON if self.is_on else STATE_OFF

    @property
    def is_on(self):
        """Return true if light is on."""
        return bool(self._state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the plug to turn on."""
        _LOGGER.debug("[%s] turn on", self.unique_id)
        await self._mesh.async_on(self._mesh_id)

        self.status_callback({'state': True})

    async def async_turn_off(self, **kwargs) -> None:
        """Instruct the plug to turn off."""
        _LOGGER.debug("[%s] turn off", self.unique_id)
        await self._mesh.async_off(self._mesh_id)

        self.status_callback({'state': False})

    @callback
    def status_callback(self, status) -> None:

        if 'state' in status:
            self._state = status['state']

        _LOGGER.debug('[%s][%s] Status callback: %s', self.unique_id, self.name, status)

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """No action here, update is handled by status_callback"""