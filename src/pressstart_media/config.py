from pathlib import Path
import shlex

from pressstart_media.profiles import get_profile


class Config:
    def __init__(self):
        self.platform = self._read_config(
            Path("/home/media/PressStart/config/media.conf")
        )

        player_config = self._read_config(
            Path("/home/media/PressStart/config/player.conf")
        )

        self.player = self._resolve_player_config(
            player_config
        )

    def _read_config(self, path: Path) -> dict:
        config = {}

        if not path.is_file():
            raise RuntimeError(
                f"Configuration file was not found: {path}"
            )

        for raw_line in path.read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            parsed = shlex.split(
                value,
                comments=True,
            )

            config[key.strip()] = (
                parsed[0] if parsed else ""
            )

        return config

    def _resolve_player_config(
        self,
        player_config: dict,
    ) -> dict:
        profile_name = (
            player_config.get("PLAYER_PROFILE")
            or player_config.get("PLAYER_TYPE")
        )

        if not profile_name:
            raise RuntimeError(
                "PLAYER_PROFILE is missing from player.conf"
            )

        resolved = get_profile(profile_name)

        resolved["PLAYER_PROFILE"] = profile_name

        player_name = player_config.get("PLAYER_NAME")

        if player_name:
            resolved["PLAYER_NAME"] = player_name
        else:
            resolved["PLAYER_NAME"] = profile_name

        override_keys = (
            "MEDIA_FOLDER",
            "PLAYLIST",
            "AUDIO",
            "SHUFFLE",
            "LOOP",
            "PLAYBACK_ENGINE",
            "ALLOW_IMAGES",
            "RECURSIVE",
            "IMAGE_DURATION",
            "ROTATION",
        )

        for key in override_keys:
            if key in player_config:
                resolved[key] = player_config[key]

        return resolved

    def get_platform(self, key):
        return self.platform.get(key)

    def get_player(self, key):
        return self.player.get(key)
