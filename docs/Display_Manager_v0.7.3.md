Press Start Display Manager v0.7.3

Purpose

Press Start media players use a fixed 1920x1080 display environment even when a connected television advertises higher resolutions. Some 4K televisions renegotiate HDMI after a power cycle and select a 4K mode. Existing media windows can then occupy only part of the physical screen.

The display manager makes display geometry a platform responsibility rather than a VLC-, MPV-, or image-viewer-specific responsibility.

Display policy

The display manager:

dynamically discovers the enabled Wayland output instead of hard-coding an HDMI connector name;

prefers 1920x1080 at a 60 Hz-class refresh rate whenever the connected display advertises a suitable mode, including standard 60.00 Hz and 59.94 Hz modes;

preserves the current resolution when a suitable 1920x1080 60 Hz-class mode is unavailable;

reads ROTATION from the resolved player profile and applies 0, 90, 180, or 270 degrees;

uses normal/0-degree rotation before provisioning;

checks the output continuously so HDMI disconnect/reconnect or television power cycles cannot permanently change the required mode or transform;

runs independently of VLC, MPV, and swayimg.

Startup

Labwc starts the display manager from config/templates/labwc-autostart:

cd /home/media/PressStart/app
/usr/bin/python3 -m pressstart_media.display_manager

Only one display-manager process is permitted per user runtime session. A non-blocking lock in /run/user/<uid>/pressstart-display-manager.lock prevents duplicate instances.

Diagnostics

The manager writes a small rotating log to:

/home/media/PressStart/logs/display-manager.log

A one-shot diagnostic/application mode is available:

cd /home/media/PressStart/app
python3 -m pressstart_media.display_manager --once

Migration note

The Outside Window mixed player retains its existing startup-time rotation call during the initial rollout. That duplication is intentional and temporary. Once the platform display manager is validated on both landscape and rotated installations, the mixed-player-specific rotation implementation can be removed.