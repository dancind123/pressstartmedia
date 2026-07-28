import secrets
from datetime import datetime, timezone
from pathlib import Path


class Identity:
    DEFAULT_PATH = Path(
        "/home/media/PressStart/config/identity.conf"
    )

    def __init__(self, identity_path=None):
        self.identity_path = Path(
            identity_path or self.DEFAULT_PATH
        )

    def exists(self) -> bool:
        return self.identity_path.is_file()

    def load(self) -> dict[str, str]:
        if not self.exists():
            raise RuntimeError(
                f"Identity file does not exist: "
                f"{self.identity_path}"
            )

        values = {}

        for raw_line in self.identity_path.read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        player_id = values.get("PLAYER_ID")
        created = values.get("CREATED")

        if not player_id:
            raise RuntimeError(
                "PLAYER_ID is missing from identity.conf"
            )

        if not created:
            raise RuntimeError(
                "CREATED is missing from identity.conf"
            )

        return values

    def create(self) -> dict[str, str]:
        if self.exists():
            raise RuntimeError(
                "Refusing to replace an existing identity file"
            )

        self.identity_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        identity = {
            "PLAYER_ID": self._generate_player_id(),
            "CREATED": self._utc_timestamp(),
        }

        contents = (
            f"PLAYER_ID={identity['PLAYER_ID']}\n"
            f"CREATED={identity['CREATED']}\n"
        )

        temporary_path = self.identity_path.with_suffix(
            ".conf.tmp"
        )

        temporary_path.write_text(
            contents,
            encoding="utf-8",
        )

        temporary_path.chmod(0o600)
        temporary_path.replace(self.identity_path)

        return identity

    def get_or_create(self) -> dict[str, str]:
        if self.exists():
            return self.load()

        return self.create()

    @staticmethod
    def _generate_player_id() -> str:
        random_part = secrets.token_hex(4)
        return f"psm-{random_part}"

    @staticmethod
    def _utc_timestamp() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
