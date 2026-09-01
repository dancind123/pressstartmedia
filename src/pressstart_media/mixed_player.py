import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
}


class MixedMediaWorker:
    IPC_CONNECT_TIMEOUT_SECONDS = 10
    IPC_POLL_SECONDS = 0.25

    def __init__(
        self,
        playlist_path: Path,
        image_duration: int,
        rotation: int,
        audio_enabled: bool,
        state_path: Path,
    ):
        self.playlist_path = playlist_path
        self.image_duration = image_duration
        self.rotation = rotation
        self.audio_enabled = audio_enabled
        self.state_path = state_path

        self.current_process: subprocess.Popen | None = None
        self.stop_requested = False

        runtime_directory = Path(
            os.environ.get(
                "XDG_RUNTIME_DIR",
                f"/run/user/{os.getuid()}",
            )
        )

        self.ipc_path = (
            runtime_directory
            / "pressstart-mixed-mpv.sock"
        )

        self.prepared_to_source: dict[str, Path] = {}

    @staticmethod
    def _find_command(
        command: str,
        package: str,
    ) -> str:
        executable = shutil.which(command)

        if executable:
            return executable

        raise RuntimeError(
            f"{command} was not found. Install it with: "
            f"sudo apt install {package}"
        )

    def _handle_signal(
        self,
        signum,
        frame,
    ) -> None:
        del signum, frame

        self.stop_requested = True
        self._stop_current_process()

    def _stop_current_process(self) -> None:
        process = self.current_process

        if (
            process is None
            or process.poll() is not None
        ):
            return

        process.terminate()

        try:
            process.wait(timeout=3)

        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def _load_playlist(self) -> list[Path]:
        if not self.playlist_path.is_file():
            raise RuntimeError(
                "Playlist was not found: "
                f"{self.playlist_path}"
            )

        items: list[Path] = []

        for raw_line in self.playlist_path.read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw_line.strip()

            if (
                not line
                or line.startswith("#")
            ):
                continue

            path = Path(line)

            if path.is_file():
                items.append(path)

        if not items:
            raise RuntimeError(
                "Playlist contains no playable media: "
                f"{self.playlist_path}"
            )

        return items

    def _write_current_media(
        self,
        path: Path,
    ) -> None:
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = (
            self.state_path.with_suffix(".tmp")
        )

        temporary_path.write_text(
            str(path),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.state_path
        )

    def _clear_current_media(self) -> None:
        try:
            self.state_path.unlink()

        except FileNotFoundError:
            pass

    def _clear_ipc_socket(self) -> None:
        try:
            self.ipc_path.unlink()

        except FileNotFoundError:
            pass

    def _find_output_name(self) -> str | None:
        executable = shutil.which("wlr-randr")

        if not executable:
            return None

        try:
            result = subprocess.run(
                [executable],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )

        except (
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            return None

        for line in result.stdout.splitlines():
            if (
                not line
                or line[0].isspace()
            ):
                continue

            return line.split(
                maxsplit=1
            )[0]

        return None

    def _apply_rotation(self) -> None:
        if self.rotation not in {
            0,
            90,
            180,
            270,
        }:
            raise RuntimeError(
                "Rotation must be one of: "
                "0, 90, 180, 270"
            )

        output_name = self._find_output_name()

        if output_name is None:
            if self.rotation != 0:
                raise RuntimeError(
                    "Unable to identify a Wayland "
                    "output for rotation"
                )

            return

        transform = (
            "normal"
            if self.rotation == 0
            else str(self.rotation)
        )

        subprocess.run(
            [
                self._find_command(
                    "wlr-randr",
                    "wlr-randr",
                ),
                "--output",
                output_name,
                "--transform",
                transform,
            ],
            check=True,
        )

    def _prepare_image(
        self,
        path: Path,
    ) -> Path:
        cache_directory = Path(
            "/home/media/PressStart/"
            "runtime/image-cache"
        )

        cache_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_name = (
            path.name
            .replace("/", "_")
            .replace("\\", "_")
        )

        cache_path = (
            cache_directory
            / f"{safe_name}.png"
        )

        try:
            source_mtime = (
                path.stat().st_mtime_ns
            )

            cache_mtime = (
                cache_path.stat().st_mtime_ns
            )

        except FileNotFoundError:
            source_mtime = (
                path.stat().st_mtime_ns
            )

            cache_mtime = -1

        if cache_mtime >= source_mtime:
            return cache_path

        temporary_path = (
            cache_path.with_suffix(
                ".tmp.png"
            )
        )

        subprocess.run(
            [
                self._find_command(
                    "ffmpeg",
                    "ffmpeg",
                ),
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-vf",
                (
                    "scale=1920:1920:"
                    "force_original_aspect_ratio="
                    "decrease"
                ),
                str(temporary_path),
            ],
            check=True,
        )

        temporary_path.replace(
            cache_path
        )

        return cache_path

    @staticmethod
    def _normalized_path(
        path: Path,
    ) -> str:
        return str(
            path.resolve()
        )

    def _build_runtime_playlist(
        self,
        items: list[Path],
    ) -> Path:
        runtime_directory = Path(
            "/home/media/PressStart/runtime"
        )

        runtime_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        runtime_playlist = (
            runtime_directory
            / "mixed-runtime-playlist.m3u"
        )

        prepared_items: list[Path] = []
        self.prepared_to_source.clear()

        for item in items:
            if (
                item.suffix.lower()
                in IMAGE_EXTENSIONS
            ):
                prepared_path = (
                    self._prepare_image(item)
                )

            else:
                prepared_path = item

            prepared_items.append(
                prepared_path
            )

            self.prepared_to_source[
                self._normalized_path(
                    prepared_path
                )
            ] = item

        temporary_path = (
            runtime_playlist.with_suffix(
                ".tmp"
            )
        )

        playlist_text = "#EXTM3U\n"

        playlist_text += "".join(
            f"{path}\n"
            for path in prepared_items
        )

        temporary_path.write_text(
            playlist_text,
            encoding="utf-8",
        )

        temporary_path.replace(
            runtime_playlist
        )

        return runtime_playlist

    def _build_mpv_command(
        self,
        runtime_playlist: Path,
    ) -> list[str]:
        command = [
            self._find_command(
                "mpv",
                "mpv",
            ),
            "--fullscreen",
            "--no-border",
            "--no-osc",
            "--no-osd-bar",
            "--cursor-autohide=1000",
            "--vo=gpu",
            "--gpu-context=wayland",
            "--hwdec=v4l2m2m-copy",
            "--gpu-shader-cache=no",
            "--cache=no",
            "--no-config",
            (
                "--image-display-duration="
                f"{self.image_duration}"
            ),
            "--loop-playlist=inf",
            (
                "--input-ipc-server="
                f"{self.ipc_path}"
            ),
            (
                "--playlist="
                f"{runtime_playlist}"
            ),
        ]

        if not self.audio_enabled:
            command.append(
                "--no-audio"
            )

        return command

    def _start_player(
        self,
        runtime_playlist: Path,
    ) -> None:
        self._clear_ipc_socket()

        command = self._build_mpv_command(
            runtime_playlist
        )

        self.current_process = (
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
            )
        )

    def _connect_ipc(
        self,
    ) -> socket.socket:
        deadline = (
            time.monotonic()
            + self.IPC_CONNECT_TIMEOUT_SECONDS
        )

        while time.monotonic() < deadline:
            if self.stop_requested:
                raise RuntimeError(
                    "Playback stopped while waiting "
                    "for MPV IPC"
                )

            if (
                self.current_process is not None
                and self.current_process.poll()
                is not None
            ):
                raise RuntimeError(
                    "MPV exited before its IPC "
                    "socket became available"
                )

            if self.ipc_path.exists():
                connection = socket.socket(
                    socket.AF_UNIX,
                    socket.SOCK_STREAM,
                )

                try:
                    connection.connect(
                        str(self.ipc_path)
                    )

                except OSError:
                    connection.close()

                else:
                    connection.settimeout(
                        self.IPC_POLL_SECONDS
                    )

                    return connection

            time.sleep(
                self.IPC_POLL_SECONDS
            )

        raise RuntimeError(
            "Timed out waiting for MPV IPC "
            f"socket: {self.ipc_path}"
        )

    @staticmethod
    def _send_ipc_command(
        connection: socket.socket,
        command: list,
        request_id: int,
    ) -> None:
        message = {
            "command": command,
            "request_id": request_id,
        }

        payload = (
            json.dumps(message)
            + "\n"
        ).encode("utf-8")

        connection.sendall(payload)

    def _request_current_path(
        self,
        connection: socket.socket,
        request_id: int,
    ) -> None:
        self._send_ipc_command(
            connection,
            ["get_property", "path"],
            request_id,
        )

    def _update_current_media(
        self,
        mpv_path: str,
    ) -> None:
        if not mpv_path:
            return

        normalized = self._normalized_path(
            Path(mpv_path)
        )

        source_path = (
            self.prepared_to_source.get(
                normalized,
                Path(mpv_path),
            )
        )

        self._write_current_media(
            source_path
        )

    def _monitor_ipc(
        self,
        connection: socket.socket,
    ) -> int:
        buffer = b""
        request_id = 1

        self._request_current_path(
            connection,
            request_id,
        )

        while (
            not self.stop_requested
            and self.current_process
            is not None
            and self.current_process.poll()
            is None
        ):
            try:
                chunk = connection.recv(
                    65536
                )

            except socket.timeout:
                continue

            except OSError:
                break

            if not chunk:
                break

            buffer += chunk

            while b"\n" in buffer:
                raw_line, buffer = (
                    buffer.split(
                        b"\n",
                        1,
                    )
                )

                if not raw_line:
                    continue

                try:
                    message = json.loads(
                        raw_line.decode(
                            "utf-8"
                        )
                    )

                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ):
                    continue

                if (
                    message.get("event")
                    == "file-loaded"
                ):
                    request_id += 1

                    self._request_current_path(
                        connection,
                        request_id,
                    )

                    continue

                if (
                    message.get("request_id")
                    is not None
                    and message.get("error")
                    == "success"
                ):
                    data = message.get("data")

                    if isinstance(
                        data,
                        str,
                    ):
                        self._update_current_media(
                            data
                        )

        if self.current_process is None:
            return 0

        return self.current_process.wait()

    def run(self) -> int:
        signal.signal(
            signal.SIGTERM,
            self._handle_signal,
        )

        signal.signal(
            signal.SIGINT,
            self._handle_signal,
        )

        self._clear_current_media()
        self._clear_ipc_socket()
        self._apply_rotation()

        connection: (
            socket.socket | None
        ) = None

        try:
            items = self._load_playlist()

            runtime_playlist = (
                self._build_runtime_playlist(
                    items
                )
            )

            self._start_player(
                runtime_playlist
            )

            connection = (
                self._connect_ipc()
            )

            return_code = (
                self._monitor_ipc(
                    connection
                )
            )

            if self.stop_requested:
                return 0

            return return_code

        finally:
            if connection is not None:
                connection.close()

            self._stop_current_process()
            self._clear_current_media()
            self._clear_ipc_socket()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Press Start mixed image/video "
            "playback worker"
        )
    )

    parser.add_argument(
        "--playlist",
        required=True,
    )

    parser.add_argument(
        "--image-duration",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--rotation",
        type=int,
        choices=(
            0,
            90,
            180,
            270,
        ),
        default=0,
    )

    parser.add_argument(
        "--audio",
        choices=(
            "enabled",
            "disabled",
        ),
        default="disabled",
    )

    parser.add_argument(
        "--state-file",
        required=True,
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    worker = MixedMediaWorker(
        playlist_path=Path(
            arguments.playlist
        ),
        image_duration=(
            arguments.image_duration
        ),
        rotation=arguments.rotation,
        audio_enabled=(
            arguments.audio
            == "enabled"
        ),
        state_path=Path(
            arguments.state_file
        ),
    )

    try:
        return worker.run()

    except Exception as error:
        print(
            "Mixed-media worker error: "
            f"{error}",
            file=sys.stderr,
            flush=True,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())