"""Platform for light integration."""
from __future__ import annotations

import logging

from .awox_mesh import AwoxMesh
from typing import Any, Dict, Optional

import homeassistant.util.color as color_util
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.entity import DeviceInfo, Entity

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_RGB_COLOR,
    LightEntity,
    COLOR_MODE_ONOFF,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_RGB
)
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
    lights = []
    for device in entry.data[CONF_DEVICES]:
        # Skip non lights
        if 'light' not in device['type']:
            continue
        if CONF_MANUFACTURER not in device:
            device[CONF_MANUFACTURER] = None
        if CONF_MODEL not in device:
            device[CONF_MODEL] = None
        if CONF_FIRMWARE not in device:
            device[CONF_FIRMWARE] = None

        type_string = ''
        supported_color_modes = set()

        if 'type' in device:
            type_string = device['type']

        if 'color' in type_string:
            supported_color_modes.add(COLOR_MODE_RGB)

        if 'temperature' in type_string:
            supported_color_modes.add(COLOR_MODE_COLOR_TEMP)

        if 'dimming' in type_string:
            supported_color_modes.add(COLOR_MODE_BRIGHTNESS)

        if len(supported_color_modes) == 0:
            supported_color_modes.add(COLOR_MODE_ONOFF)

        light = AwoxLight(mesh, device[CONF_MAC], device[CONF_MESH_ID], device[CONF_NAME], supported_color_modes,
                          device[CONF_MANUFACTURER], device[CONF_MODEL], device[CONF_FIRMWARE])
        _LOGGER.info('Setup light [%d] %s', device[CONF_MESH_ID], device[CONF_NAME])

        lights.append(light)

    async_add_entities(lights)

def convert_value_to_available_range(value, min_from, max_from, min_to, max_to) -> int:

    normalized = (value - min_from) / (max_from - min_from)
    new_value = min(
        round((normalized * (max_to - min_to)) + min_to),
        max_to,
    )
    return max(new_value, min_to)


class AwoxLight(CoordinatorEntity, LightEntity):
    """Representation of an Awesome Light."""

    def __init__(self, coordinator: AwoxMesh, mac: str, mesh_id: int, name: str, supported_color_modes: set[str] | None,
                 manufacturer: str, model: str, firmware: str):
        """Initialize an AwoX MESH Light."""
        super().__init__(coordinator)
        self._mesh = coordinator
        self._mac = mac
        self._mesh_id = mesh_id

        self._attr_name = name
        self._attr_unique_id = "awoxmesh-%s" % self._mesh_id
        self._attr_supported_color_modes = supported_color_modes

        self._manufacturer = manufacturer
        self._model = model
        self._firmware = firmware

        self._mesh.register_device(mesh_id, mac, name, self.status_callback)

        self._state = None
        self._color_mode = False
        self._red = None
        self._green = None
        self._blue = None
        self._white_temperature = None
        self._white_brightness = None
        self._color_brightness = None

    @property
    def should_poll(self) -> bool:
        """Mesh triggers state update reporting."""
        return False

    @property
    def device_info(self) -> DeviceInfo:
        """Get device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=self.name,
            manufacturer=self._manufacturer,
            model=self._model.replace('_', ' '),
            sw_version=self._firmware,
            via_device=(DOMAIN, self._mesh_id),
        )

    @property
    def icon(self) -> Optional[str]:
        if 'Spot' in self._model:
            return 'mdi:wall-sconce-flat'
        return None

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
    def rgb_color(self):
        """Return color when in color mode"""
        return (
            self._red,
            self._green,
            self._blue
        )

    @property
    def color_temp(self):
        """Return the color temperature in mired."""
        if self._white_temperature is None:
            return None
        return convert_value_to_available_range(self._white_temperature, 0, int(0x7f), self.min_mireds, self.max_mireds)

    @property
    def brightness(self):
        """Return the brightness of the light."""
        if self.color_mode != COLOR_MODE_RGB:
            if self._white_brightness is None:
                return None
            return convert_value_to_available_range(self._white_brightness, int(1), int(0x7f), 0, 255)

        if self._color_brightness is None:
            return None

        return convert_value_to_available_range(self._color_brightness, int(0xa), int(0x64), 0, 255)

    @property
    def min_mireds(self):
        # 6500 Kelvin
        return 153

    @property
    def max_mireds(self):
        # 2700 Kelvin
        return 370

    @property
    def is_on(self):
        """Return true if light is on."""
        return bool(self._state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on."""
        status = {}

        _LOGGER.debug('[%s] Turn on %s', self.unique_id, kwargs)

        if ATTR_RGB_COLOR in kwargs:
            rgb = kwargs[ATTR_RGB_COLOR]
            await self._mesh.async_set_color(self._mesh_id, rgb[0], rgb[1], rgb[2])
            status['red'] = rgb[0]
            status['green'] = rgb[1]
            status['blue'] = rgb[2]
            status['state'] = True

        if ATTR_BRIGHTNESS in kwargs:
            status['state'] = True
            if self.color_mode != COLOR_MODE_RGB:
                device_brightness = convert_value_to_available_range(kwargs[ATTR_BRIGHTNESS], 0, 255, int(1), int(0x7f))
                await self._mesh.async_set_white_brightness(self._mesh_id, device_brightness)
                status['white_brightness'] = device_brightness
            else:
                device_brightness = convert_value_to_available_range(kwargs[ATTR_BRIGHTNESS], 0, 255, int(0xa), int(0x64))
                await self._mesh.async_set_color_brightness(self._mesh_id, device_brightness)
                status['color_brightness'] = device_brightness

        if ATTR_COLOR_TEMP in kwargs:
            device_white_temp = convert_value_to_available_range(kwargs[ATTR_COLOR_TEMP], self.min_mireds, self.max_mireds, 0, int(0x7f))
            await self._mesh.async_set_white_temperature(self._mesh_id, device_white_temp)
            status['state'] = True
            status['white_temperature'] = device_white_temp

        if 'state' not in status:
            await self._mesh.async_on(self._mesh_id)
            status['state'] = True

        self.status_callback(status)

    async def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        _LOGGER.debug("[%s] turn off", self.unique_id)
        await self._mesh.async_off(self._mesh_id)
        self.status_callback({'state': False})

    @callback
    def status_callback(self, status) -> None:

        if 'state' in status:
            self._state = status['state']
        if 'white_brightness' in status:
            self._white_brightness = status['white_brightness']
        if 'white_temperature' in status:
            self._white_temperature = status['white_temperature']
        if 'color_brightness' in status:
            self._color_brightness = status['color_brightness']
        if 'red' in status:
            self._red = status['red']
        if 'green' in status:
            self._green = status['green']
        if 'blue' in status:
            self._blue = status['blue']

        if 'color_mode' in status:
            supported_color_modes = self.supported_color_modes
            color_mode = COLOR_MODE_ONOFF
            if status['color_mode']:
                color_mode = COLOR_MODE_RGB
            elif COLOR_MODE_COLOR_TEMP in supported_color_modes:
                color_mode = self._attr_color_mode = COLOR_MODE_COLOR_TEMP
            elif COLOR_MODE_BRIGHTNESS in supported_color_modes:
                color_mode = self._attr_color_mode = COLOR_MODE_BRIGHTNESS
            self._attr_color_mode = color_mode

        _LOGGER.debug('[%s][%s] mode[%s] Status callback: %s', self.unique_id, self.name, self._attr_color_mode, status)

        self.async_write_ha_state()
