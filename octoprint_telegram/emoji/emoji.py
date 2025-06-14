from .unicode_emoji_dict import unicode_emoji_dict


class Emoji:
    # Official emoji CLDR short names can change over time, so to make sure the ones
    # we hardcode in the plugin sources don't break, we initialize the emoji map
    # with some custom ones.
    _custom_emoji_map = {
        "octo": "\U0001f419",
        "mistake": "\U0001f616",
        "notify": "\U0001f514",
        "shutdown": "\U0001f4a4",
        "shutup": "\U0001f64a",
        "noNotify": "\U0001f515",
        "notallowed": "\U0001f62c",
        "rocket": "\U0001f680",
        "save": "\U0001f4be",
        "heart": "\U00002764",
        "info": "\U00002139",
        "settings": "\U0001f4dd",
        "clock": "\U000023f0",
        "height": "\U00002b06",
        "question": "\U00002753",
        "warning": "\U000026a0",
        "enter": "\U0000270f",
        "upload": "\U0001f4e5",
        "check": "\U00002705",
        "lamp": "\U0001f4a1",
        "movie": "\U0001f3ac",
        "finish": "\U0001f3c1",
        "cam": "\U0001f3a6",
        "hooray": "\U0001f389",
        "error": "\U000026d4",
        "play": "\U000025b6",
        "stop": "\U000025fc",
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
