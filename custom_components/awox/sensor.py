"""Platform for light integration."""
from __future__ import annotations

import logging

from .awox_mesh import AwoxMesh
from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import StateType

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    DEVICE_CLASS_TIMESTAMP,
)
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key='connected_device',
        name="AwoX mesh",
        icon="mdi:bluetooth-audio",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key='last_rssi_check',
        name="AwoX mesh last RSSI check",
        device_class=DEVICE_CLASS_TIMESTAMP,
        icon="mdi:calendar-clock",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key='last_connection',
        name="AwoX mesh last connection",
        device_class=DEVICE_CLASS_TIMESTAMP,
        icon="mdi:calendar-clock",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mesh = hass.data[DOMAIN][entry.entry_id]

    entities = [AwoxMeshSensor(mesh, description) for description in SENSOR_TYPES]

    async_add_entities(entities)


class AwoxMeshSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Awesome Light."""

    def __init__(self, coordinator: AwoxMesh, description: SensorEntityDescription):

        """Initialize an AwoX MESH plug."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mesh = coordinator

        self._attr_unique_id = self._mesh.identifier + self.entity_description.key

    @property
    def device_info(self) -> DeviceInfo:
        """Get device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._mesh.identifier)},
            name='AwoX mesh',
            manufacturer='AwoX',
            model='Bluetooth Mesh',
        )

    @property
    def native_value(self) -> StateType:
        if self._mesh.state and self.entity_description.key in self._mesh.state:
            return self._mesh.state[self.entity_description.key]
        return None
