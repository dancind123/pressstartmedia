# Outside Window MPV Update

Version: 0.7.0

This update adds an MPV playback engine for the `outside_window` profile while preserving VLC for all existing profiles.

## Outside Window defaults

- Media folder: `/mnt/media/TV Signs/1 Outside Window Screen/New`
- Playback engine: MPV
- Playlist: `/home/media/PressStart/config/playlist.m3u`
- Images and videos supported
- Default image duration: 10 seconds
- Default rotation: 0 degrees
- Audio disabled
- Playlist shuffled once when generated, then played completely before looping

## Home Assistant controls

- Refresh Playlist
- Image Duration
- Screen Rotation
- Restart Raspberry Pi
- Current Media

Changing Image Duration or Screen Rotation writes the setting to `player.conf` and reloads the runtime configuration. Refresh Playlist rescans the Storage Server, regenerates the playlist, and restarts playback.

## Dependency

MPV is now included in `installer/install.sh`. Existing systems must have MPV installed before using the `outside_window` profile.
