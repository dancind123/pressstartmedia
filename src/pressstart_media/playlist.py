import html
import random
from pathlib import Path
from urllib.parse import quote


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".mpg", ".mpeg",
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif",
}


class PlaylistManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        media_folder = self.config.get_player("MEDIA_FOLDER")
        playlist_path = self.config.get_player("PLAYLIST")
        if not media_folder:
            raise RuntimeError("MEDIA_FOLDER is missing from the resolved player configuration")
        if not playlist_path:
            raise RuntimeError("PLAYLIST is missing from the resolved player configuration")
        self.media_folder = Path(media_folder)
        self.playlist_path = Path(playlist_path)

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

    def find_media(self) -> list[Path]:
        if not self.media_folder.is_dir():
            raise RuntimeError(f"Media folder was not found: {self.media_folder}")
        extensions = set(VIDEO_EXTENSIONS)
        if self._as_boolean(self.config.get_player("ALLOW_IMAGES"), "ALLOW_IMAGES", False):
            extensions.update(IMAGE_EXTENSIONS)
        recursive = self._as_boolean(
            self.config.get_player("RECURSIVE"),
            "RECURSIVE",
            True,
        )
        candidates = (
            self.media_folder.rglob("*")
            if recursive
            else self.media_folder.glob("*")
        )
        media = [
            path for path in candidates
            if path.is_file() and path.suffix.lower() in extensions
        ]
        media.sort(key=lambda path: str(path.relative_to(self.media_folder)).casefold())
        return media

    def build_playback_sequence(self, media: list[Path]) -> list[Path]:
        sequence = media.copy()
        if self._as_boolean(self.config.get_player("SHUFFLE"), "SHUFFLE", True):
            random.SystemRandom().shuffle(sequence)
        return sequence

    @staticmethod
    def path_to_uri(path: Path) -> str:
        return "file://" + quote(str(path.resolve()), safe="/")

    def log_playback_sequence(self, sequence: list[Path]) -> None:
        self.logger.info("Final playback sequence:")
        for position, item in enumerate(sequence, start=1):
            self.logger.info(f"  {position:03d}: {item.relative_to(self.media_folder)}")

    def _write_xspf(self, playlist, sequence: list[Path]) -> None:
        playlist.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        playlist.write('<playlist version="1" xmlns="http://xspf.org/ns/0/" xmlns:vlc="http://www.videolan.org/vlc/playlist/ns/0/">\n')
        playlist.write("  <title>Press Start Media Playlist</title>\n  <trackList>\n")
        for item in sequence:
            location = html.escape(self.path_to_uri(item))
            title = html.escape(item.stem)
            playlist.write("    <track>\n")
            playlist.write(f"      <location>{location}</location>\n")
            playlist.write(f"      <title>{title}</title>\n")
            playlist.write("    </track>\n")
        playlist.write("  </trackList>\n</playlist>\n")

    @staticmethod
    def _write_m3u(playlist, sequence: list[Path]) -> None:
        playlist.write("#EXTM3U\n")
        for item in sequence:
            playlist.write(str(item.resolve()) + "\n")

    def generate(self) -> int:
        media = self.find_media()
        if not media:
            raise RuntimeError(f"No supported media files were found in: {self.media_folder}")
        sequence = self.build_playback_sequence(media)
        self.log_playback_sequence(sequence)
        self.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.playlist_path.with_suffix(self.playlist_path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as playlist:
            engine = str(self.config.get_player("PLAYBACK_ENGINE") or "vlc").lower()
            if engine in {"mpv", "mixed"}:
                self._write_m3u(playlist, sequence)
            else:
                self._write_xspf(playlist, sequence)
        temporary_path.replace(self.playlist_path)
        shuffle = self._as_boolean(self.config.get_player("SHUFFLE"), "SHUFFLE", True)
        self.logger.info(f"Playlist created: {self.playlist_path}")
        self.logger.info(f"Media items added to playlist: {len(sequence)}")
        recursive = self._as_boolean(
            self.config.get_player("RECURSIVE"),
            "RECURSIVE",
            True,
        )
        self.logger.info(
            "Playlist scan: "
            + ("recursive" if recursive else "base folder only")
        )
        self.logger.info("Playlist order: " + ("shuffled" if shuffle else "alphabetical"))
        return len(sequence)
