import json
import shutil
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path

from pressstart_media.identity import Identity
from pressstart_media.mqtt_client import MQTTClient
from pressstart_media.provisioning import (
    ProvisioningConfig,
    ProvisioningError,
)
from pressstart_media.version import VERSION


class MediaAgent:
    DISCOVERY_TOPIC = "pressstart/media/discovery"
    TOPIC_ROOT = "pressstart/media"

    HOME_ASSISTANT_DISCOVERY_PREFIX = "homeassistant"

    DEFAULT_HEARTBEAT_INTERVAL = 30

    def __init__(
        self,
        provisioning_path=None,
        heartbeat_interval=None,
    ):
        self.identity = Identity().get_or_create()
        self.player_id = self.identity["PLAYER_ID"]

        self.mqtt = MQTTClient(
            client_id=f"{self.player_id}-agent"
        )

        self.provisioning = ProvisioningConfig(
            config_path=provisioning_path
        )

        self.heartbeat_interval = (
            heartbeat_interval
            if heartbeat_interval is not None
            else self.DEFAULT_HEARTBEAT_INTERVAL
        )

        if self.heartbeat_interval <= 0:
            raise ValueError(
                "heartbeat_interval must be greater than zero"
            )

        self.configuration_received = threading.Event()
        self.last_configuration = None
        self.last_error = None

        self.command_handler = None

        self._heartbeat_stop_event = threading.Event()
        self._heartbeat_thread = None

        self._previous_cpu_total = None
        self._previous_cpu_idle = None

        self._current_media = None

    @staticmethod
    def _utc_timestamp() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _system_uptime_seconds() -> int | None:
        uptime_path = Path("/proc/uptime")

        try:
            raw_value = uptime_path.read_text(
                encoding="utf-8"
            ).split()[0]

            return int(float(raw_value))

        except (
            OSError,
            ValueError,
            IndexError,
        ):
            return None

    @staticmethod
    def _read_simple_config(path: Path) -> dict[str, str]:
        values = {}

        try:
            lines = path.read_text(
                encoding="utf-8"
            ).splitlines()

        except OSError:
            return values

        for line in lines:
            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "=" not in stripped
            ):
                continue

            key, value = stripped.split("=", 1)

            key = key.strip()
            value = value.strip()

            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]

            values[key] = value

        return values

    def _player_configuration(self) -> dict[str, str]:
        return self._read_simple_config(
            self.provisioning.config_path
        )

    def _player_name(self) -> str:
        player_config = self._player_configuration()

        return (
            player_config.get("PLAYER_NAME")
            or socket.gethostname()
            or self.player_id
        )

    @staticmethod
    def _primary_ip_address() -> str | None:
        network_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        try:
            network_socket.connect(
                ("10.0.5.40", 8123)
            )

            return network_socket.getsockname()[0]

        except OSError:
            return None

        finally:
            network_socket.close()

    @staticmethod
    def _cpu_temperature_c() -> float | None:
        possible_paths = (
            Path(
                "/sys/class/thermal/"
                "thermal_zone0/temp"
            ),
            Path(
                "/sys/class/hwmon/"
                "hwmon0/temp1_input"
            ),
        )

        for temperature_path in possible_paths:
            try:
                raw_value = float(
                    temperature_path.read_text(
                        encoding="utf-8"
                    ).strip()
                )

                if raw_value > 1000:
                    raw_value /= 1000

                return round(raw_value, 1)

            except (
                OSError,
                ValueError,
            ):
                continue

        return None

    @staticmethod
    def _read_cpu_times() -> tuple[int, int] | None:
        stat_path = Path("/proc/stat")

        try:
            first_line = stat_path.read_text(
                encoding="utf-8"
            ).splitlines()[0]

            fields = first_line.split()

            if not fields or fields[0] != "cpu":
                return None

            values = [
                int(value)
                for value in fields[1:]
            ]

            if len(values) < 4:
                return None

            idle = values[3]

            if len(values) > 4:
                idle += values[4]

            total = sum(values)

            return total, idle

        except (
            OSError,
            ValueError,
            IndexError,
        ):
            return None

    def _cpu_usage_percent(self) -> float | None:
        current = self._read_cpu_times()

        if current is None:
            return None

        current_total, current_idle = current

        if (
            self._previous_cpu_total is None
            or self._previous_cpu_idle is None
        ):
            self._previous_cpu_total = current_total
            self._previous_cpu_idle = current_idle
            return None

        total_delta = (
            current_total
            - self._previous_cpu_total
        )

        idle_delta = (
            current_idle
            - self._previous_cpu_idle
        )

        self._previous_cpu_total = current_total
        self._previous_cpu_idle = current_idle

        if total_delta <= 0:
            return None

        usage = (
            100.0
            * (total_delta - idle_delta)
            / total_delta
        )

        return round(
            max(0.0, min(usage, 100.0)),
            1,
        )

    @staticmethod
    def _memory_usage_percent() -> float | None:
        memory_path = Path("/proc/meminfo")
        memory_values = {}

        try:
            for line in memory_path.read_text(
                encoding="utf-8"
            ).splitlines():
                if ":" not in line:
                    continue

                key, raw_value = line.split(":", 1)
                parts = raw_value.strip().split()

                if not parts:
                    continue

                memory_values[key] = int(parts[0])

            total = memory_values.get("MemTotal")
            available = memory_values.get(
                "MemAvailable"
            )

            if (
                total is None
                or available is None
                or total <= 0
            ):
                return None

            used = total - available

            return round(
                100.0 * used / total,
                1,
            )

        except (
            OSError,
            ValueError,
        ):
            return None

    @staticmethod
    def _disk_free_gb() -> float | None:
        try:
            usage = shutil.disk_usage("/")

            return round(
                usage.free
                / (1024 ** 3),
                1,
            )

        except OSError:
            return None

    def _topic(self, suffix: str) -> str:
        return (
            f"{self.TOPIC_ROOT}/"
            f"{self.player_id}/"
            f"{suffix}"
        )

    def _home_assistant_discovery_topic(
        self,
        component: str,
        object_id: str,
    ) -> str:
        return (
            f"{self.HOME_ASSISTANT_DISCOVERY_PREFIX}/"
            f"{component}/"
            f"{self.player_id}/"
            f"{object_id}/config"
        )

    def _home_assistant_device(self) -> dict:
        return {
            "identifiers": [
                f"pressstart_media_{self.player_id}"
            ],
            "name": self._player_name(),
            "manufacturer": "Press Start",
            "model": "Press Start Media Player",
            "sw_version": VERSION,
            "serial_number": self.player_id,
        }

    @staticmethod
    def _home_assistant_origin() -> dict:
        return {
            "name": "Press Start Media",
            "sw_version": VERSION,
        }

    def _home_assistant_availability(self) -> dict:
        return {
            "availability_topic": self._topic(
                "availability"
            ),
            "payload_available": "online",
            "payload_not_available": "offline",
        }

    def _home_assistant_common_config(
        self,
        object_id: str,
        name: str,
        use_availability: bool = True,
    ) -> dict:
        config = {
            "name": name,
            "unique_id": (
                f"pressstart_media_"
                f"{self.player_id}_"
                f"{object_id}"
            ),
            "device": self._home_assistant_device(),
            "origin": self._home_assistant_origin(),
        }

        if use_availability:
            config.update(
                self._home_assistant_availability()
            )

        return config

    def _publish_home_assistant_config(
        self,
        component: str,
        object_id: str,
        config: dict,
    ) -> None:
        self.mqtt.publish(
            topic=self._home_assistant_discovery_topic(
                component,
                object_id,
            ),
            payload=config,
            qos=1,
            retain=True,
        )

    def publish_home_assistant_discovery(self) -> None:
        heartbeat_topic = self._topic("heartbeat")
        availability_topic = self._topic(
            "availability"
        )

        status_config = (
            self._home_assistant_common_config(
                object_id="status",
                name="Status",
                use_availability=False,
            )
        )
        status_config.update(
            {
                "state_topic": availability_topic,
                "payload_on": "online",
                "payload_off": "offline",
                "device_class": "connectivity",
                "icon": "mdi:television-play",
            }
        )

        self._publish_home_assistant_config(
            component="binary_sensor",
            object_id="status",
            config=status_config,
        )

        provisioned_config = (
            self._home_assistant_common_config(
                object_id="provisioned",
                name="Provisioned",
            )
        )
        provisioned_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ 'ON' if "
                    "value_json.provisioned "
                    "| default(false) "
                    "else 'OFF' }}"
                ),
                "payload_on": "ON",
                "payload_off": "OFF",
                "icon": "mdi:check-decagram",
            }
        )

        self._publish_home_assistant_config(
            component="binary_sensor",
            object_id="provisioned",
            config=provisioned_config,
        )

        heartbeat_config = (
            self._home_assistant_common_config(
                object_id="heartbeat",
                name="Heartbeat",
            )
        )
        heartbeat_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.state }}"
                ),
                "json_attributes_topic": (
                    heartbeat_topic
                ),
                "icon": "mdi:heart-pulse",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="heartbeat",
            config=heartbeat_config,
        )

        last_heartbeat_config = (
            self._home_assistant_common_config(
                object_id="last_heartbeat",
                name="Last Heartbeat",
            )
        )
        last_heartbeat_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.timestamp }}"
                ),
                "device_class": "timestamp",
                "icon": "mdi:clock-check-outline",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="last_heartbeat",
            config=last_heartbeat_config,
        )

        cpu_temperature_config = (
            self._home_assistant_common_config(
                object_id="cpu_temperature",
                name="CPU Temperature",
            )
        )
        cpu_temperature_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.cpu_temperature_c }}"
                ),
                "unit_of_measurement": "°C",
                "device_class": "temperature",
                "state_class": "measurement",
                "icon": "mdi:thermometer",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="cpu_temperature",
            config=cpu_temperature_config,
        )

        cpu_usage_config = (
            self._home_assistant_common_config(
                object_id="cpu_usage",
                name="CPU Usage",
            )
        )
        cpu_usage_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.cpu_usage_percent }}"
                ),
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:cpu-64-bit",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="cpu_usage",
            config=cpu_usage_config,
        )

        memory_usage_config = (
            self._home_assistant_common_config(
                object_id="memory_usage",
                name="Memory Usage",
            )
        )
        memory_usage_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.memory_usage_percent }}"
                ),
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:memory",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="memory_usage",
            config=memory_usage_config,
        )

        disk_free_config = (
            self._home_assistant_common_config(
                object_id="disk_free",
                name="Disk Free",
            )
        )
        disk_free_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.disk_free_gb }}"
                ),
                "unit_of_measurement": "GB",
                "state_class": "measurement",
                "icon": "mdi:harddisk",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="disk_free",
            config=disk_free_config,
        )

        uptime_config = (
            self._home_assistant_common_config(
                object_id="uptime",
                name="Uptime",
            )
        )
        uptime_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.uptime_seconds }}"
                ),
                "unit_of_measurement": "s",
                "device_class": "duration",
                "state_class": "total_increasing",
                "icon": "mdi:timer-outline",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="uptime",
            config=uptime_config,
        )

        ip_address_config = (
            self._home_assistant_common_config(
                object_id="ip_address",
                name="IP Address",
            )
        )
        ip_address_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.ip_address }}"
                ),
                "icon": "mdi:ip-network",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="ip_address",
            config=ip_address_config,
        )

        software_version_config = (
            self._home_assistant_common_config(
                object_id="software_version",
                name="Software Version",
            )
        )
        software_version_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.version }}"
                ),
                "icon": "mdi:source-branch",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="software_version",
            config=software_version_config,
        )

        player_profile_config = (
            self._home_assistant_common_config(
                object_id="player_profile",
                name="Player Profile",
            )
        )
        player_profile_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.player_profile }}"
                ),
                "icon": "mdi:playlist-play",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="player_profile",
            config=player_profile_config,
        )

        hostname_config = (
            self._home_assistant_common_config(
                object_id="hostname",
                name="Hostname",
            )
        )
        hostname_config.update(
            {
                "state_topic": heartbeat_topic,
                "value_template": (
                    "{{ value_json.hostname }}"
                ),
                "icon": "mdi:raspberry-pi",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="hostname",
            config=hostname_config,
        )

        runtime_state_topic = self._topic("state")

        current_media_config = (
            self._home_assistant_common_config(
                object_id="current_media",
                name="Current Media",
            )
        )
        current_media_config.update(
            {
                "state_topic": runtime_state_topic,
                "value_template": (
                    "{{ value_json.current_media "
                    "| default('Unknown', true) }}"
                ),
                "icon": "mdi:movie-open-play",
            }
        )

        self._publish_home_assistant_config(
            component="sensor",
            object_id="current_media",
            config=current_media_config,
        )

        refresh_config = (
            self._home_assistant_common_config(
                object_id="refresh_playlist",
                name="Refresh Playlist",
            )
        )
        refresh_config.update(
            {
                "command_topic": self._topic("command"),
                "payload_press": "reload_playlist",
                "icon": "mdi:playlist-refresh",
            }
        )
        self._publish_home_assistant_config(
            component="button",
            object_id="refresh_playlist",
            config=refresh_config,
        )

        player_config = self._player_configuration()
        if player_config.get("PLAYER_PROFILE") == "outside_window":
            image_duration_config = (
                self._home_assistant_common_config(
                    object_id="image_duration",
                    name="Image Duration",
                )
            )
            image_duration_config.update(
                {
                    "command_topic": self._topic("settings/set"),
                    "command_template": (
                        '{"image_duration": {{ value | int }}}'
                    ),
                    "state_topic": heartbeat_topic,
                    "value_template": (
                        "{{ value_json.image_duration | default(10) }}"
                    ),
                    "min": 1,
                    "max": 300,
                    "step": 1,
                    "unit_of_measurement": "s",
                    "mode": "box",
                    "icon": "mdi:timer-outline",
                    "entity_category": "config",
                }
            )
            self._publish_home_assistant_config(
                component="number",
                object_id="image_duration",
                config=image_duration_config,
            )

            rotation_config = (
                self._home_assistant_common_config(
                    object_id="rotation",
                    name="Screen Rotation",
                )
            )
            rotation_config.update(
                {
                    "command_topic": self._topic("settings/set"),
                    "command_template": (
                        '{"rotation": "{{ value }}"}'
                    ),
                    "state_topic": heartbeat_topic,
                    "value_template": (
                        "{{ value_json.rotation | default('0') | string }}"
                    ),
                    "options": ["0", "90", "180", "270"],
                    "icon": "mdi:screen-rotation",
                    "entity_category": "config",
                }
            )
            self._publish_home_assistant_config(
                component="select",
                object_id="rotation",
                config=rotation_config,
            )

        reboot_config = (
            self._home_assistant_common_config(
                object_id="reboot",
                name="Restart Raspberry Pi",
            )
        )
        reboot_config.update(
            {
                "command_topic": self._topic("command"),
                "payload_press": "reboot",
                "icon": "mdi:restart",
                "entity_category": "config",
            }
        )

        self._publish_home_assistant_config(
            component="button",
            object_id="reboot",
            config=reboot_config,
        )

    def build_discovery_payload(self) -> dict:
        player_config = self._player_configuration()

        return {
            "player_id": self.player_id,
            "player_name": player_config.get(
                "PLAYER_NAME"
            ),
            "player_profile": player_config.get(
                "PLAYER_PROFILE"
            ),
            "hostname": socket.gethostname(),
            "ip_address": self._primary_ip_address(),
            "platform": "press_start_media",
            "version": VERSION,
            "state": "announcing",
            "provisioned": (
                self.provisioning.config_path.is_file()
            ),
            "created": self.identity["CREATED"],
            "timestamp": self._utc_timestamp(),
        }

    def build_heartbeat_payload(self) -> dict:
        player_config = self._player_configuration()

        return {
            "player_id": self.player_id,
            "player_name": player_config.get(
                "PLAYER_NAME"
            ),
            "player_profile": player_config.get(
                "PLAYER_PROFILE"
            ),
            "image_duration": int(
                player_config.get("IMAGE_DURATION", "10")
            ),
            "rotation": str(
                player_config.get("ROTATION", "0")
            ),
            "hostname": socket.gethostname(),
            "ip_address": self._primary_ip_address(),
            "version": VERSION,
            "state": "online",
            "provisioned": (
                self.provisioning.config_path.is_file()
            ),
            "uptime_seconds": (
                self._system_uptime_seconds()
            ),
            "cpu_temperature_c": (
                self._cpu_temperature_c()
            ),
            "cpu_usage_percent": (
                self._cpu_usage_percent()
            ),
            "memory_usage_percent": (
                self._memory_usage_percent()
            ),
            "disk_free_gb": (
                self._disk_free_gb()
            ),
            "timestamp": self._utc_timestamp(),
        }

    def publish_discovery(self) -> None:
        self.mqtt.publish(
            topic=self.DISCOVERY_TOPIC,
            payload=self.build_discovery_payload(),
            qos=1,
            retain=False,
        )

        self.publish_home_assistant_discovery()

    def publish_availability(self, state: str) -> None:
        if state not in {"online", "offline"}:
            raise ValueError(
                "Availability must be 'online' or 'offline'"
            )

        self.mqtt.publish(
            topic=self._topic("availability"),
            payload=state,
            qos=1,
            retain=True,
        )

    def publish_heartbeat(self) -> None:
        self.mqtt.publish(
            topic=self._topic("heartbeat"),
            payload=self.build_heartbeat_payload(),
            qos=1,
            retain=False,
        )

    def publish_runtime_state(
        self,
        state: str,
        details: dict | None = None,
    ) -> None:
        payload = {
            "player_id": self.player_id,
            "hostname": socket.gethostname(),
            "version": VERSION,
            "state": state,
            "timestamp": self._utc_timestamp(),
        }

        if details:
            payload.update(details)

            current_media = details.get("current_media")

            if current_media:
                self._current_media = str(current_media)

        if self._current_media:
            payload["current_media"] = self._current_media

        self.mqtt.publish(
            topic=self._topic("state"),
            payload=payload,
            qos=1,
            retain=True,
        )

    def publish_config_state(
        self,
        state: str,
        details: dict | None = None,
    ) -> None:
        payload = {
            "player_id": self.player_id,
            "state": state,
            "timestamp": self._utc_timestamp(),
        }

        if details:
            payload.update(details)

        self.mqtt.publish(
            topic=self._topic("config/state"),
            payload=payload,
            qos=1,
            retain=True,
        )

    def set_command_handler(
        self,
        handler,
    ) -> None:
        if handler is not None and not callable(handler):
            raise TypeError(
                "Command handler must be callable"
            )

        self.command_handler = handler

    def _handle_command(
        self,
        topic: str,
        payload: bytes,
    ) -> None:
        try:
            command_text = payload.decode(
                "utf-8"
            ).strip()

        except UnicodeDecodeError as error:
            self.publish_runtime_state(
                state="COMMAND_REJECTED",
                details={
                    "error": (
                        "Command payload was not valid UTF-8"
                    ),
                },
            )
            return

        if not command_text:
            self.publish_runtime_state(
                state="COMMAND_REJECTED",
                details={
                    "error": "Command payload was empty",
                },
            )
            return

        if self.command_handler is None:
            self.publish_runtime_state(
                state="COMMAND_REJECTED",
                details={
                    "command": command_text,
                    "error": (
                        "No command handler is registered"
                    ),
                },
            )
            return

        try:
            self.command_handler(
                command_text
            )

            self.publish_runtime_state(
                state="COMMAND_RECEIVED",
                details={
                    "command": command_text,
                },
            )

        except Exception as error:
            self.publish_runtime_state(
                state="COMMAND_ERROR",
                details={
                    "command": command_text,
                    "error": str(error),
                },
            )

    def _handle_configuration(
        self,
        topic: str,
        payload: bytes,
    ) -> None:
        try:
            validated = self.provisioning.parse_payload(
                payload
            )

            resolved = self.provisioning.write(
                validated
            )

            self.last_configuration = resolved
            self.last_error = None

            self.publish_discovery()
            self.publish_heartbeat()

            self.publish_config_state(
                state="provisioned",
                details={
                    "player_name": validated["player_name"],
                    "player_profile": validated[
                        "player_profile"
                    ],
                    "restart_required": True,
                },
            )

        except ProvisioningError as error:
            self.last_configuration = None
            self.last_error = str(error)

            self.publish_config_state(
                state="rejected",
                details={
                    "error": str(error),
                },
            )

        except Exception as error:
            self.last_configuration = None
            self.last_error = str(error)

            try:
                self.publish_config_state(
                    state="error",
                    details={
                        "error": str(error),
                    },
                )
            except Exception as publish_error:
                print(
                    "Unable to publish provisioning error: "
                    f"{publish_error}"
                )

        finally:
            self.configuration_received.set()

    def _handle_settings(
        self,
        topic: str,
        payload: bytes,
    ) -> None:
        try:
            updates = json.loads(payload.decode("utf-8"))
            if not isinstance(updates, dict):
                raise ProvisioningError(
                    "Settings payload must be a JSON object"
                )

            current = self._player_configuration()
            configuration = {
                "player_name": current.get(
                    "PLAYER_NAME",
                    self._player_name(),
                ),
                "player_profile": current.get(
                    "PLAYER_PROFILE",
                ),
            }
            if current.get("IMAGE_DURATION") is not None:
                configuration["image_duration"] = current[
                    "IMAGE_DURATION"
                ]
            if current.get("ROTATION") is not None:
                configuration["rotation"] = current["ROTATION"]

            allowed = {"image_duration", "rotation"}
            unknown = set(updates) - allowed
            if unknown:
                raise ProvisioningError(
                    "Unknown settings field(s): "
                    + ", ".join(sorted(unknown))
                )
            configuration.update(updates)
            resolved = self.provisioning.write(configuration)
            self.last_configuration = resolved
            self.last_error = None
            self.publish_heartbeat()
            self.publish_config_state(
                state="settings_applied",
                details={
                    "image_duration": resolved.get(
                        "IMAGE_DURATION"
                    ),
                    "rotation": resolved.get("ROTATION"),
                },
            )
            if self.command_handler is not None:
                self.command_handler("reload_configuration")

        except (UnicodeDecodeError, json.JSONDecodeError, ProvisioningError) as error:
            self.last_error = str(error)
            self.publish_config_state(
                state="rejected",
                details={"error": str(error)},
            )
        except Exception as error:
            self.last_error = str(error)
            self.publish_config_state(
                state="error",
                details={"error": str(error)},
            )

    def is_provisioned(self) -> bool:
        return self.provisioning.config_path.is_file()

    def wait_for_provisioning(self) -> None:
        while not self.is_provisioned():
            self.configuration_received.wait()
            self.configuration_received.clear()

    def connect_for_provisioning(self) -> None:
        config_topic = self._topic("config/set")
        command_topic = self._topic("command")
        settings_topic = self._topic("settings/set")

        self.mqtt.subscribe(
            topic=config_topic,
            handler=self._handle_configuration,
            qos=1,
        )

        self.mqtt.subscribe(
            topic=command_topic,
            handler=self._handle_command,
            qos=1,
        )

        self.mqtt.subscribe(
            topic=settings_topic,
            handler=self._handle_settings,
            qos=1,
        )

        self.mqtt.connect()

        self.mqtt.wait_for_subscription(
            config_topic,
            timeout=10,
        )

        self.mqtt.wait_for_subscription(
            command_topic,
            timeout=10,
        )

        self.mqtt.wait_for_subscription(
            settings_topic,
            timeout=10,
        )

        self.publish_availability("online")
        self.publish_discovery()

        if self.provisioning.config_path.is_file():
            self.publish_config_state(
                state="provisioned",
                details={
                    "restart_required": False,
                },
            )
        else:
            self.publish_config_state(
                state="waiting_for_configuration"
            )

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop_event.is_set():
            try:
                self.publish_heartbeat()

            except Exception as error:
                print(
                    f"Heartbeat publish failed: {error}"
                )

            self._heartbeat_stop_event.wait(
                self.heartbeat_interval
            )

    def start_heartbeat(self) -> None:
        if (
            self._heartbeat_thread is not None
            and self._heartbeat_thread.is_alive()
        ):
            return

        if not self.mqtt.is_connected():
            raise RuntimeError(
                "Cannot start heartbeat because MQTT "
                "is not connected"
            )

        self._heartbeat_stop_event.clear()

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"heartbeat-{self.player_id}",
        )

        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop_event.set()

        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(
                timeout=self.heartbeat_interval + 2
            )

        self._heartbeat_thread = None

    def connect(self) -> None:
        self.connect_for_provisioning()
        self.start_heartbeat()

    def disconnect(self) -> None:
        self.stop_heartbeat()

        try:
            if self.mqtt.is_connected():
                self.publish_availability("offline")
        except Exception as error:
            print(
                f"Unable to publish offline state: {error}"
            )
        finally:
            self.mqtt.disconnect()

    def run_diagnostic(self) -> None:
        try:
            self.mqtt.connect()
            self.publish_availability("online")
            self.publish_discovery()
            self.publish_heartbeat()

        finally:
            self.mqtt.disconnect()
