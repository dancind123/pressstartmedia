import os
import shutil
import subprocess
from pathlib import Path

from pressstart_media.status_renderer import StatusRenderer
from pressstart_media.version import BUILD_LABEL


class Display:
    LOGO_PATH = Path(
        "/home/media/PressStart/assets/wallpaper.png"
    )

    def __init__(self):
        self.process = None
        self.status_renderer = StatusRenderer()

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

    def _stop_viewer(self) -> None:
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

    def _show_image(self, image_path: Path) -> None:
        if not image_path.is_file():
            raise RuntimeError(
                f"Display image was not found: {image_path}"
            )

        self._stop_viewer()

        command = [
            self.find_viewer(),
            "--fullscreen",
            "--config=info.show=no",
            str(image_path),
        ]

        self.process = subprocess.Popen(
            command,
            env=self.build_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def show_logo(self) -> None:
        self._show_image(
            self.LOGO_PATH
        )

    def hide_logo(self) -> None:
        self._stop_viewer()

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

    def show_status(
        self,
        title: str,
        message: str = "",
    ) -> None:
        self.show(
            title,
            message,
        )

        status_image = self.status_renderer.render(
            title,
            message,
        )

        self._show_image(
            status_image
        )


if __name__ == "__main__":
    display = Display()

    display.show_status(
        "Display Test",
        "Showing Press Start status screen.",
    )
