from enum import Enum


class ChatAction(Enum):
    """The activity indicator Telegram shows in a chat."""

    TYPING = "typing"
    UPLOAD_PHOTO = "upload_photo"
    UPLOAD_VIDEO = "upload_video"
    UPLOAD_DOCUMENT = "upload_document"
    RECORD_VIDEO = "record_video"


class ChatMemberStatus(Enum):
    """The role the bot has in a chat."""

    CREATOR = "creator"
    ADMINISTRATOR = "administrator"
    MEMBER = "member"
    RESTRICTED = "restricted"
    LEFT = "left"
    KICKED = "kicked"


class ChatType(Enum):
    """The type of a chat."""

    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class HttpMethod(Enum):
    """The HTTP methods the Telegram Bot API is called with."""

    GET = "get"
    POST = "post"


class Markup(Enum):
    """The markup Telegram parses in the text of a message."""

    OFF = "off"
    HTML = "HTML"
    MARKDOWN = "Markdown"
    MARKDOWN_V2 = "MarkdownV2"
