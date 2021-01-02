"""Platform for light integration."""
import logging

from .awox_mesh import AwoxMesh
from typing import Any, Dict, Optional

import homeassistant.util.color as color_util
from homeassistant.helpers.typing import StateType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ATTR_WHITE_VALUE,
    LightEntity,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    SUPPORT_WHITE_VALUE
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
from .const import DOMAIN, CONF_MESH_ID, CONF_MANUFACTURER, CONF_MODEL, CONF_FIRMWARE, CONF_SUPPORTED_FEATURES

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

        # No supported_features defined try to extract them from `type`
        if 'supported_features' not in device:
            type_string = ''
            supported_features = 0
            if 'type' in device:
                type_string = device['type']

            if 'color' in type_string:
                supported_features |= SUPPORT_COLOR
            if 'dimming' in type_string:
                supported_features |= SUPPORT_BRIGHTNESS
            if 'temperature' in type_string:
                supported_features |= SUPPORT_COLOR_TEMP
            # if 'white' in type_string:
            #     supported_features |= SUPPORT_WHITE_VALUE

            device[CONF_SUPPORTED_FEATURES] = supported_features

        light = AwoxLight(mesh, device[CONF_MAC], device[CONF_MESH_ID], device[CONF_NAME], device[CONF_SUPPORTED_FEATURES],
                          device[CONF_MANUFACTURER], device[CONF_MODEL], device[CONF_FIRMWARE])
        _LOGGER.info('setup entry [%d] %s', device[CONF_MESH_ID], device[CONF_NAME])

        lights.append(light)

    async_add_entities(lights)
    await mesh.async_refresh()


class AwoxLight(CoordinatorEntity, LightEntity):
    """Representation of an Awesome Light."""

    def __init__(self, coordinator: AwoxMesh, mac: str, mesh_id: int, name: str, supported_features: int, manufacturer: str, model: str, firmware: str):
        """Initialize an AwoX MESH Light."""
        super().__init__(coordinator)
        self._mesh = coordinator
        self._mac = mac
        self._mesh_id = mesh_id
        self._name = name
        self._supported_features = supported_features

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
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Get device specific attributes."""
        return (
            {
                "identifiers": {(DOMAIN, self.unique_id)},
                "name": self.name,
                "manufacturer": self._manufacturer,
                "model": self._model,
                "sw_version": self._firmware,
            }
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
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return "awoxmesh-%s" % self._mesh_id

    @property
    def hs_color(self):
        """Return color when in color mode"""

        if not self._color_mode:
            return None

        return color_util.color_RGB_to_hs(*[
            self._red,
            self._green,
            self._blue
        ])

    @property
    def color_temp(self):
        """Return the color temperature in mired."""
        if self._white_temperature is None:
            return None
        return int(self._white_temperature)

    @property
    def white_value(self):
        """Return the white property (white brightness)."""
        if self._white_brightness is None:
            return None
        return int(int(self._white_brightness) / int(0x7f) * 255)

    @property
    def brightness(self):
        """Return the brightness of the light."""
        if not self._color_mode and not self._supported_features & SUPPORT_WHITE_VALUE:
            if self._white_brightness is None:
                return None
            return int(int(self._white_brightness) / int(0x7f) * 255)

        if self._color_brightness is None:
            return None

        min_device = int(0xa)
        max_device = int(0x64)
        max_ha = 255
        return int((int(self._color_brightness) - min_device) / (max_device - min_device) * max_ha)

    @property
    def min_mireds(self):
        return 1

    @property
    def max_mireds(self):
        return int(0x7f)

    @property
    def is_on(self):
        """Return true if light is on."""
        return bool(self._state)

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on."""
        supported_features = self._supported_features
        status = {}

        _LOGGER.debug('[%s] Turn on %s', self.unique_id, kwargs)

        if ATTR_HS_COLOR in kwargs and supported_features & SUPPORT_COLOR:
            hs_color = kwargs[ATTR_HS_COLOR]
            rgb = color_util.color_hsv_to_RGB(hs_color[0], hs_color[1], 100)
            await self._mesh.async_set_color(self._mesh_id, rgb[0], rgb[1], rgb[2])
            status['state'] = True
            status['red'] = rgb[0]
            status['green'] = rgb[1]
            status['blue'] = rgb[2]

        if ATTR_BRIGHTNESS in kwargs and supported_features & SUPPORT_BRIGHTNESS:
            if not self._color_mode and not supported_features & SUPPORT_WHITE_VALUE:
                min_device = int(1)
                max_device = int(0x7f)
                brightness_normalized = kwargs.get(ATTR_BRIGHTNESS) / 255
                device_brightness = min(
                    round(brightness_normalized * max_device),
                    max_device,
                )
                device_brightness = max(device_brightness, min_device)
                await self._mesh.async_set_white_brightness(self._mesh_id, device_brightness)
                status['state'] = True
                status['white_brightness'] = device_brightness
            else:
                min_device = int(0xa)
                max_device = int(0x64)
                max_ha = 255
                brightness_normalized = kwargs.get(ATTR_BRIGHTNESS) / max_ha
                device_brightness = min(
                    round((brightness_normalized * (max_device - min_device)) + min_device),
                    max_device,
                )
                device_brightness = max(device_brightness, min_device)
                await self._mesh.async_set_color_brightness(self._mesh_id, device_brightness)
                status['state'] = True
                status['color_brightness'] = device_brightness

        if ATTR_COLOR_TEMP in kwargs and supported_features & SUPPORT_COLOR_TEMP:
            max_device = int(0x7f)
            max_hass = self.max_mireds
            brightness_normalized = kwargs[ATTR_COLOR_TEMP] / max_hass
            device_white_temp = min(
                round(brightness_normalized * max_device),
                max_device,
            )
            # Make sure the brightness is not rounded down to 0
            device_white_temp = max(device_white_temp, self.min_mireds)
            await self._mesh.async_set_white_temperature(self._mesh_id, device_white_temp)
            status['state'] = True
            status['white_temperature'] = device_white_temp

        if ATTR_WHITE_VALUE in kwargs and supported_features & SUPPORT_WHITE_VALUE:
            max_device = int(0x7f)
            max_hass = 255
            brightness_normalized = kwargs[ATTR_WHITE_VALUE] / max_hass
            device_brightness = min(
                round(brightness_normalized * max_device),
                max_device,
            )
            # Make sure the brightness is not rounded down to 0
            device_brightness = max(device_brightness, 1)
            await self._mesh.async_set_white_brightness(self._mesh_id, device_brightness)
            status['state'] = True
            status['white_brightness'] = device_brightness

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
        _LOGGER.debug('[%s][%s] Status callback: %s', self.unique_id, self.name, status)

        if 'state' in status:
            self._state = status['state']
        if 'color_mode' in status:
            self._color_mode = status['color_mode']
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
        self.async_write_ha_state()
