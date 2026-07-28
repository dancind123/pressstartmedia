import os
import shutil
import subprocess
from pathlib import Path

from pressstart_media.version import BUILD_LABEL


class Display:
    LOGO_PATH = Path(
        "/home/media/PressStart/assets/wallpaper.png"
    )

    def __init__(self):
        self.process = None

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

        environment["DBUS_SESSION_BUS_ADDRESS"] = (
            f"unix:path={runtime_directory}/bus"
        )

        environment.pop("DISPLAY", None)

        return environment

    def find_viewer(self) -> str:
        executable = shutil.which("swayimg")

        if executable:
            return executable

        raise RuntimeError(
            "swayimg was not found. Install it with: "
            "sudo apt install swayimg"
        )

    def show_logo(self) -> None:
        if self.process and self.process.poll() is None:
            return

        if not self.LOGO_PATH.is_file():
            raise RuntimeError(
                f"Logo image was not found: "
                f"{self.LOGO_PATH}"
            )

        command = [
            self.find_viewer(),
            "--fullscreen",
            "--config=info.show=no",
            str(self.LOGO_PATH),
        ]

        self.process = subprocess.Popen(
            command,
            env=self.build_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def hide_logo(self) -> None:
        if not self.process:
            return

        if self.process.poll() is not None:
            self.process = None
            return

        self.process.terminate()

        try:
            self.process.wait(timeout=3)

        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

        self.process = None

    def show(self, title: str, message: str = "") -> None:
        print()
        print("=" * 60)
        print(BUILD_LABEL)
        print("-" * 60)
        print(title)

        if message:
            print()
            print(message)

        print("=" * 60)
        print()


if __name__ == "__main__":
    display = Display()

    display.show(
        "Display Test",
        "Showing Press Start logo."
    )

    display.show_logo()
