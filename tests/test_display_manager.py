import unittest
from unittest.mock import patch

from pressstart_media.display_manager import (
    DisplayManager,
    WaylandOutput,
)


SAMPLE_OUTPUT = \'\'\'HDMI-A-1 "XXX Beyond TV 0x00010000 (HDMI-A-1)"
  Make: XXX
  Model: Beyond TV
  Serial: 0x00010000
  Physical size: 1210x680 mm
  Enabled: yes
  Modes:
    4096x2160 px, 24.000000 Hz (current)
    3840x2160 px, 30.000000 Hz
    1920x1080 px, 60.000000 Hz
    1920x1080 px, 59.939999 Hz
  Position: 0,0
  Transform: normal
  Scale: 1.000000
  Adaptive Sync: disabled
\'\'\'


class DisplayManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = DisplayManager(check_interval=0)

    def test_parse_output_detects_current_mode_and_transform(self):
        outputs = self.manager.parse_outputs(SAMPLE_OUTPUT)

        self.assertEqual(len(outputs), 1)
        output = outputs[0]
        self.assertEqual(output.name, "HDMI-A-1")
        self.assertTrue(output.enabled)
        self.assertEqual(output.current_width, 4096)
        self.assertEqual(output.current_height, 2160)
        self.assertEqual(output.current_refresh, 24.0)
        self.assertEqual(output.transform, "normal")

    def test_target_mode_finds_1080p60(self):
        output = self.manager.parse_outputs(SAMPLE_OUTPUT)[0]

        self.assertEqual(
            self.manager._target_mode(output),
            (1920, 1080, 60.0),
        )

    def test_target_mode_accepts_5994_when_exact_60_is_unavailable(self):
        output = WaylandOutput(
            name="HDMI-A-1",
            enabled=True,
            modes=[
                (4096, 2160, 24.0),
                (1920, 1080, 59.94),
            ],
        )

        self.assertEqual(
            self.manager._target_mode(output),
            (1920, 1080, 59.94),
        )

    @patch("pressstart_media.display_manager.subprocess.run")
    @patch.object(
        DisplayManager,
        "_find_wlr_randr",
        return_value="/usr/bin/wlr-randr",
    )
    def test_apply_sets_mode_and_rotation(
        self,
        _find_wlr_randr,
        run,
    ):
        output = WaylandOutput(
            name="HDMI-A-1",
            enabled=True,
            current_width=4096,
            current_height=2160,
            current_refresh=24.0,
            transform="normal",
            modes=[(1920, 1080, 60.0)],
        )

        self.manager._apply_output_configuration(
            output,
            (1920, 1080, 60.0),
            270,
        )

        run.assert_called_once_with(
            [
                "/usr/bin/wlr-randr",
                "--output",
                "HDMI-A-1",
                "--mode",
                "1920x1080@60.000000Hz",
                "--transform",
                "270",
            ],
            timeout=5,
            check=True,
        )

    @patch("pressstart_media.display_manager.subprocess.run")
    @patch.object(
        DisplayManager,
        "_find_wlr_randr",
        return_value="/usr/bin/wlr-randr",
    )
    def test_apply_does_nothing_when_configuration_matches(
        self,
        _find_wlr_randr,
        run,
    ):
        output = WaylandOutput(
            name="HDMI-A-2",
            enabled=True,
            current_width=1920,
            current_height=1080,
            current_refresh=60.0,
            transform="270",
            modes=[(1920, 1080, 60.0)],
        )

        self.manager._apply_output_configuration(
            output,
            (1920, 1080, 60.0),
            270,
        )

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
