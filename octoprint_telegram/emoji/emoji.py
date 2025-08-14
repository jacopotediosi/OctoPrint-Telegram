from .unicode_emoji_dict import unicode_emoji_dict


class Emoji:
    # Official emoji CLDR short names can change over time, so to make sure the ones
    # we hardcode in the plugin sources don't break, we initialize the emoji map
    # with some custom ones.
    _custom_emoji_map = {
        # Octoprint specific
        "octo": "\U0001f419",
        "plugin": "\U0001f9e9",
        # Menu actions / outcomes
        "cancel": "\u274c",
        "check": "\u2705",
        "info": "\u2139\ufe0f",
        "question": "\u2753",
        "warning": "\u26a0\ufe0f",
        "attention": "\u2757",
        "notallowed": "\U0001f6ab",
        "rocket": "\U0001f680",
        "hooray": "\U0001f389",
        "shutdown": "\U0001f4a4",
        "settings": "\u2699\ufe0f",
        "star": "\u2b50",
        "lamp": "\U0001f4a1",
        # Menu navigation
        "back": "\u21a9\ufe0f",
        "up": "\u2b06\ufe0f",
        "right": "\u27a1\ufe0f",
        "down": "\u2b07\ufe0f",
        "left": "\u2b05\ufe0f",
        # File and folders
        "folder": "\U0001f4c2",
        "file": "\U0001f4c4",
        "name": "\U0001f3f7\ufe0f",
        "filesize": "\u2696\ufe0f",
        "search": "\U0001f50d",
        "upload": "\U0001f4e4",
        "download": "\U0001f4e5",
        "new": "\U0001f195",
        "edit": "\u270f\ufe0f",
        "save": "\U0001f4be",
        "cut": "\u2702\ufe0f",
        "copy": "\U0001f4cb",
        "delete": "\U0001f5d1\ufe0f",
        # Webcams and media
        "photo": "\U0001f4f8",
        "video": "\U0001f3a6",
        "movie": "\U0001f3ac",
        # Printer commands / statuses
        "home": "\U0001f3e0",
        "play": "\u25b6\ufe0f",
        "pause": "\u23f8\ufe0f",
        "resume": "\u23ef\ufe0f",
        "stop": "\u23f9\ufe0f",
        "online": "\U0001f7e2",
        "offline": "\U0001f534",
        # Printer settings
        "profile": "\U0001f464",
        "port": "\U0001f50c",
        "speed": "\u26a1",
        # 3D printing terms
        "tool": "\U0001f527",
        "hotbed": "\u2668\ufe0f",
        "cooldown": "\u2744\ufe0f",
        "flowrate": "\u23ec",
        "feedrate": "\u23e9",
        "filament": "\U0001f9f5",
        "height": "\u2195\ufe0f",
        "cost": "\U0001f4b0",
        # Notifications
        "notify": "\U0001f514",
        "nonotify": "\U0001f515",
        "emergency": "\U0001f6a8",
        # Time
        "calendar": "\U0001f4c5",
        "clock": "\U0001f552",
        "alarmclock": "\u23f0",
        "stopwatch": "\u23f1\ufe0f",
        "finish": "\U0001f3c1",
    }

    _emoji_map = _custom_emoji_map.copy()
    _emoji_map.update(unicode_emoji_dict)

    _settings = None

    @staticmethod
    def init(settings):
        Emoji._settings = settings

    @staticmethod
    def get_emoji(name: str) -> str:
        if not Emoji._settings or not Emoji._settings.get(["send_icon"]):
            return ""

        # Remove colon (dropped by muan/unicode-emoji-json) and make lookup case-insensitive
        normalized_name = name.replace(":", "").lower()

        return Emoji._emoji_map.get(normalized_name, "")

    @staticmethod
    def get_custom_emoji_map():
        return Emoji._custom_emoji_map
