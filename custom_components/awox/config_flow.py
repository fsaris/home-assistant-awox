"""Config flow for AwoX MESH lights"""

from typing import Mapping, Optional
import logging
import pygatt

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD
)
from .scanner import DeviceScanner
from .const import DOMAIN, CONF_MESH_NAME, CONF_MESH_PASSWORD, CONF_MESH_KEY
from .awox_connect import AwoxConnect

_LOGGER = logging.getLogger(__name__)


def create_awox_connect_object(username, password) -> AwoxConnect:
    return AwoxConnect(username, password)


class AwoxMeshFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Awox config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    config: Optional[Mapping] = {}

    def __init__(self):
        """Initialize the UPnP/IGD config flow."""
        self._discoveries: Optional[Mapping] = None
        self._mesh_info: Optional[Mapping] = None

    async def async_step_user(self, user_input: Optional[Mapping] = None):

        return await self.async_step_awox_connect()

        # todo: fix manual connect
        _LOGGER.debug("async_step_user: user_input: %s", user_input)
        if self._mesh_info is None:
            return await self.async_step_mesh_info()

        if user_input is not None and user_input.get('mac'):

            # Ensure wanted device is available
            test_ok = await DeviceScanner.connect_device(
                user_input.get('mac'),
                self._mesh_info.get(CONF_MESH_NAME),
                self._mesh_info.get(CONF_MESH_PASSWORD),
                self._mesh_info.get(CONF_MESH_KEY)
            )

            if not test_ok:
                return self.async_abort(reason="device_not_found")

            await self.async_set_unique_id(
                self._mesh_info.get(CONF_MESH_NAME), raise_on_progress=False
            )
            return await self._async_create_entry_from_discovery(
                user_input.get('mac'),
                user_input.get('name'),
                self._mesh_info.get(CONF_MESH_NAME),
                self._mesh_info.get(CONF_MESH_PASSWORD),
                self._mesh_info.get(CONF_MESH_KEY)
            )

        # Scan for devices
        scan_successful = False
        try:
            discoveries = await DeviceScanner.async_find_available_devices(
                self.hass,
                self._mesh_info.get(CONF_MESH_NAME),
                self._mesh_info.get(CONF_MESH_PASSWORD)
            )
            scan_successful = True
        except (RuntimeError, pygatt.exceptions.BLEError) as e:
            _LOGGER.exception("Failed while scanning for devices [%s]", str(e))

        if not scan_successful:
            return self.async_show_form(
                step_id="manual",
                data_schema=vol.Schema({
                    vol.Required('mac'): str,
                    vol.Required("name", description={"suggested_value": "AwoX light"}): str,
                }),
            )

        # Store discoveries which have not been configured, add name for each discovery.
        current_devices = {entry.unique_id for entry in self._async_current_entries()}
        self._discoveries = [
            {
                **discovery,
                'name': discovery['name'],
            }
            for discovery in discoveries
            if discovery['mac'] not in current_devices
        ]

        # Ensure anything to add.
        if not self._discoveries:
            return self.async_abort(reason="no_devices_found")

        data_schema = vol.Schema(
            {
                vol.Required("mac"): vol.In(
                    {
                        discovery['mac']: discovery['name']
                        for discovery in self._discoveries
                    }
                ),
                vol.Required("name", description={"suggested_value": "AwoX light"}): str,
            }
        )
        return self.async_show_form(
            step_id="select_device",
            data_schema=data_schema,
        )

    async def async_step_awox_connect(self, user_input: Optional[Mapping] = None):

        errors = {}
        username: str = ''
        password: str = ''
        awox_connect = None

        if user_input is not None:
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)

        if username and password:
            try:
                awox_connect = await self.hass.async_add_executor_job(create_awox_connect_object, username, password)
            except Exception as e:
                _LOGGER.error('Can not login to AwoX Smart Connect [%s]', e)
                errors[CONF_PASSWORD] = 'cannot_connect'

        if user_input is None or awox_connect is None or errors:
            return self.async_show_form(
                step_id="awox_connect",
                data_schema=vol.Schema({
                    vol.Required(CONF_USERNAME, default=username): str,
                    vol.Required(CONF_PASSWORD, default=password): str,
                }),
                errors=errors,
            )

        devices = []
        for device in await self.hass.async_add_executor_job(awox_connect.devices):
            _LOGGER.debug('Processing device - %s', device)
            if 'type' not in device:
                _LOGGER.warning('Skipped device, missing type - %s', device)
                continue
            if 'address' not in device or not device['address']:
                _LOGGER.warning('Skipped device, missing address - %s', device)
                continue
            if 'macAddress' not in device:
                _LOGGER.warning('Skipped device, missing macAddress - %s', device)
                continue
            if 'displayName' not in device:
                _LOGGER.warning('Skipped device, missing displayName - %s', device)
                continue

            if 'modelName' not in device:
                device['modelName'] = 'unknown'
            if 'vendor' not in device:
                device['vendor'] = 'unknown'
            if 'version' not in device:
                device['version'] = 'unknown'
            if 'hardwareVersion' not in device:
                device['hardwareVersion'] = None

            devices.append({
                'mesh_id': int(device['address']),
                'name': device['displayName'],
                'mac': device['macAddress'],
                'model': device['modelName'],
                'manufacturer': device['vendor'],
                'firmware': device['version'],
                'hardware': device['hardwareVersion'],
                'type': device['type']
            })

        if len(devices) == 0:
            return self.async_abort(reason="no_devices_found")

        credentials = await self.hass.async_add_executor_job(awox_connect.credentials)

        data = {
            CONF_MESH_NAME: credentials['client_id'],
            CONF_MESH_PASSWORD: credentials['access_token'],
            CONF_MESH_KEY: credentials['refresh_token'],
            # 'awox_connect': {
            #     CONF_USERNAME: user_input[CONF_USERNAME],
            #     CONF_PASSWORD: user_input[CONF_PASSWORD]
            # },
            'devices': devices
        }

        return self.async_create_entry(title='AwoX Smart Connect', data=data)

    async def async_step_mesh_info(self, user_input: Optional[Mapping] = None):

        _LOGGER.debug("async_step_mesh_info: user_input: %s", user_input)

        errors = {}
        name: str = ''
        password: str = ''
        key: str = ''

        if user_input is not None:
            name = user_input.get(CONF_MESH_NAME)
            password = user_input.get(CONF_MESH_PASSWORD)
            key = user_input.get(CONF_MESH_KEY)

            if len(user_input.get(CONF_MESH_NAME)) > 16:
                errors[CONF_MESH_NAME] = 'max_length_16'
            if len(user_input.get(CONF_MESH_PASSWORD)) > 16:
                errors[CONF_MESH_PASSWORD] = 'max_length_16'
            if len(user_input.get(CONF_MESH_KEY)) > 16:
                errors[CONF_MESH_KEY] = 'max_length_16'

        if user_input is None or errors:
            return self.async_show_form(
                step_id="mesh_info",
                data_schema=vol.Schema({
                    vol.Required(CONF_MESH_NAME, default=name): str,
                    vol.Required(CONF_MESH_PASSWORD, default=password): str,
                    vol.Required(CONF_MESH_KEY, default=key): str
                }),
                errors=errors,
            )

        self._mesh_info = user_input
        return await self.async_step_user()

    async def async_step_manual(self, user_input: Optional[Mapping] = None):
        """Forward result of manual input form to step user"""
        return await self.async_step_user(user_input)

    async def async_step_select_device(self, user_input: Optional[Mapping] = None):
        """Forward result of device select form to step user"""
        return await self.async_step_user(user_input)

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry):
    #     """Define the config flow to handle options."""
    #     return UpnpOptionsFlowHandler(config_entry)

    async def _async_create_entry_from_discovery(
            self,
            mac: str,
            name: str,
            mesh_name: str,
            mesh_pass: str,
            mesh_key: str
    ):
        """Create an entry from discovery."""
        _LOGGER.debug(
            "_async_create_entry_from_discovery: device: %s [%s]",
            name,
            mac
        )

        data = {
            CONF_MESH_NAME: mesh_name,
            CONF_MESH_PASSWORD: mesh_pass,
            CONF_MESH_KEY: mesh_key,
            'devices': [
                {
                    'mac': mac,
                    'name': name,
                }
            ]
        }

        return self.async_create_entry(title=name, data=data)
    #
    # async def _async_get_name_for_discovery(self, discovery: Mapping):
    #     """Get the name of the device from a discovery."""
    #     _LOGGER.debug("_async_get_name_for_discovery: discovery: %s", discovery)
    #     device = await Device.async_create_device(
    #         self.hass, discovery[DISCOVERY_LOCATION]
    #     )
    #     return device.name
    #
    #

    # async def _async_get_name_for_discovery(self, discovery: Mapping):
    #     """Get the name of the device from a discovery."""
    #     _LOGGER.debug("_async_get_name_for_discovery: discovery: %s", discovery)
    #     device = await Device.async_create_device(
    #         self.hass, discovery['name']
    #     )
    #     return device.name
#
# async def _async_has_devices(hass) -> bool:
#     """Return if there are devices that can be discovered."""
#     devices = await DeviceScanner.find_devices()
#     return len(devices) > 0
