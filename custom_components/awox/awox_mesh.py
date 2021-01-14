"""AwoX Mesh handler"""
import logging
import asyncio
import async_timeout
import queue
import threading
import time
import re
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant, callback, CALLBACK_TYPE
from homeassistant.const import EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

# import awoxmeshlight from .awoxmeshlight
from .awoxmeshlight import AwoxMeshLight
from .const import DOMAIN
from .scanner import DeviceScanner

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

        self._state = {
            'last_rssi_check': None,
            'mesh': None,
        }

        self._devices = {}

        self._queue = queue.Queue()
        self._shutdown = False
        self._command_tread = threading.Thread(target=self._process_command_queue,
                                               name="AwoxMeshCommands-" + self._mesh_name)
        self._command_tread.daemon = True
        self._last_response: datetime = None
        self._command_tread.start()

        def startup(event):
            _LOGGER.debug('startup')
            asyncio.run_coroutine_threadsafe(
                self.async_refresh(), hass.loop
            ).result()

        def shutdown(event):
            _LOGGER.debug('shutdown')
            asyncio.run_coroutine_threadsafe(
                self.async_shutdown(), hass.loop
            ).result()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, startup)
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown)

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

    async def _async_update_data(self):

        if not self._command_tread.is_alive():
            raise UpdateFailed("Command tread died!")

        if self._state['last_rssi_check'] is None \
                or self._state['last_rssi_check'] < datetime.now() - timedelta(hours=24):
            await self._async_get_devices_rssi()

        _LOGGER.info('async_update: Request status')
        await self._async_add_command_to_queue('requestStatus', {'dest': 0xffff, 'withResponse': True})

        # Not connected after executing command then we assume we could not connect to a device
        if not self.is_connected():
            # Disable all when 2th run is also not successful
            if not self.last_update_success:
                self.update_status_of_all_devices_to_disabled()

            raise UpdateFailed("No device connected")

        # Give mesh time to gather status updates
        await asyncio.sleep(.5)

        for mesh_id, device_info in self._devices.items():

            # Force status update for specific mesh_id when no new update for the last minute
            if device_info['last_update'] is None \
                    or device_info['last_update'] < datetime.now() - timedelta(seconds=60):
                _LOGGER.info('async_update: Requested status of [%d] %s', mesh_id, device_info['name'])

                await self._async_add_command_to_queue('requestStatus', {'dest': mesh_id, 'withResponse': True})

                # Give mesh time to gather status updates
                await asyncio.sleep(.5)

            # Disable devices we didn't get a response the last 30 minutes
            if self._devices[mesh_id]['last_update'] is not None \
                    and self._devices[mesh_id]['last_update'] < datetime.now() - timedelta(minutes=2):
                self._devices[mesh_id]['callback']({'state': None})
                self._devices[mesh_id]['last_update'] = None

    def update_status_of_all_devices_to_disabled(self):
        for mesh_id, device_info in self._devices.items():
            if device_info['last_update'] is not None:
                device_info['callback']({'state': None})
                self._devices[mesh_id]['last_update'] = None

    async def _async_update_mesh_state(self):
        state = "disconnected"
        if self.is_connected():
            state = "connected"
        self.hass.states.async_set("awox_mesh." + self._mesh_name, state, self._state)

    @callback
    def mesh_status_callback(self, status):
        self._last_response = datetime.now()

        if 'mesh_id' not in status or status['mesh_id'] not in self._devices:
            _LOGGER.info('Status feedback of unknown device - [%s]',
                         status['mesh_id'] if 'mesh_id' in status else 'unknown')
            return

        _LOGGER.debug('[%d][%s] mesh_status_callback(%s)',
                      status['mesh_id'], self._devices[status['mesh_id']]['name'], status)

        self._devices[status['mesh_id']]['callback'](status)
        self._devices[status['mesh_id']]['last_update'] = datetime.now()

    async def async_on(self, mesh_id: int):
        await self._async_add_command_to_queue('on', {'dest': mesh_id})

    async def async_off(self, mesh_id: int, _attempt: int = 0):
        await self._async_add_command_to_queue('off', {'dest': mesh_id})

    async def async_set_color(self, mesh_id: int, r: int, g: int, b: int, _attempt: int = 0):
        await self._async_add_command_to_queue('setColor', {'red': r, 'green': g, 'blue': b, 'dest': mesh_id})

    async def async_set_color_brightness(self, mesh_id: int, brightness: int, _attempt: int = 0):
        await self._async_add_command_to_queue('setColorBrightness', {'brightness': brightness, 'dest': mesh_id})

    async def async_set_white_temperature(self, mesh_id: int, white_temperature: int, _attempt: int = 0):
        await self._async_add_command_to_queue('setWhiteTemperature', {'temp': white_temperature, 'dest': mesh_id})

    async def async_set_white_brightness(self, mesh_id: int, brightness: int, _attempt: int = 0):
        await self._async_add_command_to_queue('setWhiteBrightness', {'brightness': brightness, 'dest': mesh_id})

    async def _disconnect_current_device(self):
        if not self._connected_bluetooth_device:
            return
        try:
            device = self._connected_bluetooth_device
            self._connected_bluetooth_device = None
            await self.hass.async_add_executor_job(device.disconnect)
        except Exception as e:
            _LOGGER.exception('Failed to disconnect [%s]', e)

        await self._async_update_mesh_state()

    async def async_shutdown(self):
        _LOGGER.info('Shutdown mesh')
        self._shutdown = True
        return await self._disconnect_current_device()

    async def _async_add_command_to_queue(self, command: str, params):
        done = False

        def command_executed():
            nonlocal done
            done = True

        self._queue.put({
            'command': command,
            'params': params,
            'callback': command_executed
        })
        while not done:
            await asyncio.sleep(.01)

    def _process_command_queue(self):
        while not self._shutdown:

            _LOGGER.debug('get item from queue')
            command = self._queue.get()
            _LOGGER.debug('process 0/%d - %s', self._queue.qsize(), command)
            try:
                tries = 0
                while not self._call_command(command) and tries < 2:
                    _LOGGER.debug('retry calling command')
                    tries = tries + 1

            except Exception as e:
                _LOGGER.exception('Command failed and skipped - %s', e)

            if 'callback' in command:
                command['callback']()

            self._queue.task_done()

    def _call_command(self, command) -> bool:
        asyncio.run_coroutine_threadsafe(
            self._async_connect_device(), self.hass.loop
        ).result()
        if not self.is_connected():
            return False

        now = datetime.now()
        # Call command
        if isinstance(command['params'], tuple):
            res = getattr(self._connected_bluetooth_device, command['command'])(*command['params'])
        else:
            res = getattr(self._connected_bluetooth_device, command['command'])(**command['params'])

        if res is None:
            _LOGGER.error('Timeout executing command, probably Bluetooth connection is lost/frozen, re-connecting')
            self.update_status_of_all_devices_to_disabled()
            device = self._connected_bluetooth_device
            self._connected_bluetooth_device = None
            self.hass.states.set("awox_mesh." + self._mesh_name, "disconnected")
            device.disconnect()
            return False

        if self._last_response is not None and self._last_response < now:
            _LOGGER.warning('No response received after command! - start: %s, now: %s, last response: %s', now,
                            datetime.now(), self._last_response)

        return True

    async def _async_connect_device(self):
        if self.is_connected():
            return

        for mesh_id, device_info in self._devices.items():
            if device_info['mac'] is None:
                continue

            device = AwoxMeshLight(device_info['mac'], self._mesh_name, self._mesh_password, mesh_id)
            try:
                _LOGGER.info("[%s][%s] Trying to connect", device.mac, device_info['name'])
                async with async_timeout.timeout(10):
                    if await self.hass.async_add_executor_job(device.connect):
                        self._connected_bluetooth_device = device
                        self._state["mesh"] = device_info["name"]
                        await self._async_update_mesh_state()
                        _LOGGER.info("[%s][%s] Connected", device.mac, device_info['name'])
                        break
                    else:
                        _LOGGER.info("[%s][%s] Could not connect", device.mac, device_info['name'])
            except Exception as e:
                _LOGGER.exception('[%s][%s] Failed to connect, trying next device [%s]',
                                  device.mac, device_info['name'], e)

        if self._connected_bluetooth_device is not None:
            self._connected_bluetooth_device.status_callback = self.mesh_status_callback

    async def _async_get_devices_rssi(self):
        _LOGGER.info('Search for AwoX devices to find closest (best rssi value) device')
        devices = await DeviceScanner.async_find_devices(hass=self.hass)
        _LOGGER.debug('devices: %s', devices)

        for mesh_id, device_info in self._devices.items():
            if device_info['mac'].upper() in devices and devices[device_info['mac'].upper()]['rssi'] is not None:
                self._devices[mesh_id]['rssi'] = devices[device_info['mac'].upper()]['rssi']
            else:
                self._devices[mesh_id]['rssi'] = -999999

        self._state['last_rssi_check'] = datetime.now()
        await self._async_update_mesh_state()

        # Sort devices by rssi
        self._devices = dict(sorted(self._devices.items(), key=lambda t: t[1]['rssi'], reverse=True))
