"""Tests for kelvin-based color temperature after HA 2026.3 migration."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from custom_components.awox.light import AwoxLight, convert_value_to_available_range


def _make_light(
    supported_color_modes=None,
    white_temperature=None,
    color_mode_is_rgb=False,
):
    """Create an AwoxLight with mocked mesh for testing."""
    if supported_color_modes is None:
        supported_color_modes = {"color_temp", "rgb"}

    mesh = MagicMock()
    mesh.register_device = MagicMock()
    mesh.identifier = "test-mesh"
    mesh.async_set_white_temperature = AsyncMock()
    mesh.async_set_color = AsyncMock()
    mesh.async_set_white_brightness = AsyncMock()
    mesh.async_on = AsyncMock()

    light = AwoxLight(
        coordinator=mesh,
        mac="aa:bb:cc:dd:ee:ff",
        mesh_id=1,
        name="Test Light",
        supported_color_modes=supported_color_modes,
        manufacturer="Eglo",
        model="ESpot_225",
        firmware="2.2.6",
    )
    # Simulate a hass object for status_callback
    light.hass = MagicMock()
    light.hass.loop = MagicMock()

    if white_temperature is not None:
        light._white_temperature = white_temperature
    if color_mode_is_rgb:
        light._attr_color_mode = "rgb"

    return light


class TestKelvinProperties:
    """Test that kelvin properties replaced mired properties."""

    def test_has_min_color_temp_kelvin(self):
        light = _make_light()
        assert light.min_color_temp_kelvin == 2700

    def test_has_max_color_temp_kelvin(self):
        light = _make_light()
        assert light.max_color_temp_kelvin == 6500

    def test_no_min_mireds_property(self):
        """min_mireds should no longer exist as a property on AwoxLight itself."""
        light = _make_light()
        # Check that AwoxLight doesn't define min_mireds as a property
        assert "min_mireds" not in type(light).__dict__

    def test_no_max_mireds_property(self):
        """max_mireds should no longer exist as a property on AwoxLight itself."""
        light = _make_light()
        assert "max_mireds" not in type(light).__dict__


class TestColorTempKelvinRead:
    """Test reading color temperature as kelvin from device state."""

    def test_none_when_no_temperature(self):
        light = _make_light(white_temperature=None)
        assert light.color_temp_kelvin is None

    def test_device_zero_is_coolest(self):
        """Device value 0 = coolest = 6500K."""
        light = _make_light(white_temperature=0)
        assert light.color_temp_kelvin == 6500

    def test_device_max_is_warmest(self):
        """Device value 0x7f (127) = warmest = 2700K."""
        light = _make_light(white_temperature=0x7F)
        assert light.color_temp_kelvin == 2700

    def test_device_midpoint(self):
        """Device value ~64 should be roughly mid-range (~4600K)."""
        light = _make_light(white_temperature=64)
        kelvin = light.color_temp_kelvin
        assert 4400 <= kelvin <= 4800


class TestColorTempKelvinWrite:
    """Test that async_turn_on converts kelvin to device values correctly."""

    @pytest.mark.asyncio
    async def test_coolest_kelvin(self):
        """6500K (coolest) should send device value 0."""
        light = _make_light()
        light._state = True
        await light.async_turn_on(color_temp_kelvin=6500)
        light._mesh.async_set_white_temperature.assert_called_once()
        device_val = light._mesh.async_set_white_temperature.call_args[0][1]
        assert device_val == 0

    @pytest.mark.asyncio
    async def test_warmest_kelvin(self):
        """2700K (warmest) should send device value 0x7f (127)."""
        light = _make_light()
        light._state = True
        await light.async_turn_on(color_temp_kelvin=2700)
        light._mesh.async_set_white_temperature.assert_called_once()
        device_val = light._mesh.async_set_white_temperature.call_args[0][1]
        assert device_val == 0x7F

    @pytest.mark.asyncio
    async def test_mid_kelvin(self):
        """~4600K should send a device value near the midpoint."""
        light = _make_light()
        light._state = True
        await light.async_turn_on(color_temp_kelvin=4600)
        light._mesh.async_set_white_temperature.assert_called_once()
        device_val = light._mesh.async_set_white_temperature.call_args[0][1]
        assert 55 <= device_val <= 72


class TestKelvinRoundTrip:
    """Verify write → read round trips are accurate within device resolution."""

    def test_roundtrip_coolest(self):
        light = _make_light()
        light._white_temperature = 0  # device value for 6500K
        assert light.color_temp_kelvin == 6500

    def test_roundtrip_warmest(self):
        light = _make_light()
        light._white_temperature = 0x7F  # device value for 2700K
        assert light.color_temp_kelvin == 2700
