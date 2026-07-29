import queue
import subprocess
import time
from collections.abc import Callable

from pressstart_media.config import Config
from pressstart_media.display import Display
from pressstart_media.logger import MediaLogger
from pressstart_media.player import Player
from pressstart_media.playlist import PlaylistManager
from pressstart_media.version import BUILD_LABEL


class MediaManager:
    RESTART_DELAY_SECONDS = 5
    REQUESTED_RESTART_DELAY_SECONDS = 1
    VLC_WINDOW_START_DELAY_SECONDS = 2
    COMMAND_POLL_SECONDS = 0.5
    COMMAND_QUEUE_SIZE = 20
    SYSTEM_ACTION_DELAY_SECONDS = 1
    CURRENT_MEDIA_POLL_SECONDS = 2

    SYSTEM_ACTION_COMMANDS = {
        "reboot": (
            "/usr/bin/systemctl",
            "reboot",
        ),
        "shutdown": (
            "/usr/bin/systemctl",
            "poweroff",
        ),
    }

    def __init__(
        self,
        state_callback: (
            Callable[[str, dict | None], None] | None
        ) = None,
    ):
        self.config = Config()

        log_directory = self.config.get_platform("LOGDIR")

        if not log_directory:
            raise RuntimeError(
                "LOGDIR is missing from media.conf"
            )

        self.logger = MediaLogger(log_directory)
        self.display = Display()

        self.playlist = PlaylistManager(
            self.config,
            self.logger,
        )

        self.player = Player(
            self.config,
            self.logger,
        )

        self.state_callback = state_callback
        self.state = "STARTING"
        self.restart_count = 0

        self.command_queue = queue.Queue(
            maxsize=self.COMMAND_QUEUE_SIZE
        )

        self.command_handlers = {
            "restart": self.restart_playback,
            "reload_playlist": self.reload_playlist,
            "reboot": self.reboot_system,
            "shutdown": self.shutdown_system,
        }

        self._requested_exit_reason = None
        self._last_current_media = None
        self._next_current_media_poll = 0.0

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

    def set_state(
        self,
        state: str,
        details: dict | None = None,
    ) -> None:
        self.state = state

        self.logger.info(
            f"STATE -> {state}"
        )

        if self.state_callback is None:
            return

        runtime_details = {
            "restart_count": self.restart_count,
        }

        if details:
            runtime_details.update(details)

        try:
            self.state_callback(
                state,
                runtime_details,
            )

        except Exception as error:
            self.logger.warning(
                "Unable to publish runtime state: "
                f"{error}"
            )

    def _publish_current_media_if_changed(
        self,
        force: bool = False,
    ) -> None:
        now = time.monotonic()

        if (
            not force
            and now < self._next_current_media_poll
        ):
            return

        self._next_current_media_poll = (
            now + self.CURRENT_MEDIA_POLL_SECONDS
        )

        current_media = self.player.current_media()

        if (
            not force
            and current_media == self._last_current_media
        ):
            return

        self._last_current_media = current_media

        if current_media:
            self.logger.info(
                "CURRENT MEDIA -> "
                f"{current_media}"
            )

        if self.state_callback is None:
            return

        try:
            self.state_callback(
                self.state,
                {
                    "restart_count": self.restart_count,
                    "current_media": current_media,
                },
            )

        except Exception as error:
            self.logger.warning(
                "Unable to publish current media: "
                f"{error}"
            )

    def handle_command(
        self,
        command: str,
    ) -> None:
        normalized_command = (
            str(command)
            .strip()
            .lower()
        )

        if normalized_command not in self.command_handlers:
            raise ValueError(
                "Unsupported command: "
                f"{normalized_command}"
            )

        try:
            self.command_queue.put_nowait(
                normalized_command
            )

        except queue.Full as error:
            raise RuntimeError(
                "Command queue is full"
            ) from error

        self.logger.info(
            "COMMAND QUEUED -> "
            f"{normalized_command}"
        )

    def _execute_command(
        self,
        command: str,
    ) -> None:
        handler = self.command_handlers.get(command)

        if handler is None:
            raise ValueError(
                f"No handler exists for command: {command}"
            )

        self.logger.info(
            "COMMAND EXECUTING -> "
            f"{command}"
        )

        try:
            handler()

        except Exception as error:
            self.logger.error(
                "COMMAND FAILED -> "
                f"{command}: {error}"
            )

            self.set_state(
                "COMMAND_ERROR",
                details={
                    "command": command,
                    "error": str(error),
                },
            )

    def _request_player_restart(
        self,
        reason: str,
        state: str,
    ) -> None:
        if not self.player.is_running():
            self.logger.warning(
                f"{reason} requested while VLC is not running"
            )
            return

        self._requested_exit_reason = reason

        self.set_state(
            state,
            details={
                "command": reason,
            },
        )

        self.display.show_logo()
        self.player.stop()

    def restart_playback(self) -> None:
        self._request_player_restart(
            reason="restart",
            state="RESTARTING_PLAYER",
        )

    def reload_playlist(self) -> None:
        self.set_state(
            "RELOADING_PLAYLIST",
            details={
                "command": "reload_playlist",
            },
        )

        self.display.show_status(
            "Reloading Media",
            self.playlist_status_message(),
        )

        video_count = self.playlist.generate()

        self.logger.info(
            "Playlist reloaded successfully"
        )

        self.logger.info(
            f"Reloaded playlist contains {video_count} videos"
        )

        self._request_player_restart(
            reason="reload_playlist",
            state="RESTARTING_PLAYER",
        )

    def _request_system_action(
        self,
        action: str,
        state: str,
    ) -> None:
        if action not in self.SYSTEM_ACTION_COMMANDS:
            raise ValueError(
                f"Unsupported system action: {action}"
            )

        self._requested_exit_reason = action

        self.set_state(
            state,
            details={
                "command": action,
            },
        )

        self.display.show_logo()

        if self.player.is_running():
            self.player.stop()

    def reboot_system(self) -> None:
        self._request_system_action(
            action="reboot",
            state="REBOOTING_SYSTEM",
        )

    def shutdown_system(self) -> None:
        self._request_system_action(
            action="shutdown",
            state="SHUTTING_DOWN_SYSTEM",
        )

    def _execute_system_action(
        self,
        action: str,
    ) -> None:
        command = self.SYSTEM_ACTION_COMMANDS.get(action)

        if command is None:
            raise ValueError(
                f"Unsupported system action: {action}"
            )

        self.logger.info(
            "SYSTEM ACTION EXECUTING -> "
            f"{action}"
        )

        time.sleep(
            self.SYSTEM_ACTION_DELAY_SECONDS
        )

        subprocess.run(
            command,
            check=True,
        )

    def _monitor_player(self) -> int:
        self._publish_current_media_if_changed(
            force=True
        )

        while self.player.is_running():
            try:
                command = self.command_queue.get(
                    timeout=self.COMMAND_POLL_SECONDS
                )

            except queue.Empty:
                self._publish_current_media_if_changed()
                continue

            try:
                self._execute_command(command)

            finally:
                self.command_queue.task_done()

            self._publish_current_media_if_changed()

        return self.player.wait()

    def log_resolved_configuration(self) -> None:
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

        self.logger.info(BUILD_LABEL)

        self.logger.info(
            "Player Name: "
            f"{self.config.get_player('PLAYER_NAME')}"
        )

        self.logger.info(
            "Player Profile: "
            f"{self.config.get_player('PLAYER_PROFILE')}"
        )

        self.logger.info(
            "Media Folder: "
            f"{self.config.get_player('MEDIA_FOLDER')}"
        )

        self.logger.info(
            "Playlist: "
            f"{self.config.get_player('PLAYLIST')}"
        )

        self.logger.info(
            "Playback Policy: "
            f"audio={'enabled' if audio_enabled else 'disabled'}, "
            f"shuffle={'enabled' if shuffle_enabled else 'disabled'}, "
            f"loop={'enabled' if loop_enabled else 'disabled'}"
        )

    def playlist_status_message(self) -> str:
        shuffle_enabled = self._as_boolean(
            self.config.get_player("SHUFFLE"),
            "SHUFFLE",
            default=True,
        )

        if shuffle_enabled:
            return "Generating randomized playlist..."

        return "Generating ordered playlist..."

    def start_player(self) -> None:
        self.set_state("STARTING_PLAYER")

        self.display.show_status(
            "Starting Playback",
            "Launching VLC...",
        )

        self.player.start()

        time.sleep(
            self.VLC_WINDOW_START_DELAY_SECONDS
        )

        self.display.hide_logo()

        self.set_state("PLAYING")

    def run(self) -> None:
        try:
            self.set_state("STARTING")

            self.display.show_status(
                "Starting Platform",
                "Initializing...",
            )

            self.log_resolved_configuration()

            self.set_state(
                "GENERATING_PLAYLIST"
            )

            self.display.show_status(
                "Preparing Media",
                self.playlist_status_message(),
            )

            video_count = self.playlist.generate()

            self.logger.info(
                f"Playlist contains {video_count} videos"
            )

            while True:
                self._requested_exit_reason = None
                self._last_current_media = None
                self._next_current_media_poll = 0.0

                self.start_player()

                exit_code = self._monitor_player()

                self.display.show_logo()

                exit_reason = self._requested_exit_reason

                if exit_reason in {
                    "reboot",
                    "shutdown",
                }:
                    self.logger.info(
                        "VLC stopped for requested system action: "
                        f"{exit_reason}"
                    )

                    self._execute_system_action(
                        exit_reason
                    )

                    return

                if exit_reason in {
                    "restart",
                    "reload_playlist",
                }:
                    self.logger.info(
                        "VLC stopped for requested action: "
                        f"{exit_reason}"
                    )

                    restart_delay = (
                        self.REQUESTED_RESTART_DELAY_SECONDS
                    )

                    if exit_reason == "reload_playlist":
                        restart_message = (
                            "Playlist reloaded"
                        )
                    else:
                        restart_message = (
                            "Restart requested"
                        )

                else:
                    self.logger.warning(
                        f"VLC exited with code {exit_code}"
                    )

                    restart_delay = (
                        self.RESTART_DELAY_SECONDS
                    )

                    restart_message = (
                        "VLC stopped unexpectedly"
                    )

                    self.set_state(
                        "PLAYER_EXITED",
                        details={
                            "exit_code": exit_code,
                        },
                    )

                self.restart_count += 1

                self.set_state(
                    "WAITING_TO_RESTART",
                    details={
                        "exit_code": exit_code,
                        "exit_reason": (
                            exit_reason or "unexpected"
                        ),
                        "restart_delay_seconds": (
                            restart_delay
                        ),
                    },
                )

                self.display.show_status(
                    "Restarting Playback",
                    restart_message,
                )

                time.sleep(restart_delay)

        except KeyboardInterrupt:
            self.logger.info(
                "Shutdown requested"
            )

            self.set_state("STOPPING")

            self.player.stop()
            self.display.hide_logo()

            self.set_state("STOPPED")

        except Exception as error:
            self.logger.error(
                f"Platform error: {error}"
            )

            self.set_state(
                "ERROR",
                details={
                    "error": str(error),
                },
            )

            self.player.stop()

            try:
                self.display.show_logo()
            except Exception as display_error:
                self.logger.error(
                    "Unable to show logo after platform error: "
                    f"{display_error}"
                )

            raise
