import argparse
import fcntl
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from pressstart_media.config import Config


@dataclass
class WaylandOutput:
    name: str
    enabled: bool = False
    current_width: int | None = None
    current_height: int | None = None
    current_refresh: float | None = None
    transform: str = "normal"
    modes: list[tuple[int, int, float]] = field(
        default_factory=list
    )


class DisplayManager:
    CHECK_INTERVAL_SECONDS = 2
    TARGET_WIDTH = 1920
    TARGET_HEIGHT = 1080
    TARGET_REFRESH = 60.0

    # Accept standard 60 Hz-class modes such as 60.000 and 59.940.
    TARGET_REFRESH_TOLERANCE = 1.0

    # Once a specific advertised mode is selected, use a tight comparison
    # to decide whether the display is already running at that mode.
    MODE_MATCH_TOLERANCE = 0.01

    PLAYER_CONFIG_PATH = Path(
        "/home/media/PressStart/config/player.conf"
    )
    LOG_PATH = Path(
        "/home/media/PressStart/logs/display-manager.log"
    )

    OUTPUT_PATTERN = re.compile(
        r"^(\S+)\s+"
    )
    MODE_PATTERN = re.compile(
        r"^\s+(\d+)x(\d+) px, ([0-9.]+) Hz(.*)$"
    )

    def __init__(self, check_interval: float | None = None):
        self.check_interval = (
            check_interval
            if check_interval is not None
            else self.CHECK_INTERVAL_SECONDS
        )
        self.logger = self._build_logger()
        self._last_status: str | None = None
        self._last_config_error: str | None = None

    @classmethod
    def _build_logger(cls) -> logging.Logger:
        logger = logging.getLogger(
            "pressstart_media.display_manager"
        )

        if logger.handlers:
            return logger

        cls.LOG_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        handler = RotatingFileHandler(
            cls.LOG_PATH,
            maxBytes=262144,
            backupCount=2,
            encoding="utf-8",
        )

        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"
            )
        )

        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False

        return logger

    @staticmethod
    def _find_wlr_randr() -> str:
        executable = shutil.which("wlr-randr")

        if executable:
            return executable

        raise RuntimeError(
            "wlr-randr was not found. Install it with: "
            "sudo apt install wlr-randr"
        )

    @classmethod
    def parse_outputs(
        cls,
        output_text: str,
    ) -> list[WaylandOutput]:
        outputs: list[WaylandOutput] = []
        current_output: WaylandOutput | None = None

        for raw_line in output_text.splitlines():
            if not raw_line:
                continue

            if not raw_line[0].isspace():
                match = cls.OUTPUT_PATTERN.match(raw_line)

                if match:
                    current_output = WaylandOutput(
                        name=match.group(1)
                    )
                    outputs.append(current_output)

                continue

            if current_output is None:
                continue

            line = raw_line.strip()

            if line.startswith("Enabled:"):
                current_output.enabled = (
                    line.split(":", 1)[1].strip().lower()
                    == "yes"
                )
                continue

            if line.startswith("Transform:"):
                current_output.transform = (
                    line.split(":", 1)[1].strip()
                )
                continue

            mode_match = cls.MODE_PATTERN.match(raw_line)

            if not mode_match:
                continue

            width = int(mode_match.group(1))
            height = int(mode_match.group(2))
            refresh = float(mode_match.group(3))
            flags = mode_match.group(4)

            current_output.modes.append(
                (width, height, refresh)
            )

            if "current" in flags:
                current_output.current_width = width
                current_output.current_height = height
                current_output.current_refresh = refresh

        return outputs

    def _query_outputs(self) -> list[WaylandOutput]:
        result = subprocess.run(
            [self._find_wlr_randr()],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

        return self.parse_outputs(result.stdout)

    @staticmethod
    def _select_output(
        outputs: list[WaylandOutput],
    ) -> WaylandOutput | None:
        enabled = [
            output
            for output in outputs
            if output.enabled
        ]

        for output in enabled:
            if output.name.startswith("HDMI-"):
                return output

        return enabled[0] if enabled else None

    def _target_mode(
        self,
        output: WaylandOutput,
    ) -> tuple[int, int, float] | None:
        candidates = [
            (width, height, refresh)
            for width, height, refresh in output.modes
            if (
                width == self.TARGET_WIDTH
                and height == self.TARGET_HEIGHT
                and abs(
                    refresh - self.TARGET_REFRESH
                ) <= self.TARGET_REFRESH_TOLERANCE
            )
        ]

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda mode: abs(
                mode[2] - self.TARGET_REFRESH
            ),
        )

    def _desired_rotation(self) -> int:
        if not self.PLAYER_CONFIG_PATH.is_file():
            self._last_config_error = None
            return 0

        try:
            config = Config()
            raw_rotation = config.get_player("ROTATION")
            rotation = int(
                raw_rotation
                if raw_rotation is not None
                else 0
            )

            if rotation not in {0, 90, 180, 270}:
                raise RuntimeError(
                    "ROTATION must be one of: "
                    "0, 90, 180, 270"
                )

        except Exception as error:
            message = str(error)

            if message != self._last_config_error:
                self.logger.warning(
                    "Unable to load display rotation from "
                    "player configuration; using 0 degrees: %s",
                    message,
                )
                self._last_config_error = message

            return 0

        self._last_config_error = None
        return rotation

    @staticmethod
    def _transform_for_rotation(rotation: int) -> str:
        return "normal" if rotation == 0 else str(rotation)

    def _mode_matches(
        self,
        output: WaylandOutput,
        target_mode: tuple[int, int, float],
    ) -> bool:
        width, height, refresh = target_mode

        return (
            output.current_width == width
            and output.current_height == height
            and output.current_refresh is not None
            and abs(
                output.current_refresh - refresh
            ) <= self.MODE_MATCH_TOLERANCE
        )

    def _apply_output_configuration(
        self,
        output: WaylandOutput,
        target_mode: tuple[int, int, float] | None,
        rotation: int,
    ) -> None:
        target_transform = self._transform_for_rotation(
            rotation
        )

        mode_matches = (
            target_mode is None
            or self._mode_matches(
                output,
                target_mode,
            )
        )
        transform_matches = (
            output.transform == target_transform
        )

        if mode_matches and transform_matches:
            if target_mode is None:
                status = (
                    f"{output.name}: 1920x1080 near 60 Hz is not "
                    "advertised; preserving current resolution"
                )
                log_method = self.logger.warning
            else:
                status = (
                    f"{output.name}: display configuration is correct"
                )
                log_method = self.logger.info

            if status != self._last_status:
                log_method(status)
                self._last_status = status

            return

        command = [
            self._find_wlr_randr(),
            "--output",
            output.name,
        ]

        if target_mode is not None and not mode_matches:
            width, height, refresh = target_mode
            command.extend(
                [
                    "--mode",
                    f"{width}x{height}@{refresh:.6f}Hz",
                ]
            )

        if not transform_matches:
            command.extend(
                [
                    "--transform",
                    target_transform,
                ]
            )

        subprocess.run(
            command,
            timeout=5,
            check=True,
        )

        if target_mode is None:
            mode_description = "current resolution"
        else:
            width, height, refresh = target_mode
            mode_description = (
                f"{width}x{height}@{refresh:.6f}Hz"
            )

        status = (
            f"{output.name}: applied {mode_description}, "
            f"rotation {rotation}"
        )
        self.logger.info(status)
        self._last_status = status

    def apply_once(self) -> bool:
        try:
            outputs = self._query_outputs()
            output = self._select_output(outputs)

            if output is None:
                status = "No enabled Wayland output detected"

                if status != self._last_status:
                    self.logger.info(status)
                    self._last_status = status

                return False

            rotation = self._desired_rotation()
            target_mode = self._target_mode(output)

            self._apply_output_configuration(
                output,
                target_mode,
                rotation,
            )

            return True

        except (
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            RuntimeError,
        ) as error:
            status = f"Display configuration failed: {error}"

            if status != self._last_status:
                self.logger.warning(status)
                self._last_status = status

            return False

    def run(self) -> None:
        self.logger.info("Press Start display manager started")

        while True:
            self.apply_once()
            time.sleep(self.check_interval)


def acquire_process_lock() -> object | None:
    runtime_directory = Path(
        os.environ.get(
            "XDG_RUNTIME_DIR",
            f"/run/user/{os.getuid()}",
        )
    )
    lock_path = (
        runtime_directory
        / "pressstart-display-manager.lock"
    )

    lock_file = lock_path.open("w", encoding="utf-8")

    try:
        fcntl.flock(
            lock_file.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )
    except BlockingIOError:
        lock_file.close()
        return None

    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Enforce Press Start Wayland display resolution "
            "and rotation"
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Apply the display configuration once and exit.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    process_lock = acquire_process_lock()

    if process_lock is None:
        return 0

    manager = DisplayManager()

    if arguments.once:
        return 0 if manager.apply_once() else 1

    manager.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
