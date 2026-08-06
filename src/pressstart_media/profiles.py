from copy import deepcopy


DEFAULT_PLAYLIST = "/home/media/PressStart/config/playlist.xspf"
MPV_PLAYLIST = "/home/media/PressStart/config/playlist.m3u"


PROFILES = {
    "game_horizontal": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/7 Game Videos/Horizontal",
        "PLAYLIST": DEFAULT_PLAYLIST,
        "PLAYBACK_ENGINE": "vlc",
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": False,
    },
    "game_vertical": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/7 Game Videos/Vertical",
        "PLAYLIST": DEFAULT_PLAYLIST,
        "PLAYBACK_ENGINE": "vlc",
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": False,
    },
    "cartoons": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/6 The TV Show",
        "PLAYLIST": DEFAULT_PLAYLIST,
        "PLAYBACK_ENGINE": "vlc",
        "AUDIO": True,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": False,
    },
    "outside_window": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/1 Outside Window Screen/New",
        "PLAYLIST": MPV_PLAYLIST,
        "PLAYBACK_ENGINE": "mpv",
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": True,
        "IMAGE_DURATION": 10,
        "ROTATION": 0,
    },
    "host_stand": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/2 Host Stand TV",
        "PLAYLIST": DEFAULT_PLAYLIST,
        "PLAYBACK_ENGINE": "vlc",
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": False,
    },
    "retro_dungeon": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/3 Retro Dungeon",
        "PLAYLIST": DEFAULT_PLAYLIST,
        "PLAYBACK_ENGINE": "vlc",
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": False,
    },
    "top_of_stairs": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/4 Top of the Stairs",
        "PLAYLIST": DEFAULT_PLAYLIST,
        "PLAYBACK_ENGINE": "vlc",
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": False,
    },
    "downstairs_bar": {
        "MEDIA_FOLDER": "/mnt/media/TV Signs/5 Downstairs Bar",
        "PLAYLIST": DEFAULT_PLAYLIST,
        "PLAYBACK_ENGINE": "vlc",
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
        "ALLOW_IMAGES": False,
    },
}


def get_profile(profile_name: str) -> dict:
    if profile_name not in PROFILES:
        supported = ", ".join(sorted(PROFILES))
        raise RuntimeError(
            f"Unsupported PLAYER_PROFILE: {profile_name}. "
            f"Supported profiles: {supported}"
        )
    return deepcopy(PROFILES[profile_name])
