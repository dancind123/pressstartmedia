#!/usr/bin/env python3

import html
from pathlib import Path
from urllib.parse import quote

from pressstart_media.config import Config


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

IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}


def as_boolean(
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


def path_to_uri(path: Path) -> str:
    absolute_path = str(path.resolve())
    return "file://" + quote(
        absolute_path,
        safe="/",
    )


def collect_media(
    media_folder: Path,
    allow_images: bool,
    recursive: bool,
) -> list[Path]:
    extensions = set(VIDEO_EXTENSIONS)

    if allow_images:
        extensions.update(IMAGE_EXTENSIONS)

    iterator = (
        media_folder.rglob("*")
        if recursive
        else media_folder.iterdir()
    )

    media = sorted(
        (
            path
            for path in iterator
            if path.is_file()
            and path.suffix.lower() in extensions
        ),
        key=lambda path: (
            str(path.relative_to(media_folder)).casefold()
        ),
    )

    return media


def write_xspf(
    playlist_path: Path,
    media: list[Path],
) -> None:
    with playlist_path.open(
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

        for media_path in media:
            playlist.write("    <track>\n")
            playlist.write(
                "      <location>"
                f"{html.escape(path_to_uri(media_path))}"
                "</location>\n"
            )
            playlist.write(
                "      <title>"
                f"{html.escape(media_path.stem)}"
                "</title>\n"
            )
            playlist.write("    </track>\n")

        playlist.write("  </trackList>\n")
        playlist.write("</playlist>\n")


def write_m3u(
    playlist_path: Path,
    media: list[Path],
) -> None:
    with playlist_path.open(
        "w",
        encoding="utf-8",
    ) as playlist:
        playlist.write("#EXTM3U\n")

        for media_path in media:
            playlist.write(
                f"{media_path.resolve()}\n"
            )


def main() -> None:
    config = Config()

    media_folder_value = config.get_player(
        "MEDIA_FOLDER"
    )
    playlist_value = config.get_player(
        "PLAYLIST"
    )

    if not media_folder_value:
        raise RuntimeError(
            "MEDIA_FOLDER is missing from the resolved "
            "player configuration"
        )

    if not playlist_value:
        raise RuntimeError(
            "PLAYLIST is missing from the resolved "
            "player configuration"
        )

    media_folder = Path(media_folder_value)
    playlist_path = Path(playlist_value)

    if not media_folder.is_dir():
        raise SystemExit(
            f"Media folder not found: {media_folder}"
        )

    allow_images = as_boolean(
        config.get_player("ALLOW_IMAGES"),
        "ALLOW_IMAGES",
        False,
    )

    recursive = as_boolean(
        config.get_player("RECURSIVE"),
        "RECURSIVE",
        False,
    )

    media = collect_media(
        media_folder,
        allow_images,
        recursive,
    )

    if not media:
        allowed_description = (
            "supported media files"
            if allow_images
            else "supported video files"
        )

        raise SystemExit(
            f"No {allowed_description} found in: "
            f"{media_folder}"
        )

    playlist_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    suffix = playlist_path.suffix.lower()

    if suffix == ".m3u":
        write_m3u(
            playlist_path,
            media,
        )
    elif suffix == ".xspf":
        write_xspf(
            playlist_path,
            media,
        )
    else:
        raise RuntimeError(
            "Unsupported playlist format: "
            f"{playlist_path.suffix or '(none)'}. "
            "Expected .xspf or .m3u."
        )

    print(
        f"Created playlist: {playlist_path}"
    )
    print(
        f"Media files added: {len(media)}"
    )
    print(
        "Images allowed: "
        f"{'yes' if allow_images else 'no'}"
    )
    print(
        "Recursive scan: "
        f"{'yes' if recursive else 'no'}"
    )


if __name__ == "__main__":
    main()