"""AwoX Mesh handler"""
import logging
import async_timeout
import asyncio
from homeassistant.core import HomeAssistant, callback, CALLBACK_TYPE
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from bluepy.btle import BTLEException

# import awoxmeshlight from .awoxmeshlight
from .awoxmeshlight import AwoxMeshLight
from .const import DOMAIN
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)


class AwoxMesh(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, mesh_name: str, mesh_password: str, mesh_long_term_key: str):
        """
        Args :
            hass: HomeAssistance core
            mesh_name: The mesh name as a string
            mesh_password: The mesh password as a string
            mesh_long_term_key: The new long term key as a string
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )

        self._mesh_name = mesh_name
        self._mesh_password = mesh_password
        self._mesh_long_term_key = mesh_long_term_key

        self._connected_bluetooth_device: AwoxMeshLight = None
        self._connecting = False
        self._max_command_attempts: int = 1

        self._devices = {}

    def register_device(self, mesh_id: int, mac: str, name: str, callback_func: CALLBACK_TYPE):
        self._devices[mesh_id] = {
            'mac': mac,
            'name': name,
            'callback': callback_func,
            'last_update': None
        }

        _LOGGER.info('Registered [%s] %d', mac, mesh_id)

    def is_connected(self) -> bool:
        return self._connected_bluetooth_device and self._connected_bluetooth_device.session_key

    async def async_connect_device(self):
        if self.is_connected():
            return

        if self._connecting:
            await asyncio.sleep(0.5)
            return await self.async_connect_device()

        self._connecting = True
        for mesh_id, device_info in self._devices.items():
            if device_info['mac'] is None:
                continue

            device = AwoxMeshLight(device_info['mac'], self._mesh_name, self._mesh_password, mesh_id)
            device.status_callback = self.mesh_status_callback

            try:
                _LOGGER.info("[%s][%s] Trying to connect", device.mac, device_info['name'])
                async with async_timeout.timeout(5):
                    await self.hass.async_add_executor_job(device.connect)
                self._connected_bluetooth_device = device
                _LOGGER.info("[%s][%s] Connected", device.mac, device_info['name'])
                break
            except asyncio.exceptions.TimeoutError:
                _LOGGER.warning('[%s][%s] Timeout trying to connect, trying next device', device.mac, device_info['name'])
            except Exception as e:
                _LOGGER.warning('[%s][%s] Failed to connect, trying next device [%s]', device.mac, device_info['name'], e)

        self._connecting = False

    async def _async_update_data(self):

        await self.async_connect_device()

        if not self.is_connected():
            raise UpdateFailed("No device connected")

        _LOGGER.info('async_update: Request status')
        try:
            # Request status of all devices (dest 0xffff)
            async with async_timeout.timeout(5):
                await self.hass.async_add_executor_job(self._connected_bluetooth_device.requestStatus, 0xffff)

            # Give mesh time to gather status updates
            await asyncio.sleep(.5)

            _LOGGER.info('async_update: Requested status')

            for mesh_id, device_info in self._devices.items():

                # Force status update for specific mesh_id when no new update for the last minute
                if device_info['last_update'] is None \
                        or device_info['last_update'] < datetime.now() - timedelta(seconds=60):
                    _LOGGER.info('async_update: Requested status of [%d] %s', mesh_id, device_info['name'])
                    async with async_timeout.timeout(10):
                        await self.hass.async_add_executor_job(self._connected_bluetooth_device.requestStatus, mesh_id)
                    # Give mesh time to gather status updates
                    await asyncio.sleep(.5)

                # Disable devices we didn't get a response the last 30 minutes
                if self._connected_bluetooth_device.mesh_id != mesh_id \
                        and device_info['last_update'] is not None \
                        and device_info['last_update'] < datetime.now() - timedelta(minutes=2):
                    device_info['callback']({'state': None})
                    device_info['last_update'] = None

        except asyncio.exceptions.TimeoutError as e:
            _LOGGER.warning("readStatus timeout [%s] disconnect and retry next run", e)
            await self._disconnect_current_device()
            raise UpdateFailed(f"Timeout from MESH: {e}") from e
        except BTLEException as e:
            _LOGGER.warning("readStatus failed [%s] disconnect and retry next run", e)
            await self._disconnect_current_device()
            raise UpdateFailed(f"Invalid response from MESH: {e}") from e

    @callback
    def mesh_status_callback(self, status):

        if 'mesh_id' not in status or status['mesh_id'] not in self._devices:
            _LOGGER.info('Status feedback of unknown device - [%s]',
                         status['mesh_id'] if 'mesh_id' in status else 'unknown')
            return

        _LOGGER.debug('[%d][%s] mesh_status_callback(%s)', status['mesh_id'], self._devices[status['mesh_id']]['name'], status)

        self._devices[status['mesh_id']]['callback'](status)
        self._devices[status['mesh_id']]['last_update'] = datetime.now()

    async def async_on(self, mesh_id: int, _attempt: int = 0):
        await self.async_connect_device()

        try:
            if self.is_connected():
                await self.hass.async_add_executor_job(self._connected_bluetooth_device.on, mesh_id)
            else:
                raise Exception('Not connected')
        except Exception as e:
            _LOGGER.exception('Failed to turn on [%d] - %s [%d]', mesh_id, e, _attempt)
            await self._disconnect_current_device()
            if _attempt + 1 < self._max_command_attempts:
                await self.async_on(mesh_id, _attempt + 1)

    async def async_off(self, mesh_id: int, _attempt: int = 0):
        await self.async_connect_device()

        try:
            if self.is_connected():
                await self.hass.async_add_executor_job(self._connected_bluetooth_device.off, mesh_id)
            else:
                raise Exception('Not connected')
        except Exception as e:
            _LOGGER.exception('Failed to turn off [%d] - %s [%d]', mesh_id, e, _attempt)
            await self._disconnect_current_device()
            if _attempt + 1 < self._max_command_attempts:
                await self.async_off(mesh_id, _attempt + 1)

    async def async_set_color(self, mesh_id: int, r: int, g: int, b: int, _attempt: int = 0):
        await self.async_connect_device()

        try:
            if self.is_connected():
                await self.hass.async_add_executor_job(self._connected_bluetooth_device.setColor, r, g, b, mesh_id)
            else:
                raise Exception('Not connected')
        except Exception as e:
            _LOGGER.exception('Failed to set color for [%d] - %s [%d]', mesh_id, e, _attempt)
            await self._disconnect_current_device()
            if _attempt + 1 < self._max_command_attempts:
                await self.async_set_color(mesh_id, r, g, b, _attempt + 1)

    async def async_set_color_brightness(self, mesh_id: int, brightness: int, _attempt: int = 0):
        await self.async_connect_device()

        try:
            if self.is_connected():
                await self.hass.async_add_executor_job(self._connected_bluetooth_device.setColorBrightness, brightness, mesh_id)
            else:
                raise Exception('Not connected')
        except Exception as e:
            _LOGGER.exception('Failed to set color brightness for [%d] - %s [%d]', mesh_id, e, _attempt)
            await self._disconnect_current_device()
            if _attempt + 1 < self._max_command_attempts:
                await self.async_set_color_brightness(mesh_id, brightness, _attempt + 1)

    async def async_set_white_temperature(self, mesh_id: int, white_temperature: int, _attempt: int = 0):
        await self.async_connect_device()
        try:
            if self.is_connected():
                await self.hass.async_add_executor_job(self._connected_bluetooth_device.setWhiteTemperature, white_temperature, mesh_id)
            else:
                raise Exception('Not connected')
        except Exception as e:
            _LOGGER.exception('Failed to set white temperature for [%d] - %s [%d]', mesh_id, e, _attempt)
            await self._disconnect_current_device()
            if _attempt + 1 < self._max_command_attempts:
                await self.async_set_white_temperature(mesh_id, white_temperature, _attempt + 1)

    async def async_set_white_brightness(self, mesh_id: int, brightness: int, _attempt: int = 0):
        await self.async_connect_device()
        try:
            if self.is_connected():
                await self.hass.async_add_executor_job(self._connected_bluetooth_device.setWhiteBrightness, brightness, mesh_id)
            else:
                raise Exception('Not connected')
        except Exception as e:
            _LOGGER.exception('Failed to set white brightness for [%d] - %s [%d]', mesh_id, e, _attempt)
            await self._disconnect_current_device()
            if _attempt + 1 < self._max_command_attempts:
                await self.async_set_white_brightness(mesh_id, brightness, _attempt + 1)

    async def _disconnect_current_device(self):
        if self._connecting or not self._connected_bluetooth_device:
            return
        try:
            device = self._connected_bluetooth_device
            self._connected_bluetooth_device = None
            await self.hass.async_add_executor_job(device.disconnect)
        except Exception as e:
            _LOGGER.debug('Failed to disconnect [%s]', e)
