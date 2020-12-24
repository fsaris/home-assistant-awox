"""AwoX Mesh handler"""
import logging
from homeassistant.core import HomeAssistant, callback, CALLBACK_TYPE
from bluepy.btle import BTLEException

# import awoxmeshlight from .awoxmeshlight
from .awoxmeshlight import AwoxMeshLight
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)


class AwoxMesh:

    def __init__(self, hass: HomeAssistant, mesh_name: str, mesh_password: str, mesh_long_term_key: str):
        """
        Args :
            hass: HomeAssistance core
            mesh_name: The mesh name as a string
            mesh_password: The mesh password as a string
            mesh_long_term_key: The new long term key as a string
        """
        self._hass = hass
        self._mesh_name = mesh_name
        self._mesh_password = mesh_password
        self._mesh_long_term_key = mesh_long_term_key

        self._connected_bluetooth_device: AwoxMeshLight = None
        self._connecting = False

        self._devices = {}

    def register_device(self, mesh_id: int, mac: str, callback_func: CALLBACK_TYPE):
        self._devices[mesh_id] = {
            'mac': mac,
            'callback': callback_func,
            'last_update': None
        }

        self._hass.async_create_task(self.async_update())
        _LOGGER.info('Registered [%s] %d', mac, mesh_id)

    def is_connected(self) -> bool:
        return self._connected_bluetooth_device and self._connected_bluetooth_device.session_key

    async def async_connect_device(self):
        if self._connecting or self.is_connected():
            return

        self._connecting = True
        for mesh_id, device_info in self._devices.items():
            if device_info['mac'] is None:
                continue

            device = AwoxMeshLight(device_info['mac'], self._mesh_name, self._mesh_password, mesh_id)
            device.status_callback = self.mesh_status_callback

            try:
                _LOGGER.info("[%s] Trying to connect", device.mac)
                await self._hass.async_add_executor_job(device.connect)
                self._connected_bluetooth_device = device
                _LOGGER.info("[%s] Connected", device.mac)
                break

            except Exception as e:
                _LOGGER.warning('[%s] Failed to connect, trying next device [%s]', device.mac, e)

        self._connecting = False

    @callback
    async def async_update(self, *args, **kwargs) -> None:
        await self.async_connect_device()
        if not self.is_connected():
            _LOGGER.debug('async_update: No connected device - Connection in progress [%s]', self._connecting)
            return

        # Disable devices we didn't get a response the last 30 minutes
        for mesh_id, device_info in self._devices.items():
            if self._connected_bluetooth_device.mesh_id != mesh_id \
                    and device_info['last_update'] is not None \
                    and device_info['last_update'] < datetime.now() - timedelta(minutes=30):
                device_info['callback']({'state': None})
                device_info['last_update'] = None

        _LOGGER.debug('[%s] async_update: Read status [%s]', self._connected_bluetooth_device.mac, args)
        try:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.readStatus)
        except BTLEException as e:
            _LOGGER.warning("[%s] readStatus failed [%s] disconnect and retry next run", self._connected_bluetooth_device.mac, e)
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.disconnect)

    @callback
    def mesh_status_callback(self, status):
        _LOGGER.debug('mesh_status_callback(%s)', status)

        if 'mesh_id' not in status or status['mesh_id'] not in self._devices:
            _LOGGER.info('Status feedback of unknown device - [%s]',
                         status['mesh_id'] if 'mesh_id' in status else 'unknown')
            return

        self._devices[status['mesh_id']]['callback'](status)
        self._devices[status['mesh_id']]['last_update'] = datetime.now()

    async def async_on(self, mesh_id: int):
        await self.async_connect_device()
        if not self.is_connected():
            _LOGGER.error('async_on: No connected device - Connection in progress [%s]', self._connecting)
            return

        try:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.on, mesh_id)
        except Exception as e:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.disconnect)
            _LOGGER.error('Failed to turn on [%d] - %s', mesh_id, e)

    async def async_off(self, mesh_id: int):
        await self.async_connect_device()
        if not self.is_connected():
            _LOGGER.error('async_off: No connected device - Connection in progress [%s]', self._connecting)
            return

        try:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.off, mesh_id)
        except Exception as e:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.disconnect)
            _LOGGER.error('Failed to turn off [%d] - %s', mesh_id, e)

    async def async_set_color(self, mesh_id: int, r: int, g: int, b: int):
        await self.async_connect_device()
        if not self.is_connected():
            _LOGGER.error('async_set_color: No connected device - Connection in progress [%s]', self._connecting)
            return

        try:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.setColor, r, g, b, mesh_id)
        except Exception as e:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.disconnect)
            _LOGGER.error('Failed to set color for [%d] - %s', mesh_id, e)

    async def async_set_color_brightness(self, mesh_id: int, brightness: int):
        await self.async_connect_device()
        if not self.is_connected():
            _LOGGER.error('async_set_color_brightness: No connected device - Connection in progress [%s]', self._connecting)
            return

        try:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.setColorBrightness, brightness, mesh_id)
        except Exception as e:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.disconnect)
            _LOGGER.error('Failed to set color brightness for [%d] - %s', mesh_id, e)

    async def async_set_white_temperature(self, mesh_id: int, white_temperature: int):
        await self.async_connect_device()
        if not self.is_connected():
            _LOGGER.error('async_set_white_temperature: No connected device - Connection in progress [%s]', self._connecting)
            return

        try:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.setWhiteTemperature, white_temperature, mesh_id)
        except Exception as e:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.disconnect)
            _LOGGER.error('Failed to set white temperature for [%d] - %s', mesh_id, e)

    async def async_set_white_brightness(self, mesh_id: int, brightness: int):
        await self.async_connect_device()
        if not self.is_connected():
            _LOGGER.error('async_set_white_brightness: No connected device - Connection in progress [%s]', self._connecting)
            return

        try:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.setWhiteBrightness, brightness, mesh_id)
        except Exception as e:
            await self._hass.async_add_executor_job(self._connected_bluetooth_device.disconnect)
            _LOGGER.error('Failed to set white brightness for [%d] - %s', mesh_id, e)
