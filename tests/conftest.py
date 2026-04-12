"""Mock Home Assistant modules for testing."""
import sys
from types import ModuleType
from unittest.mock import MagicMock


def _make_module(name, **attrs):
    mod = ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


class _ColorMode:
    RGB = "rgb"
    COLOR_TEMP = "color_temp"
    BRIGHTNESS = "brightness"
    ONOFF = "onoff"


class _FakeLightEntity:
    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)

    @property
    def name(self):
        return getattr(self, "_attr_name", None)

    def async_write_ha_state(self):
        pass


class _FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class _FakeDeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class _FakeEntity:
    pass


# Build mock module tree
_mocks = {
    "homeassistant": _make_module("homeassistant"),
    "homeassistant.components": _make_module("homeassistant.components"),
    "homeassistant.components.light": _make_module(
        "homeassistant.components.light",
        ATTR_BRIGHTNESS="brightness",
        ATTR_COLOR_TEMP_KELVIN="color_temp_kelvin",
        ATTR_RGB_COLOR="rgb_color",
        DOMAIN="light",
        LightEntity=_FakeLightEntity,
        ColorMode=_ColorMode,
    ),
    "homeassistant.components.switch": _make_module(
        "homeassistant.components.switch",
        DOMAIN="switch",
    ),
    "homeassistant.components.sensor": _make_module(
        "homeassistant.components.sensor",
        DOMAIN="sensor",
        SensorDeviceClass=MagicMock(),
        SensorEntity=type("SensorEntity", (), {}),
        SensorEntityDescription=MagicMock(),
    ),
    "homeassistant.helpers": _make_module("homeassistant.helpers"),
    "homeassistant.helpers.typing": _make_module(
        "homeassistant.helpers.typing",
        StateType=str,
    ),
    "homeassistant.helpers.entity": _make_module(
        "homeassistant.helpers.entity",
        DeviceInfo=_FakeDeviceInfo,
        Entity=_FakeEntity,
        EntityCategory=MagicMock(),
        ToggleEntity=type("ToggleEntity", (), {}),
    ),
    "homeassistant.helpers.update_coordinator": _make_module(
        "homeassistant.helpers.update_coordinator",
        CoordinatorEntity=_FakeCoordinatorEntity,
    ),
    "homeassistant.config_entries": _make_module(
        "homeassistant.config_entries",
        ConfigFlow=type("ConfigFlow", (), {}),
        ConfigEntry=MagicMock(),
        CONN_CLASS_LOCAL_POLL="local_poll",
    ),
    "homeassistant.core": _make_module(
        "homeassistant.core",
        HomeAssistant=MagicMock(),
        callback=lambda f: f,
    ),
    "homeassistant.const": _make_module(
        "homeassistant.const",
        CONF_NAME="name",
        CONF_DEVICES="devices",
        CONF_MAC="mac",
        CONF_USERNAME="username",
        CONF_PASSWORD="password",
        STATE_ON="on",
        STATE_OFF="off",
        STATE_UNAVAILABLE="unavailable",
    ),
    "homeassistant.util": _make_module("homeassistant.util"),
    "homeassistant.util.color": _make_module("homeassistant.util.color"),
    "homeassistant.util.loop": _make_module("homeassistant.util.loop"),
    # AwoX internal modules that need mocking for import chain
    "custom_components.awox.awox_mesh": _make_module(
        "custom_components.awox.awox_mesh",
        AwoxMesh=MagicMock(),
    ),
    "custom_components.awox.awox_connect": _make_module(
        "custom_components.awox.awox_connect",
        AwoxConnect=MagicMock(),
    ),
    "custom_components.awox.scanner": _make_module(
        "custom_components.awox.scanner",
        DeviceScanner=MagicMock(),
    ),
    "voluptuous": MagicMock(),
    "pygatt": MagicMock(),
    "pygatt.exceptions": _make_module("pygatt.exceptions", BLEError=Exception),
}

# Install mocks before any test imports
for name, mod in _mocks.items():
    sys.modules.setdefault(name, mod)
