"""Awox device scanner class"""
import asyncio
import async_timeout
import logging

from homeassistant.core import HomeAssistant
from .awoxmeshlight import AwoxMeshLight
# import awoxmeshlight from .awoxmeshlight
from .bluetoothctl import Bluetoothctl


_LOGGER = logging.getLogger(__name__)

START_MAC_ADDRESS = "A4:C1"


class DeviceScanner:

    @staticmethod
    async def connect_device(address: str, username: str, password: str, mesh_key: str) -> bool:
        """Check if device is available"""

        light = DeviceScanner._connect(address, username, password, mesh_key)

        if light.session_key:
            light.setColor(0, 254, 0)
            light.disconnect()
            return True

        return False

    @staticmethod
    async def async_find_devices(hass: HomeAssistant, scan_timeout: int = 30):
        def init():
            return Bluetoothctl()
        devices = {}

        try:
            bl = await hass.async_add_executor_job(init)
            _LOGGER.info("Scanning %d seconds for AwoX bluetooth mesh devices!", scan_timeout)
            await hass.async_add_executor_job(bl.start_scan)
            await asyncio.sleep(scan_timeout)

            for mac, dev in (await hass.async_add_executor_job(bl.get_available_devices)).items():
                if mac.startswith(START_MAC_ADDRESS):
                    devices[mac] = dev

            _LOGGER.debug('Found devices: %s', devices)

            await hass.async_add_executor_job(bl.stop_scan)

            async with async_timeout.timeout(10):
                await hass.async_add_executor_job(bl.shutdown)

        except Exception as e:
            _LOGGER.exception('Find devices process error: %s', e)

        return devices

    @staticmethod
    async def async_find_available_devices(hass: HomeAssistant, username: str, password: str):
        """Gather a list of device"""

        result = []

        devices = await DeviceScanner.async_find_devices(hass)

        _LOGGER.debug("Found %d AwoX devices" % (len(devices)))

        for mac, dev in devices.items():
            _LOGGER.debug("Device %s [%s]" % (dev['name'], dev['mac']))
            try:
                mylight = DeviceScanner._connect(dev['mac'], username, password)
                if mylight.session_key:
                    result.append({
                        'mac': dev['mac'],
                        'name': mylight.getModelNumber()
                    })
                    mylight.disconnect()
            except:
                _LOGGER.debug('Failed to connect [%s]' % dev['mac'])

    @staticmethod
    def _connect(address, username: str, password: str, mesh_key: str = None) -> AwoxMeshLight:

        # Try to connect with factory defaults
        light = AwoxMeshLight(address)
        light.connect()

        # When connected with factory defaults and `mesh_key` is set add device to our mesh
        if light.session_key and mesh_key is not None:
            _LOGGER.info('Add %s to our mesh', address)
            light.setMesh(username, password, mesh_key)

        if not light.session_key:
            light = AwoxMeshLight(address, username, password)
            light.connect()

        return light
