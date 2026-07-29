# Build 1B — Zero-Touch Provisioning

## Objective

Allow a newly installed Press Start Media Raspberry Pi to start without `player.conf`, connect to MQTT, appear in Home Assistant as unprovisioned, accept a player name and profile, and transition directly into normal playback without manual editing.

## Startup Sequence

1. systemd launches `start-media.sh`.
2. `main.py` creates and connects `MediaAgent`.
3. The agent publishes availability, discovery, heartbeat, and provisioning state.
4. If `player.conf` exists, startup proceeds immediately.
5. If `player.conf` does not exist, `main.py` waits while the agent remains connected to MQTT.
6. A valid provisioning payload is validated and written atomically to `player.conf`.
7. The waiting startup path resumes.
8. `MediaManager` is constructed only after configuration exists.
9. The playlist is generated and VLC starts.

## Responsibilities

### `agent.py`

- Maintain persistent identity.
- Connect to MQTT.
- Publish discovery, availability, heartbeat, telemetry, and runtime state.
- Receive and validate provisioning payloads.
- Write `player.conf`.
- Report rejected or successful configuration.
- Provide `is_provisioned()` and `wait_for_provisioning()` to the entry point.

### `main.py`

- Coordinate startup.
- Connect the agent before constructing the playback manager.
- Wait for successful provisioning when necessary.
- Construct `MediaManager` only after configuration exists.
- Register runtime command handling.
- Disconnect the agent during shutdown.

### Playback engine

`manager.py`, `player.py`, `playlist.py`, and `display.py` receive no Build 1B changes.

### `install.sh`

- Install runtime dependencies and files.
- Install `media.conf` if missing.
- Do not create `player.conf`.
- Preserve an existing `player.conf` during upgrades.
- Enable, but do not start, the user service.

## Provisioning Behavior

Invalid configuration is rejected, reported through `config/state`, and leaves the application waiting for another attempt.

Valid configuration writes `player.conf`, republishes discovery and heartbeat, reports `provisioned`, releases the startup wait, and transitions directly into playback.

## Acceptance Criteria

- Application starts without `player.conf`.
- MQTT remains connected while waiting.
- Home Assistant reports the player as unprovisioned.
- Invalid profiles are rejected and the application continues waiting.
- Valid provisioning creates `player.conf`.
- `MediaManager` is never constructed before provisioning.
- Playlist generation and VLC startup begin after provisioning.
- Existing heartbeat, telemetry, Current Media, availability, and command entities remain functional.
- Existing provisioned players continue to start normally.
