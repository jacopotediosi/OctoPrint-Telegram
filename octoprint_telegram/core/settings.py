from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from octoprint.plugin import PluginSettings


class Settings:
    """The plugin settings."""

    def __init__(self, settings: PluginSettings) -> None:
        """Set up the access to the plugin settings.

        Args:
            settings (PluginSettings): The OctoPrint settings accessor of this plugin.
        """
        self._settings = settings

    ##########
    ### Bot
    ##########

    @property
    def token(self) -> str:
        """The token of the Telegram bot the plugin talks to."""
        return self._settings.get(["token"]) or ""

    @property
    def http_proxy(self) -> str:
        """The proxy the HTTP calls to Telegram go through."""
        return self._settings.get(["http_proxy"]) or ""

    @property
    def https_proxy(self) -> str:
        """The proxy the HTTPS calls to Telegram go through."""
        return self._settings.get(["https_proxy"]) or ""

    ##########
    ### Notifications
    ##########

    @property
    def notification_height(self) -> float:
        """The increase in Z height, in millimetres, that triggers a progress notification, or 0 for none."""
        return self._settings.get_float(["notification_height"]) or 0.0

    @notification_height.setter
    def notification_height(self, value: float) -> None:
        self._settings.set_float(["notification_height"], value)

    @property
    def notification_time(self) -> int:
        """The minutes between progress notifications, or 0 for none."""
        return self._settings.get_int(["notification_time"]) or 0

    @notification_time.setter
    def notification_time(self, value: int) -> None:
        self._settings.set_int(["notification_time"], value)

    @property
    def message_at_print_done_delay(self) -> int:
        """The seconds to wait after a print finishes before notifying."""
        return self._settings.get_int(["message_at_print_done_delay"]) or 0

    @property
    def force_loop_message(self) -> bool:
        """Whether the printing status is notified on a loop, for prints that raise no events."""
        return bool(self._settings.get_boolean(["ForceLoopMessage"]))

    @property
    def send_gif(self) -> bool:
        """Whether webcam videos may be attached to messages."""
        return bool(self._settings.get_boolean(["send_gif"]))

    ##########
    ### Commands
    ##########

    @property
    def no_mistake(self) -> bool:
        """Whether the bot stays quiet instead of replying to unknown commands."""
        return bool(self._settings.get_boolean(["no_mistake"]))

    @property
    def select_file_after_upload(self) -> bool:
        """Whether a file uploaded to the bot should be then selected for printing."""
        return bool(self._settings.get_boolean(["select_file_after_upload"]))

    @property
    def sort_files_by_date(self) -> bool:
        """Whether the file list is sorted by upload date, newest first, instead of by name."""
        return bool(self._settings.get_boolean(["sort_files_by_date"]))

    @sort_files_by_date.setter
    def sort_files_by_date(self, value: bool) -> None:
        self._settings.set_boolean(["sort_files_by_date"], value)

    @property
    def show_models_in_files(self) -> bool:
        """Whether the file list also includes model files."""
        return bool(self._settings.get_boolean(["show_models_in_files"]))

    @show_models_in_files.setter
    def show_models_in_files(self, value: bool) -> None:
        self._settings.set_boolean(["show_models_in_files"], value)

    @property
    def imgbb_api_key(self) -> str:
        """The ImgBB API key used to upload the thumbnails shown while browsing files."""
        return self._settings.get(["imgbbApiKey"]) or ""

    ##########
    ### Webcam media
    ##########

    @property
    def no_cpulimit(self) -> bool:
        """Whether webcam videos are recorded without cpulimit/limitcpu."""
        return bool(self._settings.get_boolean(["no_cpulimit"]))

    @property
    def ffmpeg_preset(self) -> str:
        """The encoding speed ffmpeg records webcam videos with, as a FfmpegPreset value."""
        return self._settings.get(["ffmpeg_preset"]) or ""

    @property
    def pre_img_method(self) -> str:
        """How the action before taking a webcam image is run, as an ImageHookMethod value."""
        return self._settings.get(["PreImgMethod"]) or ""

    @property
    def pre_img_command(self) -> str:
        """The command the action before taking a webcam image runs."""
        return self._settings.get(["PreImgCommand"]) or ""

    @property
    def pre_img_delay(self) -> int:
        """The seconds to wait between the action before taking a webcam image and the capture."""
        return self._settings.get_int(["PreImgDelay"], min=0) or 0

    @property
    def post_img_method(self) -> str:
        """How the action after taking a webcam image is run, as an ImageHookMethod value."""
        return self._settings.get(["PostImgMethod"]) or ""

    @property
    def post_img_command(self) -> str:
        """The command the action after taking a webcam image runs."""
        return self._settings.get(["PostImgCommand"]) or ""

    @property
    def post_img_delay(self) -> int:
        """The seconds to wait between the capture and the action after taking a webcam image."""
        return self._settings.get_int(["PostImgDelay"], min=0) or 0

    ##########
    ### Time formats
    ##########

    @property
    def time_format(self) -> str:
        """The strftime format for a time falling within the day."""
        return self._settings.get(["TimeFormat"]) or ""

    @property
    def day_time_format(self) -> str:
        """The strftime format for a time falling within the week."""
        return self._settings.get(["DayTimeFormat"]) or ""

    @property
    def week_time_format(self) -> str:
        """The strftime format for a time more than a week ahead."""
        return self._settings.get(["WeekTimeFormat"]) or ""

    ##########
    ### Chats
    ##########

    @property
    def chats(self) -> dict[str, dict]:
        """Settings of every known chat, keyed by chat id."""
        return self._settings.get(["chats"]) or {}

    @chats.setter
    def chats(self, value: dict[str, dict]) -> None:
        self._settings.set(["chats"], value)

    def chat(self, chat_id: str) -> dict | None:
        """Settings of a single chat, or None if the chat is unknown."""
        return self._settings.get(["chats", str(chat_id)])

    def set_chat(self, chat_id: str, chat_settings: dict) -> None:
        """Store the settings of a single chat."""
        self._settings.set(["chats", str(chat_id)], chat_settings)

    def set_chat_field(self, chat_id: str, field: str, value: str) -> None:
        """Store one field in the settings of a single chat."""
        self._settings.set(["chats", str(chat_id), field], value)

    def remove_chat(self, chat_id: str) -> None:
        """Remove a chat from the known chats."""
        self._settings.remove(["chats", str(chat_id)])

    ##########
    ### Notification messages
    ##########

    def message(self, event: str) -> dict:
        """Configuration of the notification message for an event."""
        return self._settings.get(["messages", event], merged=True) or {}

    ##########
    ### Persistence
    ##########

    def save(self) -> None:
        """Write the settings to disk."""
        self._settings.save()


class OctoPrintSettings:
    """The settings stored by OctoPrint itself."""

    def __init__(self, settings: PluginSettings) -> None:
        """Set up the access to the settings stored by OctoPrint itself.

        Args:
            settings (PluginSettings): The OctoPrint settings accessor of this plugin.
        """
        self._settings = settings

    ##########
    ### Other plugins
    ##########

    def plugin_setting(self, plugin_id: str, *path: str) -> Any:  # noqa: ANN401
        """A setting belonging to another plugin."""
        return self._settings.global_get(["plugins", plugin_id, *path])

    ##########
    ### API
    ##########

    @property
    def global_api_key(self) -> str | None:
        """OctoPrint's global API key."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return self._settings.global_get(["api", "key"])

    ##########
    ### Webcam
    ##########

    @property
    def ffmpeg_path(self) -> str | None:
        """The path of the ffmpeg binary."""
        return self._settings.global_get(["webcam", "ffmpeg"])

    @property
    def webcam_name(self) -> str | None:
        """The name of the webcam."""
        return self._settings.global_get(["webcam", "name"])

    @property
    def webcam_snapshot(self) -> str | None:
        """The URL a webcam snapshot is fetched from."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return self._settings.global_get(["webcam", "snapshot"])

    @property
    def webcam_snapshot_timeout(self) -> int | None:
        """The seconds to wait for a webcam snapshot."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return self._settings.global_get_int(["webcam", "snapshotTimeout"])

    @property
    def webcam_snapshot_ssl_validation(self) -> bool:
        """Whether the certificate of the snapshot URL is validated."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return bool(self._settings.global_get_boolean(["webcam", "snapshotSslValidation"]))

    @property
    def webcam_stream(self) -> str | None:
        """The URL of the webcam stream."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return self._settings.global_get(["webcam", "stream"])

    @property
    def webcam_flip_h(self) -> bool:
        """Whether the webcam image is flipped horizontally."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return bool(self._settings.global_get_boolean(["webcam", "flipH"]))

    @property
    def webcam_flip_v(self) -> bool:
        """Whether the webcam image is flipped vertically."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return bool(self._settings.global_get_boolean(["webcam", "flipV"]))

    @property
    def webcam_rotate_90(self) -> bool:
        """Whether the webcam image is rotated by 90 degrees."""
        # nosemgrep (this is a fallback for older OctoPrint versions)
        return bool(self._settings.global_get_boolean(["webcam", "rotate90"]))

    ##########
    ### Printer connection
    ##########

    @property
    def preferred_connector(self) -> str | None:
        """The connector OctoPrint connects to the printer with."""
        return self._settings.global_get(["printerConnection", "preferred", "connector"])

    @property
    def preferred_connection_parameters(self) -> dict:
        """The parameters OctoPrint connects to the printer with."""
        return self._settings.global_get(["printerConnection", "preferred", "parameters"]) or {}

    ##########
    ### Custom controls
    ##########

    @property
    def controls(self) -> list:
        """The custom controls defined by the user."""
        return self._settings.global_get(["controls"]) or []

    ##########
    ### System
    ##########

    @property
    def system_actions(self) -> list:
        """The system actions defined by the user."""
        return self._settings.global_get(["system", "actions"]) or []

    def server_command(self, name: str) -> str | None:
        """The shell command OctoPrint runs for one of its own server actions, such as restarting or shutting down."""
        return self._settings.global_get(["server", "commands", name])

    @property
    def online_check_host(self) -> str | None:
        """The host OctoPrint reaches to tell whether it is online."""
        return self._settings.global_get(["server", "onlineCheck", "host"])

    @property
    def online_check_port(self) -> int | None:
        """The port OctoPrint reaches to tell whether it is online."""
        return self._settings.global_get(["server", "onlineCheck", "port"])
