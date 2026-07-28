#!/usr/bin/env python3

import html
import os
import shlex
from pathlib import Path
from urllib.parse import quote

PLATFORM_CONFIG = Path("/home/media/PressStart/config/media.conf")
PLAYER_CONFIG = Path("/home/media/PressStart/config/player.conf")

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


def read_config(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        parsed = shlex.split(value, comments=True)
        config[key.strip()] = parsed[0] if parsed else ""

    return config


def path_to_uri(path: Path) -> str:
    absolute_path = str(path.resolve())
    return "file://" + quote(absolute_path, safe="/")


platform = read_config(PLATFORM_CONFIG)
player = read_config(PLAYER_CONFIG)

media_folder = Path(player["MEDIA_FOLDER"])
playlist_path = Path(player["PLAYLIST"])

if not media_folder.is_dir():
    raise SystemExit(f"Media folder not found: {media_folder}")

videos = sorted(
    (
        path
        for path in media_folder.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ),
    key=lambda path: path.name.casefold(),
)

if not videos:
    raise SystemExit(f"No supported video files found in: {media_folder}")

playlist_path.parent.mkdir(parents=True, exist_ok=True)

with playlist_path.open("w", encoding="utf-8") as playlist:
    playlist.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    playlist.write(
        '<playlist version="1" '
        'xmlns="http://xspf.org/ns/0/" '
        'xmlns:vlc="http://www.videolan.org/vlc/playlist/ns/0/">\n'
    )
    playlist.write("  <title>Press Start Media Playlist</title>\n")
    playlist.write("  <trackList>\n")

    for video in videos:
        playlist.write("    <track>\n")
        playlist.write(
            f"      <location>{html.escape(path_to_uri(video))}</location>\n"
        )
        playlist.write(f"      <title>{html.escape(video.stem)}</title>\n")
        playlist.write("    </track>\n")

    playlist.write("  </trackList>\n")
    playlist.write("</playlist>\n")

print(f"Created playlist: {playlist_path}")
print(f"Videos added: {len(videos)}")
