import os
import re
import shutil
import subprocess
from urllib.parse import unquote, urlparse
from pathlib import Path


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

    def find_vlc(self) -> str:
        for command in ("vlc", "cvlc"):
            executable = shutil.which(command)

            if executable:
                return executable

        raise RuntimeError(
            "VLC was not found. Install it with: "
            "sudo apt install vlc"
        )

    def _as_boolean(
        self,
        value,
        setting_name: str,
        default: bool,
    ) -> bool:
        if value is None:
            return default

        if isinstance(value, bool):
            return value

        normalized = str(value).strip().lower()

        if normalized in (
            "1",
            "true",
            "yes",
            "on",
            "enabled",
        ):
            return True

        if normalized in (
            "0",
            "false",
            "no",
            "off",
            "disabled",
        ):
            return False

        raise RuntimeError(
            f"{setting_name} has an invalid Boolean value: "
            f"{value!r}"
        )

    def build_command(self) -> list[str]:
        vlc_command = self.find_vlc()

        if not self.playlist_path.is_file():
            raise RuntimeError(
                f"Playlist was not found: "
                f"{self.playlist_path}"
            )

        audio_enabled = self._as_boolean(
            self.config.get_player("AUDIO"),
            "AUDIO",
            default=False,
        )

        shuffle_enabled = self._as_boolean(
            self.config.get_player("SHUFFLE"),
            "SHUFFLE",
            default=True,
        )

        loop_enabled = self._as_boolean(
            self.config.get_player("LOOP"),
            "LOOP",
            default=True,
        )

        command = [
            vlc_command,
            "--intf=qt",
            "--extraintf=dbus",
            "--fullscreen",
        ]

        if shuffle_enabled:
            command.append("--random")
        else:
            command.append("--no-random")

        if loop_enabled:
            command.append("--loop")
        else:
            command.append("--no-loop")

        if not audio_enabled:
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

        environment["XDG_RUNTIME_DIR"] = str(
            runtime_directory
        )

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
                "VLC is already running"
            )

        command = self.build_command()
        environment = self.build_environment()

        audio_enabled = self._as_boolean(
            self.config.get_player("AUDIO"),
            "AUDIO",
            default=False,
        )

        shuffle_enabled = self._as_boolean(
            self.config.get_player("SHUFFLE"),
            "SHUFFLE",
            default=True,
        )

        loop_enabled = self._as_boolean(
            self.config.get_player("LOOP"),
            "LOOP",
            default=True,
        )

        self.logger.info("Launching VLC")

        self.logger.info(
            "Playback mode: "
            f"fullscreen, "
            f"shuffle={'enabled' if shuffle_enabled else 'disabled'}, "
            f"loop={'enabled' if loop_enabled else 'disabled'}, "
            f"audio={'enabled' if audio_enabled else 'disabled'}"
        )

        self.logger.info(
            "Video decoding: software"
        )

        self.logger.info(
            "VLC interface: persistent Qt fullscreen window"
        )

        self.logger.info(
            "Qt platform: Wayland"
        )

        self.logger.info(
            "XDG_RUNTIME_DIR: "
            + environment["XDG_RUNTIME_DIR"]
        )

        self.logger.info(
            "WAYLAND_DISPLAY: "
            + environment["WAYLAND_DISPLAY"]
        )

        self.logger.info(
            "VLC command: "
            + " ".join(command)
        )

        self.process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
        )

    def current_media(self) -> str | None:
        if not self.is_running():
            return None

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
            parsed_url = urlparse(
                url_match.group(1)
            )

            if parsed_url.path:
                return Path(
                    unquote(parsed_url.path)
                ).name

        title_match = re.search(
            r"'xesam:title': <'([^']+)'>",
            metadata,
        )

        if title_match:
            title = title_match.group(1).strip()

            if title:
                return title

        return None

    def is_running(self) -> bool:
        return (
            self.process is not None
            and self.process.poll() is None
        )

    def wait(self) -> int:
        if not self.process:
            raise RuntimeError(
                "VLC has not been started"
            )

        return self.process.wait()

    def stop(self) -> None:
        if not self.is_running():
            return

        self.logger.info(
            "Stopping VLC"
        )

        self.process.terminate()

        try:
            self.process.wait(timeout=5)

        except subprocess.TimeoutExpired:
            self.logger.warning(
                "VLC did not stop normally; forcing shutdown"
            )

            self.process.kill()
            self.process.wait()
