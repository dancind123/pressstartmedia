import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


class Player:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.process = None

        playlist_path = self.config.get_player("PLAYLIST")
        if not playlist_path:
            raise RuntimeError(
                "PLAYLIST is missing from the resolved player configuration"
            )

        self.playlist_path = Path(playlist_path)
        self.engine = str(
            self.config.get_player("PLAYBACK_ENGINE") or "vlc"
        ).strip().lower()

        if self.engine not in {"vlc", "mixed"}:
            raise RuntimeError(
                f"Unsupported playback engine: {self.engine}"
            )

        self.current_media_path = Path(
            f"/run/user/{os.getuid()}/"
            "pressstart-media-current-media"
        )

    @staticmethod
    def _find_command(command: str, package: str) -> str:
        executable = shutil.which(command)
        if executable:
            return executable
        raise RuntimeError(
            f"{command} was not found. Install it with: "
            f"sudo apt install {package}"
        )

    @staticmethod
    def _as_boolean(
        value,
        setting_name: str,
        default: bool,
    ) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value

        normalized = str(value).strip().lower()
        if normalized in ("1", "true", "yes", "on", "enabled"):
            return True
        if normalized in ("0", "false", "no", "off", "disabled"):
            return False

        raise RuntimeError(
            f"{setting_name} has an invalid Boolean value: {value!r}"
        )

    @staticmethod
    def _as_integer(
        value,
        setting_name: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"{setting_name} must be an integer"
            ) from error

        if not minimum <= parsed <= maximum:
            raise RuntimeError(
                f"{setting_name} must be between "
                f"{minimum} and {maximum}"
            )

        return parsed

    def _build_vlc_command(self) -> list[str]:
        command = [
            self._find_command("vlc", "vlc"),
            "--intf=qt",
            "--extraintf=dbus",
            "--fullscreen",
        ]

        command.append(
            "--random"
            if self._as_boolean(
                self.config.get_player("SHUFFLE"),
                "SHUFFLE",
                True,
            )
            else "--no-random"
        )
        command.append(
            "--loop"
            if self._as_boolean(
                self.config.get_player("LOOP"),
                "LOOP",
                True,
            )
            else "--no-loop"
        )

        if not self._as_boolean(
            self.config.get_player("AUDIO"),
            "AUDIO",
            False,
        ):
            command.append("--no-audio")

        command.extend(
            [
                "--no-disable-screensaver",
                "--no-video-title-show",
                "--no-osd",
                "--no-video-deco",
                "--no-metadata-network-access",
                "--no-qt-system-tray",
                "--qt-minimal-view",
                "--no-qt-video-autoresize",
                "--avcodec-hw=none",
                "--mouse-hide-timeout=1000",
                str(self.playlist_path),
            ]
        )
        return command

    def _build_mixed_command(self) -> list[str]:
        image_duration = self._as_integer(
            self.config.get_player("IMAGE_DURATION"),
            "IMAGE_DURATION",
            10,
            1,
            3600,
        )
        rotation = self._as_integer(
            self.config.get_player("ROTATION"),
            "ROTATION",
            0,
            0,
            270,
        )
        if rotation not in {0, 90, 180, 270}:
            raise RuntimeError(
                "ROTATION must be one of: 0, 90, 180, 270"
            )

        audio_enabled = self._as_boolean(
            self.config.get_player("AUDIO"),
            "AUDIO",
            False,
        )

        try:
            self.current_media_path.unlink()
        except FileNotFoundError:
            pass

        return [
            sys.executable,
            "-m",
            "pressstart_media.mixed_player",
            "--playlist",
            str(self.playlist_path),
            "--image-duration",
            str(image_duration),
            "--rotation",
            str(rotation),
            "--audio",
            "enabled" if audio_enabled else "disabled",
            "--state-file",
            str(self.current_media_path),
        ]

    def build_command(self) -> list[str]:
        if not self.playlist_path.is_file():
            raise RuntimeError(
                f"Playlist was not found: {self.playlist_path}"
            )

        if self.engine == "mixed":
            return self._build_mixed_command()

        return self._build_vlc_command()

    def build_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        runtime_directory = Path(
            environment.get(
                "XDG_RUNTIME_DIR",
                f"/run/user/{os.getuid()}",
            )
        )
        wayland_socket = runtime_directory / "wayland-0"

        if not wayland_socket.exists():
            raise RuntimeError(
                "Wayland display socket was not found: "
                f"{wayland_socket}"
            )

        environment["XDG_RUNTIME_DIR"] = str(runtime_directory)
        environment["WAYLAND_DISPLAY"] = "wayland-0"
        environment["QT_QPA_PLATFORM"] = "wayland"
        environment["DBUS_SESSION_BUS_ADDRESS"] = (
            f"unix:path={runtime_directory}/bus"
        )
        environment.pop("DISPLAY", None)
        environment.pop("VLC_VOUT", None)
        return environment

    def start(self) -> None:
        if self.is_running():
            raise RuntimeError(
                f"{self.engine.upper()} player is already running"
            )

        command = self.build_command()
        environment = self.build_environment()

        self.logger.info(
            f"Launching {self.engine.upper()} playback"
        )
        self.logger.info(
            f"Playback engine: {self.engine}"
        )
        self.logger.info(
            "Playback command: " + " ".join(command)
        )

        self.process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
        )

    def _current_media_vlc(self) -> str | None:
        try:
            result = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.mpris.MediaPlayer2.vlc",
                    "--object-path",
                    "/org/mpris/MediaPlayer2",
                    "--method",
                    "org.freedesktop.DBus.Properties.Get",
                    "org.mpris.MediaPlayer2.Player",
                    "Metadata",
                ],
                env=self.build_environment(),
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            return None

        metadata = result.stdout
        url_match = re.search(
            r"'xesam:url': <'([^']+)'>",
            metadata,
        )
        if url_match:
            parsed_url = urlparse(url_match.group(1))
            if parsed_url.path:
                return Path(
                    unquote(parsed_url.path)
                ).name

        title_match = re.search(
            r"'xesam:title': <'([^']+)'>",
            metadata,
        )
        if title_match and title_match.group(1).strip():
            return title_match.group(1).strip()

        return None

    def _current_media_mixed(self) -> str | None:
        try:
            raw_path = self.current_media_path.read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return None

        return Path(raw_path).name if raw_path else None

    def current_media(self) -> str | None:
        if not self.is_running():
            return None

        if self.engine == "mixed":
            return self._current_media_mixed()

        return self._current_media_vlc()

    def is_running(self) -> bool:
        return (
            self.process is not None
            and self.process.poll() is None
        )

    def wait(self) -> int:
        if not self.process:
            raise RuntimeError(
                f"{self.engine.upper()} player has not been started"
            )
        return self.process.wait()

    def stop(self) -> None:
        if not self.is_running():
            return

        self.logger.info(
            f"Stopping {self.engine.upper()} playback"
        )
        self.process.terminate()

        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.logger.warning(
                f"{self.engine.upper()} player did not stop normally; "
                "forcing shutdown"
            )
            self.process.kill()
            self.process.wait()

        if self.engine == "mixed":
            try:
                self.current_media_path.unlink()
            except FileNotFoundError:
                pass
