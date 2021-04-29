# Based on ReachView code from Egor Fedorov (egor.fedorov@emlid.com)
# Updated for Python 3.6.8 on a Raspberry  Pi


import time
import pexpect
import subprocess
import logging
import re


logger = logging.getLogger("btctl")


class Bluetoothctl:
    """A wrapper for bluetoothctl utility."""

    def __init__(self):
        try:
            subprocess.check_output(
                "PATH=/usr/sbin:$PATH; rfkill unblock bluetooth", shell=True
            )
        except Exception as e:
            logger.warning("Failed to unblock active bluetooth connections", exc_info=1)

        self.process = pexpect.spawnu("bluetoothctl", echo=False)

    def send(self, command, pause=0):
        self.process.send(f"{command}\n")
        time.sleep(pause)
        if self.process.expect(["bluetooth", pexpect.EOF]):
            raise Exception(f"failed after {command}")

    def get_output(self, *args, **kwargs):
        """Run a command in bluetoothctl prompt, return output as a list of lines."""
        self.send(*args, **kwargs)
        return self.process.before.split("\r\n")

    def start_scan(self):
        """Start bluetooth scanning process."""
        try:
            self.send("scan on")
        except Exception as e:
            logger.error(e)

    def stop_scan(self):
        """Stop bluetooth scanning process."""
        try:
            self.send("scan off")
        except Exception as e:
            logger.error(e)

    def make_discoverable(self):
        """Make device discoverable."""
        try:
            self.send("discoverable on")
        except Exception as e:
            logger.error(e)

    def parse_device_info(self, command_output) -> dict:
        """Parse a string corresponding to a device."""
        devices = {}

        for line in command_output:
            # search for mac address
            address_search = re.search(
                r"Device ((?:[\da-fA-F]{2}[:\-]){5}[\da-fA-F]{2})", line
            )

            if not address_search:
                continue
            address = address_search.group(1)
            if address not in devices:
                devices[address] = {"mac": address, "name": address, "rssi": None}

            device_name_search = re.search(
                r"^Device ((?:[\da-fA-F]{2}[:\-]){5}[\da-fA-F]{2}) (.*)", line
            )
            if device_name_search:
                devices[address]["name"] = device_name_search.group(2)

            rssi_search = re.search(r"RSSI: (-[0-9]+)$", line)
            if rssi_search:
                devices[address]["rssi"] = int(rssi_search.group(1))
        logger.info("found: %s", devices)
        return devices

    def get_available_devices(self) -> dict:
        """Return a list paired and discoverable devices."""
        available_devices = {}
        try:
            out = self.get_output("devices")
        except Exception as e:
            logger.error(e)
        else:
            available_devices = self.parse_device_info(out)

        return available_devices

    def get_paired_devices(self) -> dict:
        """Return a list of paired devices."""
        paired_devices = {}
        try:
            out = self.get_output("paired-devices")
        except Exception as e:
            logger.error(e)
        else:
            paired_devices = self.parse_device_info(out)
        return paired_devices

    def get_device_info(self, mac_address):
        """Get device info by mac address."""
        try:
            out = self.get_output(f"info {mac_address}")
        except Exception as e:
            logger.error(e)
            return False
        else:
            return out

    def pair(self, mac_address):
        """Try to pair with a device by mac address."""
        try:
            self.send(f"pair {mac_address}", 4)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["Failed to pair", "Pairing successful", pexpect.EOF]
            )
            return res == 1

    def trust(self, mac_address):
        try:
            self.send(f"trust {mac_address}", 4)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["Failed to trust", "Pairing successful", pexpect.EOF]
            )
            return res == 1

    def remove(self, mac_address):
        """Remove paired device by mac address, return success of the operation."""
        try:
            self.send(f"remove {mac_address}", 3)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["not available", "Device has been removed", pexpect.EOF]
            )
            return res == 1

    def connect(self, mac_address):
        """Try to connect to a device by mac address."""
        try:
            self.send(f"connect {mac_address}", 2)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["Failed to connect", "Connection successful", pexpect.EOF]
            )
            return res == 1

    def disconnect(self, mac_address):
        """Try to disconnect to a device by mac address."""
        try:
            self.send(f"disconnect {mac_address}", 2)
        except Exception as e:
            logger.error(e)
            return False
        else:
            res = self.process.expect(
                ["Failed to disconnect", "Successful disconnected", pexpect.EOF]
            )
            return res == 1

    def shutdown(self):
        self.process.terminate()
