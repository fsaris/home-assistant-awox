"""AwoX integration."""

import logging

from .awox_mesh import AwoxMesh
from .const import DOMAIN, CONF_MESH_NAME, CONF_MESH_PASSWORD, CONF_MESH_KEY

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    """Set up a skeleton component."""

    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up awox light via a config (flow) entry."""

    _LOGGER.info('setup config flow entry %s', entry.data)

    mesh = AwoxMesh(hass, entry.data[CONF_MESH_NAME], entry.data[CONF_MESH_PASSWORD], entry.data[CONF_MESH_KEY])

    # Make `mesh` accessible for all platforms
    hass.data[DOMAIN][entry.entry_id] = mesh

    # Setup lights
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, LIGHT_DOMAIN)
    )

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    if entry.entry_id in hass.data[DOMAIN]:
        await hass.data[DOMAIN][entry.entry_id].async_shutdown()
    return await hass.config_entries.async_forward_entry_unload(entry, LIGHT_DOMAIN)
