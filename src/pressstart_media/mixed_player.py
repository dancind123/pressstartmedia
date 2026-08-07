import argparse
import os
import shutil
import signal
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

    @staticmethod
    def _find_command(command: str, package: str) -> str:
        executable = shutil.which(command)
        if executable:
            return executable
        raise RuntimeError(
            f"{command} was not found. Install it with: "
            f"sudo apt install {package}"
        )

    def _handle_signal(self, signum, frame) -> None:
        del signum, frame
        self.stop_requested = True
        self._stop_current_process()

    def _stop_current_process(self) -> None:
        process = self.current_process
        if process is None or process.poll() is not None:
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
                f"Playlist was not found: {self.playlist_path}"
            )

        items = []
        for raw_line in self.playlist_path.read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            path = Path(line)
            if path.is_file():
                items.append(path)

        if not items:
            raise RuntimeError(
                f"Playlist contains no playable media: "
                f"{self.playlist_path}"
            )

        return items

    def _write_current_media(self, path: Path) -> None:
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(
            str(path),
            encoding="utf-8",
        )
        temporary_path.replace(self.state_path)

    def _clear_current_media(self) -> None:
        try:
            self.state_path.unlink()
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
            if not line or line[0].isspace():
                continue
            return line.split(maxsplit=1)[0]

        return None

    def _apply_rotation(self) -> None:
        if self.rotation not in {0, 90, 180, 270}:
            raise RuntimeError(
                "Rotation must be one of: 0, 90, 180, 270"
            )

        output_name = self._find_output_name()
        if output_name is None:
            if self.rotation != 0:
                raise RuntimeError(
                    "Unable to identify a Wayland output for rotation"
                )
            return

        transform = "normal" if self.rotation == 0 else str(self.rotation)
        subprocess.run(
            [
                self._find_command("wlr-randr", "wlr-randr"),
                "--output",
                output_name,
                "--transform",
                transform,
            ],
            check=True,
        )

    def _play_image(self, path: Path) -> None:
        command = [
            self._find_command("swayimg", "swayimg"),
            "--fullscreen",
            "--config=info.show=no",
            str(path),
        ]

        self.current_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + self.image_duration
        while not self.stop_requested:
            if self.current_process.poll() is not None:
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            time.sleep(min(0.1, remaining))

        self._stop_current_process()
        self.current_process = None

    def _play_video(self, path: Path) -> None:
        command = [
            self._find_command("mpv", "mpv"),
            "--fullscreen",
            "--no-border",
            "--no-osc",
            "--no-osd-bar",
            "--cursor-autohide=1000",
            "--vo=gpu-next",
            "--gpu-context=wayland",
            "--hwdec=auto-safe",
            "--keep-open=no",
        ]

        if not self.audio_enabled:
            command.append("--no-audio")

        command.append(str(path))

        self.current_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
        )

        while (
            not self.stop_requested
            and self.current_process.poll() is None
        ):
            time.sleep(0.1)

        if self.stop_requested:
            self._stop_current_process()

        self.current_process = None

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._clear_current_media()
        self._apply_rotation()

        try:
            while not self.stop_requested:
                items = self._load_playlist()

                for item in items:
                    if self.stop_requested:
                        break

                    self._write_current_media(item)

                    if item.suffix.lower() in IMAGE_EXTENSIONS:
                        self._play_image(item)
                    else:
                        self._play_video(item)

            return 0

        finally:
            self._stop_current_process()
            self._clear_current_media()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Press Start mixed image/video playback worker"
    )
    parser.add_argument("--playlist", required=True)
    parser.add_argument(
        "--image-duration",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--rotation",
        type=int,
        choices=(0, 90, 180, 270),
        default=0,
    )
    parser.add_argument(
        "--audio",
        choices=("enabled", "disabled"),
        default="disabled",
    )
    parser.add_argument("--state-file", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    worker = MixedMediaWorker(
        playlist_path=Path(arguments.playlist),
        image_duration=arguments.image_duration,
        rotation=arguments.rotation,
        audio_enabled=(arguments.audio == "enabled"),
        state_path=Path(arguments.state_file),
    )

    try:
        return worker.run()
    except Exception as error:
        print(
            f"Mixed-media worker error: {error}",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
