import json
import threading
from pathlib import Path
from typing import Any, Callable

import paho.mqtt.client as mqtt


MessageHandler = Callable[[str, bytes], None]


class MQTTClient:
    DEFAULT_BROKER = "10.0.5.40"
    DEFAULT_PORT = 1883
    DEFAULT_KEEPALIVE = 60

    DEFAULT_CREDENTIALS_PATH = Path(
        "/home/media/PressStart/config/mqtt-credentials"
    )

    def __init__(
        self,
        client_id: str,
        broker: str = DEFAULT_BROKER,
        port: int = DEFAULT_PORT,
        keepalive: int = DEFAULT_KEEPALIVE,
        credentials_path=None,
    ):
        if not client_id:
            raise ValueError("MQTT client_id cannot be empty")

        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.keepalive = keepalive

        self.credentials_path = Path(
            credentials_path or self.DEFAULT_CREDENTIALS_PATH
        )

        self._connected_event = threading.Event()
        self._connection_error = None

        self._message_handlers: dict[str, MessageHandler] = {}
        self._handler_lock = threading.Lock()

        self._subscription_events: dict[str, threading.Event] = {}
        self._subscription_message_ids: dict[int, str] = {}
        self._subscription_lock = threading.Lock()

        credentials = self._load_credentials()

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            protocol=mqtt.MQTTv311,
        )

        self.client.username_pw_set(
            credentials["USERNAME"],
            credentials["PASSWORD"],
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe

    def _load_credentials(self) -> dict[str, str]:
        if not self.credentials_path.is_file():
            raise RuntimeError(
                f"MQTT credentials file does not exist: "
                f"{self.credentials_path}"
            )

        credentials = {}

        for raw_line in self.credentials_path.read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            credentials[key.strip()] = value.strip()

        username = credentials.get("USERNAME")
        password = credentials.get("PASSWORD")

        if not username:
            raise RuntimeError(
                "USERNAME is missing from MQTT credentials"
            )

        if not password:
            raise RuntimeError(
                "PASSWORD is missing from MQTT credentials"
            )

        return credentials

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        if reason_code.is_failure:
            self._connection_error = RuntimeError(
                f"MQTT connection rejected: {reason_code}"
            )
            self._connected_event.set()
            return

        self._connection_error = None
        self._connected_event.set()

        with self._handler_lock:
            topics = list(self._message_handlers)

        for topic in topics:
            self._request_subscription(
                topic=topic,
                qos=1,
            )

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):
        self._connected_event.clear()

        with self._subscription_lock:
            for event in self._subscription_events.values():
                event.clear()

            self._subscription_message_ids.clear()

    def _on_subscribe(
        self,
        client,
        userdata,
        message_id,
        reason_codes,
        properties,
    ):
        with self._subscription_lock:
            topic = self._subscription_message_ids.pop(
                message_id,
                None,
            )

            if topic is None:
                return

            event = self._subscription_events.get(topic)

        if event is not None:
            event.set()

    def _on_message(
        self,
        client,
        userdata,
        message,
    ):
        with self._handler_lock:
            handlers = list(
                self._message_handlers.items()
            )

        for topic_filter, handler in handlers:
            if not mqtt.topic_matches_sub(
                topic_filter,
                message.topic,
            ):
                continue

            worker = threading.Thread(
                target=self._run_message_handler,
                args=(
                    handler,
                    message.topic,
                    bytes(message.payload),
                ),
                daemon=True,
                name=(
                    f"mqtt-handler-"
                    f"{self.client_id}"
                ),
            )

            worker.start()

    @staticmethod
    def _run_message_handler(
        handler: MessageHandler,
        topic: str,
        payload: bytes,
    ) -> None:
        try:
            handler(topic, payload)
        except Exception as error:
            print(
                f"MQTT message handler failed for "
                f"{topic}: {error}"
            )

    def _request_subscription(
        self,
        topic: str,
        qos: int,
    ) -> None:
        result, message_id = self.client.subscribe(
            topic,
            qos=qos,
        )

        if result != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"MQTT subscription failed with "
                f"result code {result}"
            )

        with self._subscription_lock:
            self._subscription_message_ids[
                message_id
            ] = topic

    def connect(self, timeout: float = 10.0) -> None:
        self._connected_event.clear()
        self._connection_error = None

        self.client.connect(
            self.broker,
            self.port,
            self.keepalive,
        )

        self.client.loop_start()

        if not self._connected_event.wait(timeout):
            self.client.loop_stop()

            raise TimeoutError(
                f"Timed out connecting to MQTT broker "
                f"{self.broker}:{self.port}"
            )

        if self._connection_error:
            self.client.loop_stop()
            raise self._connection_error

    def is_connected(self) -> bool:
        return self.client.is_connected()

    def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        qos: int = 1,
    ) -> None:
        if not topic:
            raise ValueError(
                "MQTT subscription topic cannot be empty"
            )

        if not callable(handler):
            raise TypeError(
                "MQTT message handler must be callable"
            )

        with self._handler_lock:
            self._message_handlers[topic] = handler

        with self._subscription_lock:
            event = self._subscription_events.get(topic)

            if event is None:
                event = threading.Event()
                self._subscription_events[topic] = event

            event.clear()

        if self.is_connected():
            self._request_subscription(
                topic=topic,
                qos=qos,
            )

    def wait_for_subscription(
        self,
        topic: str,
        timeout: float = 10.0,
    ) -> None:
        with self._subscription_lock:
            event = self._subscription_events.get(topic)

        if event is None:
            raise RuntimeError(
                f"No MQTT subscription is registered "
                f"for topic: {topic}"
            )

        if not event.wait(timeout):
            raise TimeoutError(
                f"Timed out waiting for MQTT subscription "
                f"acknowledgment: {topic}"
            )

    def unsubscribe(self, topic: str) -> None:
        with self._handler_lock:
            self._message_handlers.pop(topic, None)

        with self._subscription_lock:
            self._subscription_events.pop(
                topic,
                None,
            )

        if self.is_connected():
            result, _message_id = self.client.unsubscribe(
                topic
            )

            if result != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(
                    f"MQTT unsubscribe failed with "
                    f"result code {result}"
                )

    def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 1,
        retain: bool = False,
        timeout: float = 10.0,
    ) -> None:
        if not self.is_connected():
            raise RuntimeError(
                "Cannot publish because MQTT is not connected"
            )

        if isinstance(payload, (dict, list)):
            encoded_payload = json.dumps(
                payload,
                separators=(",", ":"),
            )
        elif isinstance(payload, bool):
            encoded_payload = (
                "true" if payload else "false"
            )
        elif payload is None:
            encoded_payload = ""
        else:
            encoded_payload = str(payload)

        publish_result = self.client.publish(
            topic,
            encoded_payload,
            qos=qos,
            retain=retain,
        )

        if publish_result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"MQTT publish failed with result code "
                f"{publish_result.rc}"
            )

        publish_result.wait_for_publish(
            timeout=timeout
        )

        if not publish_result.is_published():
            raise TimeoutError(
                f"Timed out publishing MQTT message "
                f"to {topic}"
            )

    def disconnect(self) -> None:
        try:
            if self.client.is_connected():
                self.client.disconnect()
        finally:
            self.client.loop_stop()
            self._connected_event.clear()
