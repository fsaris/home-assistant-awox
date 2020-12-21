"""Awox device scanner class"""
import pygatt
import logging


from .awoxmeshlight import AwoxMeshLight
# import awoxmeshlight from .awoxmeshlight


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
    async def find_devices(username: str, password: str):
        """Gather a list of device infos from the local network."""

        result = []
        adapter = pygatt.GATTToolBackend()
        devices = adapter.scan()

        _LOGGER.debug("Found %d devices" % (len(devices)))

        for dev in devices:
            if not dev.address.startswith(START_MAC_ADDRESS):
                _LOGGER.debug("Skipped device %s [%s] the MAC address of this device does not start with valid sequence"
                              % (dev.name, dev.address))
                continue

            _LOGGER.debug("Device %s [%s]" % (dev.name, dev.address))

            try:
                mylight = DeviceScanner._connect(dev.address, username, password)
                #
                if mylight.session_key:
                    result.append({
                        'mac': dev.address,
                        'name': mylight.getModelNumber()
                    })
                    mylight.disconnect()
            except:
                _LOGGER.debug('Failed to connect [%s]' % dev.address)

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
