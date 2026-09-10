# Press Start Display Manager v0.7.4

## Purpose

Press Start media players use a fixed 1920x1080 display environment even when a connected television advertises higher resolutions. Some 4K televisions renegotiate HDMI after a power cycle and select a 4K mode.

The display manager makes display geometry a platform responsibility rather than a VLC-, MPV-, or image-viewer-specific responsibility.

## Display policy

The display manager:

- dynamically discovers the enabled Wayland output instead of hard-coding an HDMI connector name;
- prefers 1920x1080 at a 60 Hz-class refresh rate whenever the connected display advertises a suitable mode, including standard 60.00 Hz and 59.94 Hz modes;
- preserves the current resolution when a suitable 1920x1080 60 Hz-class mode is unavailable;
- reads `ROTATION` from the resolved player profile and applies 0, 90, 180, or 270 degrees;
- uses normal/0-degree rotation before provisioning;
- checks the output continuously so HDMI disconnect/reconnect or television power cycles cannot permanently change the required mode or transform;
- runs independently of VLC, MPV, and `swayimg`.

## Media refresh after geometry changes

A live Wayland mode or transform change can leave an already-running media surface sized for the output geometry that existed before the change. This was observed on Retro Dungeon: the display manager correctly changed the television from 4K to 1920x1080, but VLC remained sized for the earlier 4K output and appeared cropped.

After the display manager actually changes the output mode or transform, it runs:

```text
systemctl --user try-restart pressstart-media.service
```

`try-restart` refreshes the media player only when the service is already active. It does not start a deliberately stopped service. Once the media service restarts, VLC, MPV, or the image viewer creates its surface against the corrected output geometry.

No restart occurs during normal two-second polling when the display is already configured correctly.

## Startup

Labwc starts the display manager from `config/templates/labwc-autostart`:

```text
cd /home/media/PressStart/app
/usr/bin/python3 -m pressstart_media.display_manager
```

Only one display-manager process is permitted per user runtime session. A non-blocking lock in `/run/user/<uid>/pressstart-display-manager.lock` prevents duplicate instances.

## Diagnostics

The manager writes a small rotating log to:

```text
/home/media/PressStart/logs/display-manager.log
```

A one-shot diagnostic/application mode is available:

```text
cd /home/media/PressStart/app
python3 -m pressstart_media.display_manager --once
```

## Migration note

The Outside Window mixed player retains its existing startup-time rotation call during the initial rollout. That duplication remains intentional and temporary. Once the platform display manager is validated on both landscape and rotated installations, the mixed-player-specific rotation implementation can be removed.
