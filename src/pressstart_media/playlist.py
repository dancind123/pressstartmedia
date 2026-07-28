import html
import random
from pathlib import Path
from urllib.parse import quote


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".webm",
    ".mpg",
    ".mpeg",
}


class PlaylistManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        media_folder = self.config.get_player("MEDIA_FOLDER")
        playlist_path = self.config.get_player("PLAYLIST")

        if not media_folder:
            raise RuntimeError(
                "MEDIA_FOLDER is missing from the resolved "
                "player configuration"
            )

        if not playlist_path:
            raise RuntimeError(
                "PLAYLIST is missing from the resolved "
                "player configuration"
            )

        self.media_folder = Path(media_folder)
        self.playlist_path = Path(playlist_path)

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

    def find_videos(self) -> list[Path]:
        if not self.media_folder.is_dir():
            raise RuntimeError(
                f"Media folder was not found: "
                f"{self.media_folder}"
            )

        videos = [
            path
            for path in self.media_folder.rglob("*")
            if path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
        ]

        videos.sort(
            key=lambda path: (
                str(
                    path.relative_to(
                        self.media_folder
                    )
                ).casefold()
            )
        )

        return videos

    def build_playback_sequence(
        self,
        videos: list[Path],
    ) -> list[Path]:
        sequence = videos.copy()

        shuffle_enabled = self._as_boolean(
            self.config.get_player("SHUFFLE"),
            "SHUFFLE",
            default=True,
        )

        if shuffle_enabled:
            random.SystemRandom().shuffle(sequence)

        return sequence

    @staticmethod
    def path_to_uri(path: Path) -> str:
        absolute_path = str(path.resolve())

        return "file://" + quote(
            absolute_path,
            safe="/",
        )

    def log_playback_sequence(
        self,
        playback_sequence: list[Path],
    ) -> None:
        self.logger.info(
            "Final playback sequence:"
        )

        for position, video in enumerate(
            playback_sequence,
            start=1,
        ):
            relative_path = video.relative_to(
                self.media_folder
            )

            self.logger.info(
                f"  {position:03d}: {relative_path}"
            )

    def generate(self) -> int:
        videos = self.find_videos()

        if not videos:
            raise RuntimeError(
                "No supported video files were found in: "
                f"{self.media_folder}"
            )

        playback_sequence = self.build_playback_sequence(
            videos
        )

        self.log_playback_sequence(
            playback_sequence
        )

        self.playlist_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.playlist_path.with_suffix(
            self.playlist_path.suffix + ".tmp"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as playlist:
            playlist.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
            )

            playlist.write(
                '<playlist version="1" '
                'xmlns="http://xspf.org/ns/0/" '
                'xmlns:vlc="http://www.videolan.org/'
                'vlc/playlist/ns/0/">\n'
            )

            playlist.write(
                "  <title>Press Start Media Playlist</title>\n"
            )

            playlist.write("  <trackList>\n")

            for video in playback_sequence:
                location = html.escape(
                    self.path_to_uri(video)
                )

                title = html.escape(video.stem)

                playlist.write("    <track>\n")

                playlist.write(
                    f"      <location>{location}</location>\n"
                )

                playlist.write(
                    f"      <title>{title}</title>\n"
                )

                playlist.write("    </track>\n")

            playlist.write("  </trackList>\n")
            playlist.write("</playlist>\n")

        temporary_path.replace(
            self.playlist_path
        )

        shuffle_enabled = self._as_boolean(
            self.config.get_player("SHUFFLE"),
            "SHUFFLE",
            default=True,
        )

        self.logger.info(
            f"Playlist created: {self.playlist_path}"
        )

        self.logger.info(
            f"Videos added to playlist: "
            f"{len(playback_sequence)}"
        )

        self.logger.info(
            "Playlist scan: recursive"
        )

        self.logger.info(
            "Playlist order: "
            + (
                "shuffled"
                if shuffle_enabled
                else "alphabetical"
            )
        )

        return len(playback_sequence)
