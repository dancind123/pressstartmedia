import json
import os
import re
from pathlib import Path
from typing import Any

from pressstart_media.profiles import PROFILES


class ProvisioningError(RuntimeError):
    pass


class ProvisioningConfig:
    DEFAULT_CONFIG_PATH = Path(
        "/home/media/PressStart/config/player.conf"
    )

    PLAYER_NAME_MIN_LENGTH = 1
    PLAYER_NAME_MAX_LENGTH = 80

    def __init__(self, config_path=None):
        self.config_path = Path(
            config_path or self.DEFAULT_CONFIG_PATH
        )

    def parse_payload(
        self,
        payload: bytes | str | dict[str, Any],
    ) -> dict[str, str]:
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ProvisioningError(
                    "Configuration payload is not valid UTF-8"
                ) from error

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as error:
                raise ProvisioningError(
                    "Configuration payload is not valid JSON"
                ) from error

        if not isinstance(payload, dict):
            raise ProvisioningError(
                "Configuration payload must be a JSON object"
            )

        return self.validate(payload)

    def validate(
        self,
        values: dict[str, Any],
    ) -> dict[str, str]:
        allowed_keys = {
            "player_name",
            "player_profile",
            "player_type",
            "image_duration",
            "rotation",
        }

        unknown_keys = set(values) - allowed_keys

        if unknown_keys:
            unknown = ", ".join(
                sorted(unknown_keys)
            )

            raise ProvisioningError(
                f"Unknown configuration field(s): {unknown}"
            )

        player_name = values.get("player_name")

        if not isinstance(player_name, str):
            raise ProvisioningError(
                "player_name must be a string"
            )

        player_name = player_name.strip()

        if not (
            self.PLAYER_NAME_MIN_LENGTH
            <= len(player_name)
            <= self.PLAYER_NAME_MAX_LENGTH
        ):
            raise ProvisioningError(
                "player_name must contain between "
                f"{self.PLAYER_NAME_MIN_LENGTH} and "
                f"{self.PLAYER_NAME_MAX_LENGTH} characters"
            )

        if any(
            character in player_name
            for character in ("\n", "\r", "\0")
        ):
            raise ProvisioningError(
                "player_name contains invalid characters"
            )

        player_profile = values.get("player_profile")
        legacy_player_type = values.get("player_type")

        if (
            player_profile is not None
            and legacy_player_type is not None
            and player_profile != legacy_player_type
        ):
            raise ProvisioningError(
                "player_profile and legacy player_type "
                "must match when both are provided"
            )

        profile_name = (
            player_profile
            if player_profile is not None
            else legacy_player_type
        )

        if not isinstance(profile_name, str):
            raise ProvisioningError(
                "player_profile must be a string"
            )

        profile_name = profile_name.strip()

        if not re.fullmatch(
            r"[a-z0-9_]+",
            profile_name,
        ):
            raise ProvisioningError(
                "player_profile may contain only lowercase "
                "letters, numbers, and underscores"
            )

        if profile_name not in PROFILES:
            supported = ", ".join(
                sorted(PROFILES)
            )

            raise ProvisioningError(
                f"Unsupported player_profile: {profile_name}. "
                f"Supported profiles: {supported}"
            )

        result = {
            "player_name": player_name,
            "player_profile": profile_name,
        }

        image_duration = values.get("image_duration")
        if image_duration is not None:
            try:
                image_duration = int(image_duration)
            except (TypeError, ValueError) as error:
                raise ProvisioningError(
                    "image_duration must be an integer"
                ) from error
            if not 1 <= image_duration <= 3600:
                raise ProvisioningError(
                    "image_duration must be between 1 and 3600 seconds"
                )
            result["image_duration"] = str(image_duration)

        rotation = values.get("rotation")
        if rotation is not None:
            try:
                rotation = int(rotation)
            except (TypeError, ValueError) as error:
                raise ProvisioningError(
                    "rotation must be one of: 0, 90, 180, 270"
                ) from error
            if rotation not in {0, 90, 180, 270}:
                raise ProvisioningError(
                    "rotation must be one of: 0, 90, 180, 270"
                )
            result["rotation"] = str(rotation)

        return result

    def resolve(
        self,
        configuration: dict[str, str],
    ) -> dict[str, str]:
        validated = self.validate(configuration)

        resolved = {
            "PLAYER_NAME": validated["player_name"],
            "PLAYER_PROFILE": validated["player_profile"],
        }
        if "image_duration" in validated:
            resolved["IMAGE_DURATION"] = validated["image_duration"]
        if "rotation" in validated:
            resolved["ROTATION"] = validated["rotation"]
        return resolved

    @staticmethod
    def _quote(value: str) -> str:
        escaped = (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )

        return f'"{escaped}"'

    def render(
        self,
        resolved: dict[str, str],
    ) -> str:
        required_keys = (
            "PLAYER_NAME",
            "PLAYER_PROFILE",
        )

        missing_keys = [
            key
            for key in required_keys
            if not resolved.get(key)
        ]

        if missing_keys:
            missing = ", ".join(missing_keys)

            raise ProvisioningError(
                "Resolved configuration is missing: "
                f"{missing}"
            )

        lines = [
            (
                "PLAYER_NAME="
                f"{self._quote(resolved['PLAYER_NAME'])}"
            ),
            (
                "PLAYER_PROFILE="
                f"{self._quote(resolved['PLAYER_PROFILE'])}"
            ),
        ]
        if resolved.get("IMAGE_DURATION") is not None:
            lines.append(
                "IMAGE_DURATION="
                f"{self._quote(str(resolved['IMAGE_DURATION']))}"
            )
        if resolved.get("ROTATION") is not None:
            lines.append(
                "ROTATION="
                f"{self._quote(str(resolved['ROTATION']))}"
            )

        return "\n".join(lines) + "\n"

    def write(
        self,
        configuration: dict[str, str],
    ) -> dict[str, str]:
        resolved = self.resolve(configuration)
        contents = self.render(resolved)

        self.config_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.config_path.with_name(
            f".{self.config_path.name}.tmp"
        )

        try:
            temporary_path.write_text(
                contents,
                encoding="utf-8",
            )

            temporary_path.chmod(0o600)

            os.replace(
                temporary_path,
                self.config_path,
            )

        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        return resolved
