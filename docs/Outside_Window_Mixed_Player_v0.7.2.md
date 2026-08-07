# Outside Window Mixed Player v0.7.2

## Changes

- Default Outside Window rotation is 270 degrees.
- Rotation remains configurable through the player configuration / Home Assistant.
- Still images are no longer shown with swayimg.
- Each still image is resized into a local cache with a maximum 1920x1920 bounding box before MPV displays it.
- Original image files on the Storage Server are never modified.
- Cached images are regenerated when the source file is newer than the cached copy.
- Videos continue to play directly from the Storage Server with MPV.
- Mixed-media sequencing remains one item at a time, completing the full generated playlist before looping.
