from __future__ import unicode_literals

from . import packetutils as pckt

from os import urandom
from bluepy import btle
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

logger = logging.getLogger(__name__)


class Peripheral(btle.Peripheral):

    def _connect(self, addr, addrType=btle.ADDR_TYPE_PUBLIC, iface=None, timeout=5):
        """
        Temporary manual patch see https://github.com/IanHarvey/bluepy/pull/434
        also added a default `timeout` as this is not part yet of the release bluepy package
        """
        if len(addr.split(":")) != 6:
            raise ValueError("Expected MAC address, got %s" % repr(addr))
        if addrType not in (btle.ADDR_TYPE_PUBLIC, btle.ADDR_TYPE_RANDOM):
            raise ValueError("Expected address type public or random, got {}".format(addrType))
        self._startHelper(iface)
        self.addr = addr
        self.addrType = addrType
        self.iface = iface
        if iface is not None:
            self._writeCmd("conn %s %s %s\n" % (addr, addrType, "hci"+str(iface)))
        else:
            self._writeCmd("conn %s %s\n" % (addr, addrType))
        rsp = self._getResp('stat', timeout)
        if rsp is None:
            self._stopHelper()
            raise btle.BTLEDisconnectError("Timed out while trying to connect to peripheral %s, addr type: %s" %
                                      (addr, addrType), rsp)
        while rsp and rsp['state'][0] == 'tryconn':
            rsp = self._getResp('stat', timeout)

        if rsp is None:
            self._stopHelper()
            raise btle.BTLEDisconnectError("Timed out while trying to connect to peripheral %s, addr type: %s" %
                                      (addr, addrType), rsp)

        if rsp['state'][0] != 'conn':
            self._stopHelper()
            raise btle.BTLEDisconnectError("Failed to connect to peripheral %s, addr type: %s [%s]" % (addr, addrType, rsp), rsp)

    def _getResp(self, wantType, timeout=None):
        """
        Temporary manual patch see https://github.com/IanHarvey/bluepy/commit/b02b436cb5c71387bd70339a1b472b3a6bfe9ac8
        """
        # Temp set max timeout for wr commands (failsave)
        if timeout is None and wantType == 'wr':
            logger.debug('Set fallback time out - %s', wantType)
            timeout = 10

        if isinstance(wantType, list) is not True:
            wantType = [wantType]

        while True:
            resp = self._waitResp(wantType + ['ntfy', 'ind'], timeout)
            if resp is None:
                return None

            respType = resp['rsp'][0]
            if respType == 'ntfy' or respType == 'ind':
                hnd = resp['hnd'][0]
                data = resp['d'][0]
                if self.delegate is not None:
                    self.delegate.handleNotification(hnd, data)
            if respType not in wantType:
                continue
            return resp

    def _waitResp(self, wantType, timeout=None):
        while True:
            if self._helper.poll() is not None:
                raise btle.BTLEInternalError("Helper exited")

            if timeout:
                logger.debug("_waitResp - set timeout to %d", timeout)
                fds = self._poller.poll(timeout*1000)
                if len(fds) == 0:
                    logger.debug("Select timeout")
                    return None

            rv = self._helper.stdout.readline()
            if rv.startswith('#') or rv == '\n' or len(rv)==0:
                continue

            resp = btle.BluepyHelper.parseResp(rv)
            if 'rsp' not in resp:
                raise btle.BTLEInternalError("No response type indicator", resp)

            respType = resp['rsp'][0]
            if respType in wantType:
                logger.debug("_waitResp - resp [%s]", resp)
                return resp
            elif respType == 'stat':
                if 'state' in resp and len(resp['state']) > 0 and resp['state'][0] == 'disc':
                    self._stopHelper()
                    raise btle.BTLEDisconnectError("Device disconnected", resp)
            elif respType == 'err':
                errcode=resp['code'][0]
                if errcode=='nomgmt':
                    raise btle.BTLEManagementError("Management not available (permissions problem?)", resp)
                elif errcode=='atterr':
                    raise btle.BTLEGattError("Bluetooth command failed", resp)
                else:
                    raise btle.BTLEException("Error from bluepy-helper (%s)" % errcode, resp)
            elif respType == 'scan':
                # Scan response when we weren't interested. Ignore it
                continue
            else:
                raise btle.BTLEInternalError("Unexpected response (%s)" % respType, resp)

    def stop(self):
        self._stopHelper()


class Delegate(btle.DefaultDelegate):
    def __init__(self, light):
        self.light = light
        btle.DefaultDelegate.__init__(self)

    def handleNotification(self, cHandle, data):

        if self.light.session_key is None:
            logger.info(
                "Device [%s] is disconnected, ignoring received notification [unable to decrypt without active session]",
                self.light.mac)
            return

        message = pckt.decrypt_packet(self.light.session_key, self.light.mac, data)
        if message is None:
            logger.warning("Failed to decrypt package [key: %s, data: %s]", self.light.session_key, data)
            return

        logger.debug("Received notification %s", message)

        self.light.parseStatusResult(message)


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
        self.btdevice = Peripheral()
        self.session_key = None

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

    def connect(self, mesh_name=None, mesh_password=None):
        """
        Args :
            mesh_name: The mesh name as a string.
            mesh_password: The mesh password as a string.
        """
        if mesh_name: self.mesh_name = mesh_name.encode()
        if mesh_password: self.mesh_password = mesh_password.encode()

        assert len(self.mesh_name) <= 16, "mesh_name can hold max 16 bytes"
        assert len(self.mesh_password) <= 16, "mesh_password can hold max 16 bytes"

        self.btdevice.connect(self.mac)
        self.btdevice.setDelegate(Delegate(self))
        pair_char = self.btdevice.getCharacteristics(uuid=PAIR_CHAR_UUID)[0]
        self.session_random = urandom(8)
        message = pckt.make_pair_packet(self.mesh_name, self.mesh_password, self.session_random)
        pair_char.write(message)

        self.status_char = self.btdevice.getCharacteristics(uuid=STATUS_CHAR_UUID)[0]
        self.status_char.write(b'\x01')

        reply = bytearray(pair_char.read())
        if reply[0] == 0xd:
            self.session_key = pckt.make_session_key(self.mesh_name, self.mesh_password, self.session_random, reply[1:9])
        else:
            if reply[0] == 0xe:
                logger.info("Auth error : check name and password.")
            else:
                logger.info("Unexpected pair value : %s", repr(reply))
            self.disconnect()
            return False

        return True

    def waitForNotifications(self):
        session_key = self.session_key
        logger.info('[%s] Started waitForNotifications', self.mac)
        while self.session_key == session_key:
            try:
                self.btdevice.waitForNotifications(5)
            except btle.BTLEDisconnectError:
                self.session_key = None
            except Exception as error:
                logger.debug("waitForNotifications error - %s", error)
                # If we get the response to a write then we'll break
                pass
        logger.info('[%s] WaitForNotifications done', self.mac)

    def connectWithRetry(self, num_tries=1, mesh_name=None, mesh_password=None):
        """
        Args:
           num_tries: The number of attempts to connect.
           mesh_name: The mesh name as a string.
           mesh_password: The mesh password as a string.
        """
        connected = False
        attempts = 0
        while (not connected and attempts < num_tries):
            try:
                connected = self.connect(mesh_name, mesh_password)
            except btle.BTLEDisconnectError:
                logger.info("connection_error: retrying for %s time", attempts)
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

        pair_char = self.btdevice.getCharacteristics(uuid=PAIR_CHAR_UUID)[0]

        # FIXME : Removing the delegate as a workaround to a bluepy.btle.BTLEException
        #         similar to https://github.com/IanHarvey/bluepy/issues/182 That may be
        #         a bluepy bug or I'm using it wrong or both ...
        self.btdevice.setDelegate(None)

        message = pckt.encrypt(self.session_key, new_mesh_name.encode())
        message.insert(0, 0x4)
        pair_char.write(message)

        message = pckt.encrypt(self.session_key, new_mesh_password.encode())
        message.insert(0, 0x5)
        pair_char.write(message)

        message = pckt.encrypt(self.session_key, new_mesh_long_term_key.encode())
        message.insert(0, 0x6)
        pair_char.write(message)

        time.sleep(1)
        reply = bytearray(pair_char.read())

        self.btdevice.setDelegate(Delegate(self))

        if reply[0] == 0x7:
            self.mesh_name = new_mesh_name.encode()
            self.mesh_password = new_mesh_password.encode()
            logger.info("Mesh network settings accepted.")
            return True
        else:
            logger.info("Mesh network settings change failed : %s", repr(reply))
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

    def writeCommand(self, command, data, dest=None, withResponse=True):
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
            if not self.command_char:
                self.command_char = self.btdevice.getCharacteristics(uuid=COMMAND_CHAR_UUID)[0]

            logger.info("[%s][%d] Writing command %i data %s", self.mac, dest, command, repr(data))
            return self.command_char.write(packet, withResponse=withResponse)
        except btle.BTLEDisconnectError as err:
            logger.error('Command failed, device is disconnected: %s', err)
            self.session_key = None
            raise err
        except btle.BTLEInternalError as err:
            if 'Helper not started' in str(err):
                logger.error('Command failed, Helper not started, device is disconnected: %s', err)
                self.session_key = None
            else:
                logger.exception('Command response failed to be correctly processed but we ignore it for now: %s', err)

    def resetMesh(self):
        """
        Restores the default name and password. Will disconnect the device.
        """
        return self.writeCommand(C_MESH_RESET, b'\x00')

    def readStatus(self):
        packet = self.status_char.read()
        return pckt.decrypt_packet(self.session_key, self.mac, packet)

    def parseStatusResult(self, data):
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
            logger.debug('parsed status %s', status)
        else:
            logger.info('Unknown command [%d]', command)

        if status and status['mesh_id'] == self.mesh_id:
            logger.info('Update light status - mesh_id %d', status['mesh_id'])
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

    def requestStatus(self, dest=None, withResponse=False):
        logger.debug('requestStatus(%s)', dest)
        data = struct.pack('B', 16)
        return self.writeCommand(C_GET_STATUS_SENT, data, dest, withResponse)

    def setColor(self, red, green, blue, dest=None):
        """
        Args :
            red, green, blue: between 0 and 0xff
        """
        data = struct.pack('BBBB', 0x04, red, green, blue)
        return self.writeCommand(C_COLOR, data, dest)

    def setColorBrightness(self, brightness, dest=None):
        """
        Args :
            brightness: a value between 0xa and 0x64 ...
        """
        data = struct.pack('B', brightness)
        return self.writeCommand(C_COLOR_BRIGHTNESS, data, dest)

    def setSequenceColorDuration(self, duration, dest=None):
        """
        Args :
            duration: in milliseconds.
        """
        data = struct.pack("<I", duration)
        return self.writeCommand(C_SEQUENCE_COLOR_DURATION, data, dest)

    def setSequenceFadeDuration(self, duration, dest=None):
        """
        Args:
            duration: in milliseconds.
        """
        data = struct.pack("<I", duration)
        return self.writeCommand(C_SEQUENCE_FADE_DURATION, data, dest)

    def setPreset(self, num, dest=None):
        """
        Set a preset color sequence.

        Args :
            num: number between 0 and 6
        """
        data = struct.pack('B', num)
        return self.writeCommand(C_PRESET, data, dest)

    def setWhiteBrightness(self, brightness, dest=None):
        """
        Args :
            brightness: between 1 and 0x7f
        """
        data = struct.pack('B', brightness)
        return self.writeCommand(C_WHITE_BRIGHTNESS, data, dest)

    def setWhiteTemperature(self, temp, dest=None):
        """
        Args :
            temp: between 0 and 0x7f
        """
        data = struct.pack('B', temp)
        return self.writeCommand(C_WHITE_TEMPERATURE, data, dest)

    def setWhite(self, temp, brightness, dest=None):
        """
        Args :
            temp: between 0 and 0x7f
            brightness: between 1 and 0x7f
        """
        data = struct.pack('B', temp)
        self.writeCommand(C_WHITE_TEMPERATURE, data, dest)
        data = struct.pack('B', brightness)
        return self.writeCommand(C_WHITE_BRIGHTNESS, data, dest)

    def on(self, dest=None):
        """ Turns the light on.
        """
        return self.writeCommand(C_POWER, b'\x01', dest)

    def off(self, dest=None):
        """ Turns the light off.
        """
        return self.writeCommand(C_POWER, b'\x00', dest)

    def reconnect(self):
        logger.debug("Reconnecting.")
        self.session_key = None
        self.connect()

    def disconnect(self):
        logger.debug("Disconnecting.")
        try:
            self.btdevice.disconnect()
        except Exception as err:
            logger.warning('Disconnect failed: %s', err)

        self.session_key = None

    def stop(self):
        logger.debug("force stoppping blue helper")
        try:
            self.btdevice.stop()
        except Exception as err:
            logger.warning('Stop failed: %s', err)

        self.session_key = None

    def getFirmwareRevision(self):
        """
        Returns :
            The firmware version as a null terminated utf-8 string.
        """
        char = self.btdevice.getCharacteristics(uuid=btle.AssignedNumbers.firmwareRevisionString)[0]
        return char.read()

    def getHardwareRevision(self):
        """
        Returns :
            The hardware version as a null terminated utf-8 string.
        """
        char = self.btdevice.getCharacteristics(uuid=btle.AssignedNumbers.hardwareRevisionString)[0]
        return char.read()

    def getModelNumber(self):
        """
        Returns :
            The model as a null terminated utf-8 string.
        """
        char = self.btdevice.getCharacteristics(uuid=btle.AssignedNumbers.modelNumberString)[0]
        return char.read()

    def sendFirmware(self, firmware_path):
        """
        Updates the light bulb's firmware. The light will blink green after receiving the new
        firmware.

        Args:
            firmware_path: The path of the firmware file.
        """
        assert (self.session_key)

        with open(firmware_path, 'rb') as firmware_file:
            firmware_data = firmware_file.read()

        if not firmware_data:
            return

        ota_char = self.btdevice.getCharacteristics(uuid=OTA_CHAR_UUID)[0]
        count = 0
        for i in range(0, len(firmware_data), 0x10):
            data = struct.pack('<H', count) + firmware_data[i:i + 0x10].ljust(0x10, b'\xff')
            crc = pckt.crc16(data)
            packet = data + struct.pack('<H', crc)
            logger.debug("Writing packet %i of %i : %s", count + 1, len(firmware_data) / 0x10 + 1, repr(packet))
            ota_char.write(packet)
            # FIXME : When calling write with withResponse=True bluepy hangs after a few packets.
            #         Without any delay the light blinks once without accepting the firmware.
            #         The choosen value is arbitrary.
            time.sleep(0.01)
            count += 1
        data = struct.pack('<H', count)
        crc = pckt.crc16(data)
        packet = data + struct.pack('<H', crc)
        logger.debug("Writing last packet : %s", repr(packet))
        ota_char.write(packet)
