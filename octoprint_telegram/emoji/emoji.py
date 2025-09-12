import re

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
        "loading": "\u23f3",
        "view": "\U0001f441\ufe0f",
        "pointer": "\U0001f449",
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

    _EMOJI_PATTERN = re.compile(r"\{emo:([^\}]+)\}")
    _EMOJI_GROUP_PATTERN = re.compile(r"(\{emo:[^\}]+\}(?:\s*\{emo:[^\}]+\})*)")

    @staticmethod
    def init(settings):
        Emoji._settings = settings

    @staticmethod
    def get_emoji(name: str) -> str:
        """
        Return the emoji for the given name (case-insensitive).
        Returns "" if not found.
        """
        # Remove colon (dropped by muan/unicode-emoji-json) and make lookup case-insensitive
        normalized_name = name.replace(":", "").lower()

        return Emoji._emoji_map.get(normalized_name, "")

    @staticmethod
    def render_emojis(text: str) -> str:
        """
        Replace `{emo:name}` placeholders with emojis or remove them if emojis are disabled in plugin settings.

        Behavior:

        When emojis are active:
        - Each `{emo:name}` is replaced by the corresponding emoji.
        - Consecutive placeholders are replaced independently.

        When emojis are disabled:
        - Consecutive placeholders (with optional spaces in between) are treated
        as a single "emoji group" and removed together.
        - Spaces immediately adjacent to the group are normalized:
            - If both sides had a space -> replaced by a single space.
            - If only one side had a space -> that space is removed, but a space is
                preserved if the other side is a non-space character, to avoid merging words.
            - If no spaces around the group -> the group is removed, but a space is inserted
                if there are non-space characters immediately before and after, to avoid merging words.
        """
        # Quick return if text doesn't contain emojis
        if "{emo:" not in text:
            return text

        # Check if emojis are enabled in settings
        emojis_active = Emoji._settings and Emoji._settings.get_boolean(["send_icon"])

        if emojis_active:
            # Simple substitution: replace each {emo:name} with the actual emoji
            def render_emojis(match):
                name = match.group(1).strip()
                return Emoji.get_emoji(name)

            return Emoji._EMOJI_PATTERN.sub(render_emojis, text)

        # Emojis disabled -> we must carefully remove them and normalize spaces
        # Pattern matches one or more {emo:...} possibly separated by spaces
        matches = list(Emoji._EMOJI_GROUP_PATTERN.finditer(text))
        if not matches:  # No emojis -> return unchanged
            return text

        result = text

        # Process matches right-to-left so indexes remain valid after replacements
        for match in reversed(matches):
            start, end = match.start(), match.end()

            # Detect if there's a space before/after the group
            space_before = start > 0 and result[start - 1] == " "
            space_after = end < len(result) and result[end] == " "

            if space_before and space_after:
                # Case: "foo {emo:x} bar"
                # Both sides have spaces -> replace group + both spaces with a single space
                replacement = " "
                start -= 1
                end += 1
            elif space_before:
                # Case: "foo {emo:x}"
                # # Only space before -> remove group + preceding space
                replacement = ""
                start -= 1
                # Preserve space if the char after group is non-space
                if end < len(result) and result[end] != " ":
                    replacement = " "
            elif space_after:
                # Case: "{emo:x} bar"
                # Only space after -> remove group + following space
                replacement = ""
                end += 1
                # Preserve space if char before group is non-space
                if start > 0 and result[start - 1] != " ":
                    replacement = " "
            else:
                # No spaces around -> remove group
                replacement = ""
                # Insert a space if there are non-space characters before and after
                if start > 0 and end < len(result) and result[start - 1] != " " and result[end] != " ":
                    replacement = " "
                else:
                    replacement = ""

            # Apply replacement in the result string
            result = result[:start] + replacement + result[end:]

        return result

    @staticmethod
    def get_custom_emoji_map():
        return Emoji._custom_emoji_map
