from copy import deepcopy


DEFAULT_PLAYLIST = "/home/media/PressStart/config/playlist.xspf"


PROFILES = {
    "game_horizontal": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "7 Game Videos/Horizontal"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
    },
    "game_vertical": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "7 Game Videos/Vertical"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
    },
    "cartoons": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "6 The TV Show"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": True,
        "SHUFFLE": True,
        "LOOP": True,
    },
    "outside_window": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "1 Outside Window Screen"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
    },
    "host_stand": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "2 Host Stand TV"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
    },
    "retro_dungeon": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "3 Retro Dungeon"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
    },
    "top_of_stairs": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "4 Top of the Stairs"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
    },
    "downstairs_bar": {
        "MEDIA_FOLDER": (
            "/mnt/media/TV Signs/"
            "5 Downstairs Bar"
        ),
        "PLAYLIST": DEFAULT_PLAYLIST,
        "AUDIO": False,
        "SHUFFLE": True,
        "LOOP": True,
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
