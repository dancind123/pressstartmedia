# Outside Window Mixed Player v0.7.1

## Purpose

This revision replaces MPV's mixed image/video playlist mode with a dedicated Press Start mixed-media worker for the `outside_window` profile.

## Playback Architecture

- Videos are played individually with MPV.
- Images are displayed individually with swayimg.
- The worker stays alive between items, so the Press Start manager does not treat normal item transitions as player exits.
- The generated M3U playlist defines the cycle order.
- Every item is visited once before the worker starts the cycle again.
- The playlist is shuffled once when generated; it is not randomly re-selected during playback.

## Outside Window Media Folder

`/mnt/media/TV Signs/1 Outside Window Screen`

The Outside Window profile scans only the base folder. Subfolders are intentionally ignored.

## Home Assistant

Existing controls remain supported:

- Refresh Playlist
- Image Duration
- Screen Rotation
- Current Media
- Restart Playback
- Restart Raspberry Pi

Refresh Playlist regenerates the M3U file from the current Storage Server folder contents and restarts the worker with the new sequence.

## Rotation

Rotation is applied at the Wayland output level using `wlr-randr`, so the selected 0/90/180/270 degree orientation applies consistently to both videos and images.

## Stability Rationale

MPV 0.40 on the Raspberry Pi Wayland stack played the source H.264 video correctly when used by itself, but long-running mixed image/video playlists produced colored blank frames and renderer stalls. Keeping MPV video-only and swayimg image-only avoids those renderer transitions.
