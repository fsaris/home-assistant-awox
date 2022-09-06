from __future__ import unicode_literals

import binascii

import bleak

from . import packetutils as pckt

from os import urandom
from bleak import BleakClient
from bleak.__version__ import __version__ as bleak_version
import asyncio
import logging
import struct
import time

# Commands :

#: Set mesh groups.
#: Data : 3 bytes
C_MESH_GROUP = 0xd7

#: Set the mesh id. The light will still answer to the 0 mesh id. Calling the
#: command again replaces the previous mesh id.
#: Data : the new mesh id, 2 bytes in little endian order
C_MESH_ADDRESS = 0xe0

#:
C_MESH_RESET = 0xe3

#: On/Off command. Data : one byte 0, 1
C_POWER = 0xd0

#: Data : one byte
C_LIGHT_MODE = 0x33

#: Data : one byte 0 to 6
C_PRESET = 0xc8

#: White temperature. one byte 0 to 0x7f
C_WHITE_TEMPERATURE = 0xf0

#: one byte 1 to 0x7f
C_WHITE_BRIGHTNESS = 0xf1

#: 4 bytes : 0x4 red green blue
C_COLOR = 0xe2

#: one byte : 0xa to 0x64 ....
C_COLOR_BRIGHTNESS = 0xf2

#: Data 4 bytes : How long a color is displayed in a sequence in milliseconds as
#:   an integer in little endian order
C_SEQUENCE_COLOR_DURATION = 0xf5

#: Data 4 bytes : Duration of the fading between colors in a sequence, in
#:   milliseconds, as an integer in little endian order
C_SEQUENCE_FADE_DURATION = 0xf6

#: 7 bytes
C_TIME = 0xe4

#: 10 bytes
C_ALARMS = 0xe5

#: Request current light/device status
C_GET_STATUS_SENT = 0xda

#: Response of light/device status request
C_GET_STATUS_RECEIVED = 0xdb

#: State notification
C_NOTIFICATION_RECEIVED = 0xdc

PAIR_CHAR_UUID = '00010203-0405-0607-0809-0a0b0c0d1914'
COMMAND_CHAR_UUID = '00010203-0405-0607-0809-0a0b0c0d1912'
STATUS_CHAR_UUID = '00010203-0405-0607-0809-0a0b0c0d1911'
OTA_CHAR_UUID = '00010203-0405-0607-0809-0a0b0c0d1913'

FIRMWARE_REV_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(0x2A26)
HARDWARE_REV_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(0x2A27)
MODEL_NBR_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(0x2A24)

_LOGGER = logging.getLogger(__name__)


class AwoxMeshLightException(Exception):
    """Exception class for AwoxMeshLight."""
    pass


class AwoxMeshLight:
    def __init__(self, mac, mesh_name="unpaired", mesh_password="1234", mesh_id=0):
        """
        Args :
            mac: The light's MAC address as a string in the form AA:BB:CC:DD:EE:FF
            mesh_name: The mesh name as a string.
            mesh_password: The mesh password as a string.
            mesh_id: The mesh id (address)
        """
        self.mac = mac
        self.mesh_id = mesh_id

        def disconnected_callback(client: BleakClient):
            _LOGGER.debug(f"BLE client disconnected: {client.address}")
            self.session_key = None

        self._client = BleakClient(self.mac, disconnected_callback=disconnected_callback)

        self._notification_queue = asyncio.Queue(maxsize=1)

        self.session_key = None

        self._default_timeout = 10

        self.command_char = None
        self.status_char = None

        self.mesh_name = mesh_name.encode()
        self.mesh_password = mesh_password.encode()

        # Light status
        self.white_brightness = None
        self.white_temperature = None
        self.color_brightness = None
        self.red = None
        self.green = None
        self.blue = None
        self.color_mode = None
        self.transition_mode = None
        self.state = None
        self.status_callback = None

    def createPairMessage(self):

        self.session_random = urandom(8)
        message = pckt.make_pair_packet(self.mesh_name, self.mesh_password, self.session_random)

        _LOGGER.debug(f"Sent pair message: {binascii.hexlify(message)}")

    async def connect(self, mesh_name=None, mesh_password=None):
        """
        Args :
            mesh_name: The mesh name as a string.
            mesh_password: The mesh password as a string.
        """
        if mesh_name: self.mesh_name = mesh_name.encode()
        if mesh_password: self.mesh_password = mesh_password.encode()

        assert len(self.mesh_name) <= 16, "mesh_name can hold max 16 bytes"
        assert len(self.mesh_password) <= 16, "mesh_password can hold max 16 bytes"

        _LOGGER.debug("Connecting to %s, bleak: %s", self.mac, bleak_version)

        try:
            await asyncio.wait_for(
                self._client.connect(),
                self._default_timeout)
        except Exception as ex:
            _LOGGER.error("Failed to connect %s", ex)
            raise ex

        _LOGGER.debug("Connected to %s", self.mac)

        self.session_random = urandom(8)
        message = pckt.make_pair_packet(self.mesh_name, self.mesh_password, self.session_random)

        _LOGGER.debug(f"Sent pair message: {binascii.hexlify(message)}")
        await self._client.write_gatt_char(PAIR_CHAR_UUID, message)

        try:
            _LOGGER.debug("Read pair char")
            value = await self._client.read_gatt_char(PAIR_CHAR_UUID)
        except Exception as ex:
            _LOGGER.error("Failed to pair %s", ex)
            raise ex
        _LOGGER.debug(f"Read {value} from characteristic {PAIR_CHAR_UUID}")

        reply = bytearray(value)
        if reply[0] == 0xd:
            self.session_key = pckt.make_session_key(self.mesh_name, self.mesh_password, self.session_random,
                                                     reply[1:9])
        else:
            if reply[0] == 0xe:
                _LOGGER.info("Auth error : check name and password.")
            else:
                _LOGGER.info("Unexpected pair value : %s", repr(reply))
            await self.disconnect()
            return False

        return True

    async def requestStatusUpdates(self):

        def _handle_data(handle, data):
            """Handle an incoming notification message."""

            if self.session_key is None:
                _LOGGER.info(
                    "Device [%s] is disconnected, ignoring received notification [unable to decrypt without active session]",
                    self.mac)
                return

            message = pckt.decrypt_packet(self.session_key, self.mac, data)
            if message is None:
                _LOGGER.warning("Failed to decrypt package [key: %s, data: %s]", self.session_key, data)
                return

            _LOGGER.debug("Received notification %s", message)

            self._processStatusResult(message)

        _LOGGER.debug("Sent status message to enable notifications")
        await self._client.write_gatt_char(STATUS_CHAR_UUID, b'\x01')

        try:
            _LOGGER.debug("Start notify")
            await self._client.start_notify(STATUS_CHAR_UUID, _handle_data)
            _LOGGER.debug("Started notify")
        except bleak.exc.BleakDBusError as e:
            if str(e) != '[org.bluez.Error.Failed] Operation failed with ATT error: 0x0e (Connection Rejected Due To Security Reasons)':
                _LOGGER.exception(f'Failed to start notify {e}', e)
            else:
                _LOGGER.debug(f'Failed to start notify due to mismatch in handle: {e}')

            await self.reconnect()

    async def connectWithRetry(self, num_tries=1, mesh_name=None, mesh_password=None):
        """
        Args:
           num_tries: The number of attempts to connect.
           mesh_name: The mesh name as a string.
           mesh_password: The mesh password as a string.
        """
        connected = False
        attempts = 0
        while not connected and attempts < num_tries:
            try:
                connected = await self.connect(mesh_name, mesh_password)
            except Exception as error:
                _LOGGER.info("connection_error: retrying for %s time - %s", attempts, error)
            finally:
                attempts += 1

        return connected

    def setMesh(self, new_mesh_name, new_mesh_password, new_mesh_long_term_key):
        """
        Sets or changes the mesh network settings.

        Args :
            new_mesh_name: The new mesh name as a string, 16 bytes max.
            new_mesh_password: The new mesh password as a string, 16 bytes max.
            new_mesh_long_term_key: The new long term key as a string, 16 bytes max.

        Returns :
            True on success.
        """
        assert (self.session_key), "Not connected"
        assert len(new_mesh_name.encode()) <= 16, "new_mesh_name can hold max 16 bytes"
        assert len(new_mesh_password.encode()) <= 16, "new_mesh_password can hold max 16 bytes"
        assert len(new_mesh_long_term_key.encode()) <= 16, "new_mesh_long_term_key can hold max 16 bytes"

        message = pckt.encrypt(self.session_key, new_mesh_name.encode())
        message.insert(0, 0x4)
        self._client.write_gatt_char(PAIR_CHAR_UUID, message)

        message = pckt.encrypt(self.session_key, new_mesh_password.encode())
        message.insert(0, 0x5)
        self._client.write_gatt_char(PAIR_CHAR_UUID, message)

        message = pckt.encrypt(self.session_key, new_mesh_long_term_key.encode())
        message.insert(0, 0x6)
        self._client.write_gatt_char(PAIR_CHAR_UUID, message)

        time.sleep(1)
        reply = bytearray(self._client.read_gatt_char(PAIR_CHAR_UUID))

        if reply[0] == 0x7:
            self.mesh_name = new_mesh_name.encode()
            self.mesh_password = new_mesh_password.encode()
            _LOGGER.info("Mesh network settings accepted.")
            return True
        else:
            _LOGGER.info("Mesh network settings change failed : %s", repr(reply))
            return False

    def setMeshId(self, mesh_id):
        """
        Sets the mesh id.

        Args :
            mesh_id: as a number.

        """
        data = struct.pack("<H", mesh_id)
        self.writeCommand(C_MESH_ADDRESS, data)
        self.mesh_id = mesh_id

    async def writeCommand(self, command, data, dest=None, withResponse=True):
        """
        Args:
            command: The command, as a number.
            data: The parameters for the command, as bytes.
            dest: The destination mesh id, as a number. If None, this lightbulb's
                mesh id will be used.
        """
        assert (self.session_key)
        if dest == None: dest = self.mesh_id
        packet = pckt.make_command_packet(self.session_key, self.mac, dest, command, data)

        try:
            res = await self._client.write_gatt_char(char_specifier=COMMAND_CHAR_UUID, data=packet,
                                                     response=withResponse)
            _LOGGER.debug('res: %s', res)
            return True
        except Exception as ex:
            _LOGGER.error('Command %s failed, device is disconnected: %s', command, ex)
            self.session_key = None
            raise ex

    def resetMesh(self):
        """
        Restores the default name and password. Will disconnect the device.
        """
        return self.writeCommand(C_MESH_RESET, b'\x00')

    def _processStatusResult(self, data):
        command = struct.unpack('B', data[7:8])[0]
        status = {}
        if command == C_GET_STATUS_RECEIVED:
            mode = struct.unpack('B', data[10:11])[0]
            mesh_id = (struct.unpack('B', data[4:5])[0] * 256) + struct.unpack('B', data[3:4])[0]
            white_brightness, white_temperature = struct.unpack('BB', data[11:13])
            color_brightness, red, green, blue = struct.unpack('BBBB', data[13:17])
            status = {
                'mesh_id': mesh_id,
                'state': (mode & 1) == 1,
                'color_mode': ((mode >> 1) & 1) == 1,
                'transition_mode': ((mode >> 2) & 1) == 1,
                'red': red,
                'green': green,
                'blue': blue,
                'white_temperature': white_temperature,
                'white_brightness': white_brightness,
                'color_brightness': color_brightness,
            }

        if command == C_NOTIFICATION_RECEIVED:
            mesh_id = (struct.unpack('B', data[19:20])[0] * 256) + struct.unpack('B', data[10:11])[0]
            mode = struct.unpack('B', data[12:13])[0]
            white_brightness, white_temperature = struct.unpack('BB', data[13:15])
            color_brightness, red, green, blue = struct.unpack('BBBB', data[15:19])

            status = {
                'mesh_id': mesh_id,
                'state': (mode & 1) == 1,
                'color_mode': ((mode >> 1) & 1) == 1,
                'transition_mode': ((mode >> 2) & 1) == 1,
                'red': red,
                'green': green,
                'blue': blue,
                'white_temperature': white_temperature,
                'white_brightness': white_brightness,
                'color_brightness': color_brightness,
            }

        if status:
            _LOGGER.debug('parsed status %s', status)
        else:
            _LOGGER.info('Unknown command [%d]', command)

        if status and status['mesh_id'] == self.mesh_id:
            _LOGGER.info('Update device status - mesh_id %d', status['mesh_id'])
            self.state = status['state']
            self.color_mode = status['color_mode']
            self.transition_mode = status['transition_mode']
            self.white_brightness = status['white_brightness']
            self.white_temperature = status['white_temperature']
            self.color_brightness = status['color_brightness']
            self.red = status['red']
            self.green = status['green']
            self.blue = status['blue']

        if status and self.status_callback:
            self.status_callback(status)

    async def requestStatus(self, dest=None, withResponse=False):
        _LOGGER.debug('requestStatus(%s)', dest)
        data = struct.pack('B', 16)
        return await self.writeCommand(C_GET_STATUS_SENT, data, dest, withResponse)

    async def setColor(self, red, green, blue, dest=None):
        """
        Args :
            red, green, blue: between 0 and 0xff
        """
        data = struct.pack('BBBB', 0x04, red, green, blue)
        return await self.writeCommand(C_COLOR, data, dest)

    async def setColorBrightness(self, brightness, dest=None):
        """
        Args :
            brightness: a value between 0xa and 0x64 ...
        """
        data = struct.pack('B', brightness)
        return await self.writeCommand(C_COLOR_BRIGHTNESS, data, dest)

    async def setSequenceColorDuration(self, duration, dest=None):
        """
        Args :
            duration: in milliseconds.
        """
        data = struct.pack("<I", duration)
        return await self.writeCommand(C_SEQUENCE_COLOR_DURATION, data, dest)

    async def setSequenceFadeDuration(self, duration, dest=None):
        """
        Args:
            duration: in milliseconds.
        """
        data = struct.pack("<I", duration)
        return await self.writeCommand(C_SEQUENCE_FADE_DURATION, data, dest)

    async def setPreset(self, num, dest=None):
        """
        Set a preset color sequence.

        Args :
            num: number between 0 and 6
        """
        data = struct.pack('B', num)
        return await self.writeCommand(C_PRESET, data, dest)

    async def setWhiteBrightness(self, brightness, dest=None):
        """
        Args :
            brightness: between 1 and 0x7f
        """
        data = struct.pack('B', brightness)
        return await self.writeCommand(C_WHITE_BRIGHTNESS, data, dest)

    async def setWhiteTemperature(self, temp, dest=None):
        """
        Args :
            temp: between 0 and 0x7f
        """
        data = struct.pack('B', temp)
        return await self.writeCommand(C_WHITE_TEMPERATURE, data, dest)

    async def setWhite(self, temp, brightness, dest=None):
        """
        Args :
            temp: between 0 and 0x7f
            brightness: between 1 and 0x7f
        """
        data = struct.pack('B', temp)
        await self.writeCommand(C_WHITE_TEMPERATURE, data, dest)
        data = struct.pack('B', brightness)
        return await self.writeCommand(C_WHITE_BRIGHTNESS, data, dest)

    async def on(self, dest=None):
        """ Turns the light on.
        """
        return await self.writeCommand(C_POWER, b'\x01', dest)

    async def off(self, dest=None):
        """ Turns the light off.
        """
        return await self.writeCommand(C_POWER, b'\x00', dest)

    async def reconnect(self):
        _LOGGER.debug("Reconnecting.")

        if self._client.is_connected:
            await self.disconnect()

        self.session_key = None
        await self.connect()

    async def stopNotify(self):
        _LOGGER.debug("stopNotify.")
        try:
            await self._client.stop_notify(STATUS_CHAR_UUID)
        except Exception as err:
            _LOGGER.warning('stopNotify failed: %s', err)
            return

    async def disconnect(self):
        _LOGGER.debug("Disconnecting.")
        try:
            await self._client.disconnect()
        except Exception as err:
            _LOGGER.warning('Disconnect failed: %s', err)

        self.session_key = None

    async def getFirmwareRevision(self):
        """
        Returns :
            The firmware version as a null terminated utf-8 string.
        """
        return await self._client.read_gatt_char(FIRMWARE_REV_UUID)

    async def getHardwareRevision(self):
        """
        Returns :
            The hardware version as a null terminated utf-8 string.
        """
        return await self._client.read_gatt_char(HARDWARE_REV_UUID)

    async def getModelNumber(self):
        """
        Returns :
            The model as a null terminated utf-8 string.
        """
        return await self._client.read_gatt_char(MODEL_NBR_UUID)

    @property
    def is_connected(self) -> bool:
        return self._client and self._client.is_connected and self.session_key