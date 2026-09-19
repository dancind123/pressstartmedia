import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse


IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}


class DualImagePlayer:
    def __init__(
        self,
        playlist_path: str,
        state_file: str,
    ) -> None:
        self.playlist_path = Path(playlist_path)
        self.state_file = Path(state_file)

        self.viewer_path = self._find_viewer()

        self.right_process = None
        self.left_process = None

        self.stopping = False

    @staticmethod
    def _find_viewer() -> str:
        executable = shutil.which("swayimg")

        if executable is None:
            raise RuntimeError(
                "swayimg was not found. Install it with: "
                "sudo apt install swayimg"
            )

        return executable

    @staticmethod
    def _playlist_entry_to_path(entry: str) -> Path:
        entry = entry.strip()

        if entry.startswith("file://"):
            parsed = urlparse(entry)
            return Path(unquote(parsed.path))

        return Path(entry)

    def _read_playlist(self) -> list[Path]:
        if not self.playlist_path.is_file():
            raise RuntimeError(
                f"Playlist does not exist: {self.playlist_path}"
            )

        entries = []

        with self.playlist_path.open(
            "r",
            encoding="utf-8-sig",
        ) as playlist_file:
            for raw_line in playlist_file:
                line = raw_line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                path = self._playlist_entry_to_path(line)

                if path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue

                if not path.is_file():
                    continue

                entries.append(path)

        if not entries:
            raise RuntimeError(
                "The dual-image playlist contains no usable images."
            )

        return entries

    def _write_state(self, image_path: Path) -> None:
        self.state_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.state_file.write_text(
            str(image_path),
            encoding="utf-8",
        )

    def _clear_state(self) -> None:
        try:
            self.state_file.unlink()
        except FileNotFoundError:
            pass

    def _viewer_command(
        self,
        window_class: str,
        image_path: Path,
    ) -> list[str]:
        return [
            self.viewer_path,
            f"--class={window_class}",
            "--config=info.show=no",
            str(image_path),
        ]

    def _start_viewers(self, image_path: Path) -> None:
        self._stop_viewers()

        self.right_process = subprocess.Popen(
            self._viewer_command(
                "pressstart-downstairs-right",
                image_path,
            )
        )

        time.sleep(1)

        self.left_process = subprocess.Popen(
            self._viewer_command(
                "pressstart-downstairs-left",
                image_path,
            )
        )

        self._write_state(image_path)

    @staticmethod
    def _stop_process(process) -> None:
        if process is None:
            return

        if process.poll() is not None:
            return

        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _stop_viewers(self) -> None:
        self._stop_process(self.right_process)
        self._stop_process(self.left_process)

        self.right_process = None
        self.left_process = None

    def _viewers_running(self) -> bool:
        if self.right_process is None:
            return False

        if self.left_process is None:
            return False

        if self.right_process.poll() is not None:
            return False

        if self.left_process.poll() is not None:
            return False

        return True

    def request_stop(
        self,
        signum=None,
        frame=None,
    ) -> None:
        self.stopping = True

    def run(self) -> int:
        images = self._read_playlist()

        # Production behavior for the current Downstairs Bar:
        # display the first playlist image on both televisions and
        # leave both swayimg processes running continuously.
        #
        # Future scheduled image rotation belongs here rather than in
        # the generic Player class.
        current_image = images[0]

        self._start_viewers(current_image)

        try:
            while not self.stopping:
                if not self._viewers_running():
                    raise RuntimeError(
                        "One or both dual-image viewers stopped unexpectedly."
                    )

                time.sleep(1)
        finally:
            self._stop_viewers()
            self._clear_state()

        return 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Press Start dual-display image player"
        )
    )

    parser.add_argument(
        "--playlist",
        required=True,
        help="M3U playlist containing image paths.",
    )

    parser.add_argument(
        "--state-file",
        required=True,
        help="File used to report the currently displayed image.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    player = DualImagePlayer(
        playlist_path=arguments.playlist,
        state_file=arguments.state_file,
    )

    signal.signal(
        signal.SIGTERM,
        player.request_stop,
    )

    signal.signal(
        signal.SIGINT,
        player.request_stop,
    )

    try:
        return player.run()
    except Exception as error:
        print(
            f"Dual-image player error: {error}",
            file=sys.stderr,
            flush=True,
        )

        player._stop_viewers()
        player._clear_state()

        return 1


if __name__ == "__main__":
    raise SystemExit(main())