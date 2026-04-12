"""Tests for convert_value_to_available_range."""
from custom_components.awox.light import convert_value_to_available_range


class TestConvertValueToAvailableRange:
    """Baseline tests for the range conversion helper."""

    def test_min_input_maps_to_min_output(self):
        assert convert_value_to_available_range(0, 0, 127, 100, 200) == 100

    def test_max_input_maps_to_max_output(self):
        assert convert_value_to_available_range(127, 0, 127, 100, 200) == 200

    def test_midpoint(self):
        result = convert_value_to_available_range(64, 0, 127, 0, 255)
        # 64/127 * 255 ≈ 128.5 → 129
        assert result == 129

    def test_clamps_below_min(self):
        """Input below min_from should clamp to min_to."""
        result = convert_value_to_available_range(-10, 0, 127, 100, 200)
        assert result == 100

    def test_clamps_above_max(self):
        """Input above max_from should clamp to max_to."""
        result = convert_value_to_available_range(200, 0, 127, 100, 200)
        assert result == 200

    def test_device_brightness_white(self):
        """Reproduce actual brightness conversion: device 1-0x7f → HA 0-255."""
        assert convert_value_to_available_range(1, 1, 0x7f, 0, 255) == 0
        assert convert_value_to_available_range(0x7f, 1, 0x7f, 0, 255) == 255
        assert convert_value_to_available_range(0x40, 1, 0x7f, 0, 255) == 128

    def test_device_color_temp_mired_old(self):
        """Reproduce OLD mired conversion: device 0-0x7f → mireds 153-370.

        This locks in the existing behavior before the kelvin migration.
        Device 0 = coolest (153 mireds / 6500K).
        Device 127 = warmest (370 mireds / 2700K).
        """
        assert convert_value_to_available_range(0, 0, 0x7f, 153, 370) == 153
        assert convert_value_to_available_range(0x7f, 0, 0x7f, 153, 370) == 370
