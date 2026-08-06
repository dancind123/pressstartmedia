import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse


class Player:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.process = None
        playlist_path = self.config.get_player("PLAYLIST")
        if not playlist_path:
            raise RuntimeError("PLAYLIST is missing from the resolved player configuration")
        self.playlist_path = Path(playlist_path)
        self.engine = str(self.config.get_player("PLAYBACK_ENGINE") or "vlc").strip().lower()
        if self.engine not in {"vlc", "mpv"}:
            raise RuntimeError(f"Unsupported playback engine: {self.engine}")
        self.mpv_socket_path = Path(f"/run/user/{os.getuid()}/pressstart-media-mpv.sock")

    def _find_command(self, command: str, package: str) -> str:
        executable = shutil.which(command)
        if executable:
            return executable
        raise RuntimeError(f"{command} was not found. Install it with: sudo apt install {package}")

    def _as_boolean(self, value, setting_name: str, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in ("1", "true", "yes", "on", "enabled"):
            return True
        if normalized in ("0", "false", "no", "off", "disabled"):
            return False
        raise RuntimeError(f"{setting_name} has an invalid Boolean value: {value!r}")

    def _as_integer(self, value, setting_name: str, default: int, minimum: int, maximum: int) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"{setting_name} must be an integer") from error
        if not minimum <= parsed <= maximum:
            raise RuntimeError(f"{setting_name} must be between {minimum} and {maximum}")
        return parsed

    def _build_vlc_command(self) -> list[str]:
        command = [self._find_command("vlc", "vlc"), "--intf=qt", "--extraintf=dbus", "--fullscreen"]
        command.append("--random" if self._as_boolean(self.config.get_player("SHUFFLE"), "SHUFFLE", True) else "--no-random")
        command.append("--loop" if self._as_boolean(self.config.get_player("LOOP"), "LOOP", True) else "--no-loop")
        if not self._as_boolean(self.config.get_player("AUDIO"), "AUDIO", False):
            command.append("--no-audio")
        command.extend([
            "--no-disable-screensaver", "--no-video-title-show", "--no-osd", "--no-video-deco",
            "--no-metadata-network-access", "--no-qt-system-tray", "--qt-minimal-view",
            "--no-qt-video-autoresize", "--avcodec-hw=none", "--mouse-hide-timeout=1000",
            str(self.playlist_path),
        ])
        return command

    def _build_mpv_command(self) -> list[str]:
        image_duration = self._as_integer(self.config.get_player("IMAGE_DURATION"), "IMAGE_DURATION", 10, 1, 3600)
        rotation = self._as_integer(self.config.get_player("ROTATION"), "ROTATION", 0, 0, 270)
        if rotation not in {0, 90, 180, 270}:
            raise RuntimeError("ROTATION must be one of: 0, 90, 180, 270")
        try:
            self.mpv_socket_path.unlink()
        except FileNotFoundError:
            pass
        command = [
            self._find_command("mpv", "mpv"),
            "--fullscreen", "--no-border", "--no-osc", "--no-osd-bar", "--cursor-autohide=1000",
            "--vo=gpu-next", "--gpu-context=wayland", "--hwdec=auto-safe",
            f"--image-display-duration={image_duration}", f"--video-rotate={rotation}",
            f"--input-ipc-server={self.mpv_socket_path}",
            f"--playlist={self.playlist_path}",
        ]
        if not self._as_boolean(self.config.get_player("AUDIO"), "AUDIO", False):
            command.append("--no-audio")
        if self._as_boolean(self.config.get_player("LOOP"), "LOOP", True):
            command.append("--loop-playlist=inf")
        else:
            command.append("--loop-playlist=no")
        return command

    def build_command(self) -> list[str]:
        if not self.playlist_path.is_file():
            raise RuntimeError(f"Playlist was not found: {self.playlist_path}")
        return self._build_mpv_command() if self.engine == "mpv" else self._build_vlc_command()

    def build_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        runtime_directory = Path(environment.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        wayland_socket = runtime_directory / "wayland-0"
        if not wayland_socket.exists():
            raise RuntimeError(f"Wayland display socket was not found: {wayland_socket}")
        environment["XDG_RUNTIME_DIR"] = str(runtime_directory)
        environment["WAYLAND_DISPLAY"] = "wayland-0"
        environment["QT_QPA_PLATFORM"] = "wayland"
        environment["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime_directory}/bus"
        environment.pop("DISPLAY", None)
        environment.pop("VLC_VOUT", None)
        return environment

    def start(self) -> None:
        if self.is_running():
            raise RuntimeError(f"{self.engine.upper()} is already running")
        command = self.build_command()
        environment = self.build_environment()
        self.logger.info(f"Launching {self.engine.upper()}")
        self.logger.info(f"Playback engine: {self.engine}")
        self.logger.info("Playback command: " + " ".join(command))
        self.process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL)

    def _current_media_vlc(self) -> str | None:
        try:
            result = subprocess.run([
                "gdbus", "call", "--session", "--dest", "org.mpris.MediaPlayer2.vlc",
                "--object-path", "/org/mpris/MediaPlayer2", "--method",
                "org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player", "Metadata",
            ], env=self.build_environment(), capture_output=True, text=True, timeout=2, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
        metadata = result.stdout
        url_match = re.search(r"'xesam:url': <'([^']+)'>", metadata)
        if url_match:
            parsed_url = urlparse(url_match.group(1))
            if parsed_url.path:
                return Path(unquote(parsed_url.path)).name
        title_match = re.search(r"'xesam:title': <'([^']+)'>", metadata)
        return title_match.group(1).strip() if title_match and title_match.group(1).strip() else None

    def _current_media_mpv(self) -> str | None:
        if not self.mpv_socket_path.exists():
            return None
        request = json.dumps({"command": ["get_property", "path"]}).encode("utf-8") + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(self.mpv_socket_path))
                client.sendall(request)
                response = b""
                while b"\n" not in response:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            payload = json.loads(response.splitlines()[0].decode("utf-8"))
            path = payload.get("data")
            return Path(path).name if path else None
        except (OSError, ValueError, IndexError, json.JSONDecodeError):
            return None

    def current_media(self) -> str | None:
        if not self.is_running():
            return None
        return self._current_media_mpv() if self.engine == "mpv" else self._current_media_vlc()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def wait(self) -> int:
        if not self.process:
            raise RuntimeError(f"{self.engine.upper()} has not been started")
        return self.process.wait()

    def stop(self) -> None:
        if not self.is_running():
            return
        self.logger.info(f"Stopping {self.engine.upper()}")
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.logger.warning(f"{self.engine.upper()} did not stop normally; forcing shutdown")
            self.process.kill()
            self.process.wait()
        if self.engine == "mpv":
            try:
                self.mpv_socket_path.unlink()
            except FileNotFoundError:
                pass
