import datetime
import html
import time
from typing import TYPE_CHECKING

import octoprint.util

from .emoji import Emoji
from .telegram_utils import escape_markdown

if TYPE_CHECKING:
    from . import TelegramPlugin

get_emoji = Emoji.get_emoji

# telegramMsgDict contains message settings.
# Each entry has the following structure:
#
#   <messageName>: {fields}
#
# - messageName (str):
#     The name of the message. You can hook into OctoPrint events by choosing the event name as the messageName.
#     See: http://docs.octoprint.org/en/master/events/index.html#sec-events-available-events
#
# Fields:
#
# - 'text' (str):
#     The default text sent with the notification. Supports both emoji and variables,
#     using the same format as the text that can be set from the plugin settings.
#
# - 'image' (bool):
#     The default message configuration. If true, the message will also include webcam snapshots.
#
# - 'gif' (bool):
#     The default message configuration. If true, the message will also include short webcam videos.
#
# - 'silent' (bool):
#     The default message configuration. If true, the notification will be sent silently.
#
# - 'markup' (str):
#     The default message configuration.  Controls markup for message text:
#       - 'HTML'      : use HTML markup
#       - 'Markdown'  : use Markdown markup
#       - 'MarkdownV2': use MarkdownV2 markup
#       - 'off'       : no markup
#
# - 'desc' (str):
#     Human-readable description shown in settings/help.
#
# - 'no_setting' (bool, optional):
#     If True, no checkbox will be shown in the plugin's notification settings.
#     Typically used for user-triggered messages. You must pass chat_id when sending them;
#     otherwise they will be sent to all users with notifications enabled.
#     Defaults to off.
#     Example: StatusNotPrinting and StatusNotConnected use this.
#
# - 'bind_msg' (str, optional):
#     Binds this message to another message by name. It shares text and other settings
#     with the bound message. When this notification is sent, it contains the same content
#     as the bound message, and no extra edit box is shown in the settings UI.
#     Examples: StatusPrinting and ZChange.
#
# IMPORTANT:
# If you add a new message to telegramMsgDict, you must also add its messageName
# to msgCmdDict in class TMSG to link it with its handler.
#
# Each time you add/remove a command or notification, please remember to increment the
# settings version number in `get_settings_version`.

telegramMsgDict = {
    "PrinterStart": {
        "text": "{emo:rocket} Hello. I'm online and ready to receive your commands.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when OctoPrint starts",
    },
    "PrinterShutdown": {
        "text": "{emo:shutdown} Shutting down. Goodbye.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when OctoPrint shuts down",
    },
    "PrintStarted": {
        "text": "{emo:play} Started printing {file}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when a print starts",
    },
    "PrintPaused": {
        "text": "{emo:pause} Paused printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when a print is paused",
    },
    "PrintResumed": {
        "text": "{emo:resume} Resumed printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when a print is resumed",
    },
    "PrintFailed": {
        "text": "{emo:attention} Printing {file} failed.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when a print fails",
    },
    "ZChange": {
        "text": "Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}% done, {time_left} remaining.\nCompleted time {time_finish}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the printer's Z-height changes (new layer)",
    },
    "PrintDone": {
        "text": "{emo:finish} Finished printing {file}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when a print completes successfully",
    },
    "StatusNotPrinting": {
        "text": "Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "no_setting": True,
        "desc": "Triggered on user request when no print is running",
    },
    "StatusNotConnected": {
        "text": "{emo:warning} Not connected to a printer. Use /con to connect.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "no_setting": True,
        "desc": "Triggered on user request when printer is not connected",
    },
    "StatusPrinting": {
        "bind_msg": "ZChange",
        "desc": "Triggered on user request when a print is running",
    },
    "PausedForUser": {
        "text": "{emo:warning} User interaction required.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the printer requests user interaction, via 'echo:busy: paused for user' or '// action:paused' on the serial line",
    },
    "gCode_M600": {
        "text": "{emo:warning} Color change requested.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when OctoPrint sends the M600 G-code (filament change) to the printer - only for prints started via OctoPrint",
    },
    "Error": {
        "text": "{emo:attention} Printer Error {error_msg}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered in case of an unrecoverable error (e.g., thermal runaway or connection loss)",
    },
    "plugin_octolapse_movie_done": {
        "bind_msg": "MovieDone",
        "desc": "Triggered when the Octolapse plugin finishes rendering the movie",
    },
    "MovieDone": {
        "text": "{emo:movie} Movie done.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the timelapse movie is completed",
    },
    "Connected": {
        "text": "{emo:online} Printer Connected.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when OctoPrint connects to the printer",
    },
    "Disconnected": {
        "text": "{emo:offline} Printer Disconnected.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the printer disconnects from OctoPrint",
    },
    "Home": {
        "text": "{emo:home} Printer received home command\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when OctoPrint sends the home command (G-code G28) to the printer",
    },
    "Alert": {
        "text": "{emo:notify} Printer received alert command\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when OctoPrint sends the M300 G-code to sound the printer buzzer",
    },
    "UserNotif": {
        "text": "{emo:notify} User Notification: {UserNotif_Text}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the printer sends 'echo:UserNotif TEXT' over serial, e.g. from a G-code like 'M118 E1 UserNotif TEXT'",
    },
    "PrusaMMU_Status": {
        "text": "Prusa MMU reported an update. Its status is: {prusammu[state]}. Previous tool: {prusammu[previousTool]}. Current tool: {prusammu[tool]}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the Prusa MMU plugin reports a status / tool change",
    },
    "PrusaMMU_Error": {
        "text": "{emo:warning} Prusa MMU reported an error. Its status is: {prusammu[state]}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the Prusa MMU plugin reports an error",
    },
}


class TMSG:
    def __init__(self, main: "TelegramPlugin"):
        self.main = main
        self._logger = main._logger.getChild("TMSG")

        self.z = ""
        self.last_z = 0.0
        self.last_notification_time = 0
        self.last_prusammu_state = ""

        self.msgCmdDict = {
            "Alert": self._sendNotification,
            "Connected": self._sendNotification,
            "Disconnected": self._sendNotification,
            "Error": self._sendNotification,
            "gCode_M600": self._sendNotification,
            "Home": self._sendNotification,
            "MovieDone": self._sendNotification,
            "PausedForUser": self._sendNotification,
            "plugin_octolapse_movie_done": self._sendNotification,
            "PrintDone": self._on_msgPrintDone,
            "PrinterShutdown": self._sendNotification,
            "PrinterStart": self._sendNotification,
            "PrintFailed": self._on_msgPrintFailed,
            "PrintPaused": self._sendNotification,
            "PrintResumed": self._sendNotification,
            "PrintStarted": self._on_msgPrintStarted,
            "PrusaMMU_Error": self._on_msgPrusaMMU,
            "PrusaMMU_Status": self._on_msgPrusaMMU,
            "StatusNotConnected": self._sendNotification,
            "StatusNotPrinting": self._sendNotification,
            "StatusPrinting": self._sendNotification,
            "UserNotif": self._sendNotification,
            "ZChange": self._on_msgZChange,
        }

    def startEvent(self, event, payload, **kwargs):
        # Not all events have payload
        payload = payload or {}

        status = self.main._printer.get_current_data()
        self.z = status["currentZ"] or 0.0
        kwargs["event"] = event
        self.msgCmdDict[event](payload, **kwargs)

    def _on_msgZChange(self, payload, **kwargs):
        status = self.main._printer.get_current_data()
        if not status["state"]["flags"]["printing"] or not self.is_notification_necessary(
            payload["new"], payload["old"]
        ):
            return
        self.z = payload["new"]
        self._logger.debug(
            "Z-Change. new_z=%.2f old_z=%.2f last_z=%.2f notification_height=%.2f notification_time=%d",
            self.z,
            payload["old"],
            self.last_z,
            self.main._settings.get_float(["notification_height"]),
            self.main._settings.get_int(["notification_time"]),
        )
        self._sendNotification(payload, **kwargs)

    def _on_msgPrintStarted(self, payload, **kwargs):
        self.last_z = 0.0
        self.last_notification_time = time.time()
        self._sendNotification(payload, **kwargs)

    def _on_msgPrintDone(self, payload, **kwargs):
        self.main.shut_up = set()
        kwargs["delay"] = self.main._settings.get_int(["message_at_print_done_delay"])
        self._sendNotification(payload, **kwargs)

    def _on_msgPrintFailed(self, payload, **kwargs):
        self.main.shut_up = set()
        self._sendNotification(payload, **kwargs)

    def _on_msgPrusaMMU(self, payload, **kwargs):
        state = payload.get("state", "")
        if state != self.last_prusammu_state:
            self.last_prusammu_state = state
            self._sendNotification(payload, **kwargs)

    def _sendNotification(self, payload, **kwargs):
        try:
            _logger = self._logger

            # --- Defines all template variables available for notification messages ---
            # To add new template variables, just add them as a @property in LazyVariables class

            class LazyVariables:
                """Context class that calculates template variables only when accessed"""

                def __init__(self, parent: "TMSG", payload, kwargs):
                    self.parent = parent
                    self.payload = payload
                    self.kwargs = kwargs
                    self._cache = {}

                def _get_cached(self, key, calculator):
                    """
                    Get cached value or calculate it if not cached.

                    The cache prevents calculating the same template variable multiple times
                    within a single notification message. The cache is local to each
                    notification and does not persist between different notifications.

                    Args:
                        key: Cache key for the variable
                        calculator: Lambda function that calculates the variable value

                    Returns:
                        The calculated or cached variable value
                    """
                    if key not in self._cache:
                        self._cache[key] = calculator()
                    return self._cache[key]

                @property
                def status(self):
                    """Current printer data from OctoPrint API"""
                    return self._get_cached("status", lambda: self.parent.main._printer.get_current_data())

                @property
                def event(self):
                    """Event that triggered the notification. If the event has an alias (bind_msg), it resolves to that."""

                    def calculate_event():
                        event = str(self.kwargs.get("event"))
                        event_bind_msg = telegramMsgDict.get(event, {}).get("bind_msg")
                        return event_bind_msg if event_bind_msg else event

                    return self._get_cached("event", calculate_event)

                @property
                def z(self):
                    """Current Z value"""
                    return self._get_cached("z", lambda: self.parent.z)

                @property
                def temps(self):
                    """Full temperature data for all tools and bed from OctoPrint API"""
                    return self._get_cached("temps", lambda: self.parent.main._printer.get_current_temperatures())

                @property
                def bed_temp(self):
                    """Current bed temperature"""
                    return self._get_cached("bed_temp", lambda: self.temps.get("bed", {}).get("actual", 0.0))

                @property
                def bed_target(self):
                    """Target bed temperature"""
                    return self._get_cached("bed_target", lambda: self.temps.get("bed", {}).get("target", 0.0))

                @property
                def e1_temp(self):
                    """Current temperature of extruder 1 (tool0)"""
                    return self._get_cached("e1_temp", lambda: self.temps.get("tool0", {}).get("actual", 0.0))

                @property
                def e1_target(self):
                    """Target temperature of extruder 1 (tool0)"""
                    return self._get_cached("e1_target", lambda: self.temps.get("tool0", {}).get("target", 0.0))

                @property
                def e2_temp(self):
                    """Current temperature of extruder 2 (tool1)"""
                    return self._get_cached("e2_temp", lambda: self.temps.get("tool1", {}).get("actual", 0.0))

                @property
                def e2_target(self):
                    """Target temperature of extruder 2 (tool1)"""
                    return self._get_cached("e2_target", lambda: self.temps.get("tool1", {}).get("target", 0.0))

                @property
                def e3_temp(self):
                    """Current temperature of extruder 3 (tool2)"""
                    return self._get_cached("e3_temp", lambda: self.temps.get("tool2", {}).get("actual", 0.0))

                @property
                def e3_target(self):
                    """Target temperature of extruder 3 (tool2)"""
                    return self._get_cached("e3_target", lambda: self.temps.get("tool2", {}).get("target", 0.0))

                @property
                def e4_temp(self):
                    """Current temperature of extruder 4 (tool3)"""
                    return self._get_cached("e4_temp", lambda: self.temps.get("tool3", {}).get("actual", 0.0))

                @property
                def e4_target(self):
                    """Target temperature of extruder 4 (tool3)"""
                    return self._get_cached("e4_target", lambda: self.temps.get("tool3", {}).get("target", 0.0))

                @property
                def e5_temp(self):
                    """Current temperature of extruder 5 (tool4)"""
                    return self._get_cached("e5_temp", lambda: self.temps.get("tool4", {}).get("actual", 0.0))

                @property
                def e5_target(self):
                    """Target temperature of extruder 5 (tool4)"""
                    return self._get_cached("e5_target", lambda: self.temps.get("tool4", {}).get("target", 0.0))

                @property
                def percent(self):
                    """Current percentage of the print progress"""

                    def calculate_percent():
                        progress = self.status.get("progress", {})
                        completion = progress.get("completion")
                        return int(completion if completion is not None else 0)

                    return self._get_cached("percent", calculate_percent)

                @property
                def time_done(self):
                    """Elapsed time of the current print"""

                    def calculate_time_done():
                        progress = self.status.get("progress", {})
                        print_time = progress.get("printTime") or 0
                        return octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=print_time))

                    return self._get_cached("time_done", calculate_time_done)

                @property
                def time_left(self):
                    """Remaining time of the current print"""

                    def _calculate_time_left():
                        progress = self.status.get("progress", {})
                        print_time_left = progress.get("printTimeLeft")
                        if print_time_left is not None:
                            return octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=print_time_left))
                        return "[Unknown]"

                    return self._get_cached("time_left", _calculate_time_left)

                @property
                def time_finish(self):
                    """Estimated finish time of the current print"""

                    def _calculate_time_finish():
                        progress = self.status.get("progress", {})
                        print_time_left = progress.get("printTimeLeft")
                        if print_time_left is not None:
                            return self.parent.main.calculate_ETA(print_time_left)

                    return self._get_cached("time_finish", _calculate_time_finish)

                @property
                def currentLayer(self):
                    """Current layer number"""

                    def calculate_current_layer():
                        layer_data = self.parent.main.get_layer_progress_values() or {}
                        layer_info = layer_data.get("layer") or {}
                        return layer_info.get("current", "?")

                    return self._get_cached("currentLayer", calculate_current_layer)

                @property
                def totalLayer(self):
                    """Total number of layers"""

                    def calculate_total_layer():
                        layer_data = self.parent.main.get_layer_progress_values() or {}
                        layer_info = layer_data.get("layer") or {}
                        return layer_info.get("total", "?")

                    return self._get_cached("totalLayer", calculate_total_layer)

                @property
                def owner(self):
                    """The name of the user who started the print"""
                    return self._get_cached("owner", lambda: self.status["job"].get("user") or "")

                @property
                def user(self):
                    """The name of the user who performed the action that triggered the notification (e.g., paused or canceled the print)"""
                    return self._get_cached("user", lambda: self.payload.get("user") or "")

                @property
                def file(self):
                    """File name of the file currently being printed"""

                    def calculate_file():
                        file = self.status.get("job", {}).get("file", {}).get("name", "")
                        for key in ("filename", "gcode", "file"):
                            value = self.payload.get(key)
                            if value:
                                file = value
                                break
                        return file

                    return self._get_cached("file", calculate_file)

                @property
                def path(self):
                    """Full path of the file currently being printed"""
                    return self._get_cached("path", lambda: self.status.get("job", {}).get("file", {}).get("path", ""))

                @property
                def error_msg(self):
                    """The error message string. Only useful for 'Error' event notifications."""
                    return self._get_cached("error_msg", lambda: self.payload.get("error", ""))

                @property
                def UserNotif_Text(self):
                    """The text received via the serial message echo:UserNotif TEXT, which is triggered by printing a G-code like: M118 E1 UserNotif TEXT."""
                    return self._get_cached("UserNotif_Text", lambda: self.payload.get("UserNotif", ""))

                @property
                def prusammu(self):
                    """A dictionary containing the current state of the Prusa MMU, provided by the Prusa MMU plugin."""

                    def calculate_prusammu():
                        return self.parent.main.send_octoprint_simpleapi_command("prusammu", "getmmu").json()

                    return self._get_cached("prusammu", calculate_prusammu)

                @property
                def enclosure(self):
                    """A dictionary containing the data provided by the Enclosure plugin, such as the temperatures measured by the sensors or the configured target temperature."""

                    def _calculate_enclosure():
                        enclosure = {"current_temps": {}, "humidity": {}, "target_temps": {}}
                        enclosure_plugin_id = "enclosure"
                        enclosure_module = self.parent.main._plugin_manager.get_plugin(enclosure_plugin_id, True)
                        if enclosure_module:
                            enclosure_implementation = self.parent.main._plugin_manager.plugins[
                                enclosure_plugin_id
                            ].implementation

                            for rpi_input in enclosure_implementation.rpi_inputs:
                                if rpi_input["input_type"] == "temperature_sensor":
                                    index_id = str(rpi_input["index_id"])
                                    label = rpi_input.get("label") or "Enclosure"
                                    temp = rpi_input.get("temp_sensor_temp", "")
                                    humidity = rpi_input.get("temp_sensor_humidity", "")

                                    if temp != "":
                                        enclosure["current_temps"][index_id] = {"label": label, "temp": temp}

                                    if humidity != "":
                                        enclosure["humidity"][index_id] = {"label": label, "humidity": humidity}

                            for rpi_output in enclosure_implementation.rpi_outputs:
                                if rpi_output["output_type"] == "temp_hum_control":
                                    index_id = str(rpi_output["index_id"])
                                    label = rpi_output.get("label") or "Enclosure"
                                    temp = rpi_output.get("temp_ctr_set_value", "")

                                    if temp != "":
                                        enclosure["target_temps"][index_id] = {"label": label, "temp": temp}
                        return enclosure

                    return self._get_cached("enclosure", _calculate_enclosure)

            lazy_vars = LazyVariables(self, payload, kwargs)

            event = lazy_vars.event

            # --- Set additional kwargs to send the message ---

            thumbnail = None
            try:
                if event == "PrintStarted":
                    metadata = self.main._file_manager.get_metadata(
                        octoprint.filemanager.FileDestinations.LOCAL, lazy_vars.path
                    )
                    if metadata:
                        thumbnail = metadata.get("thumbnail")
            except Exception:
                self._logger.exception("Exception on getting thumbnail")
            kwargs["thumbnail"] = thumbnail

            movie = payload.get("movie")
            if movie:
                kwargs["movie"] = movie

            kwargs["event"] = event

            with_image = bool(self.main._settings.get(["messages", event, "image"]) or False)
            kwargs["with_image"] = with_image

            event_gif = bool(self.main._settings.get(["messages", event, "gif"]) or False)
            send_gif_setting = bool(self.main._settings.get(["send_gif"]) or False)
            kwargs["with_gif"] = send_gif_setting and event_gif

            silent = bool(self.main._settings.get(["messages", event, "silent"]) or False)
            kwargs["silent"] = silent

            markup = self.main._settings.get(["messages", event, "markup"]) or "off"
            kwargs["markup"] = markup

            # Log locals for debugging (only accessed variables to avoid triggering lazy calculation)
            debug_info = {
                "event": event,
                "paload": payload,
                "kwargs": kwargs,
                "accessed_lazy_vars": list(lazy_vars._cache.keys()) if hasattr(lazy_vars, "_cache") else [],
            }
            self._logger.debug(f"_sendNotification debug info: {debug_info}")

            # Format the message
            try:

                class EmojiFormatter:
                    def __format__(self, fmt):
                        # Replace with corresponding emoji
                        return get_emoji(fmt)

                class MarkupEscapedValue:
                    """
                    Wrapper for template variable values that applies markup escaping at string conversion time.

                    This ensures that escaping happens AFTER template variable resolution and dictionary/list
                    navigation is complete. This allows users to write templates like {status[job][user]}
                    where the escaping is applied only to the final resolved value, not to intermediate
                    dictionary keys during navigation.

                    The wrapper maintains the markup context and applies the appropriate escaping
                    (HTML, Markdown, MarkdownV2) only when the final value is converted to string.
                    """

                    def __init__(self, value, markup):
                        self.value = value
                        self.markup = markup

                    def __getitem__(self, key):
                        try:
                            # Support dictionary/list navigation
                            return MarkupEscapedValue(self.value[key], self.markup)
                        except Exception:
                            _logger.exception("Caught an exception navigating dict/list")
                            # Return an error placeholder if attempting to access non-existent key or invalid index
                            return MarkupEscapedValue("[ERROR]", self.markup)

                    def __str__(self):
                        # Apply markup escaping only at final string conversion
                        val = str(self.value)
                        if self.markup == "HTML":
                            return html.escape(val)
                        elif self.markup == "Markdown":
                            return escape_markdown(val, 1)
                        elif self.markup == "MarkdownV2":
                            return escape_markdown(val, 2)
                        return val

                class SecureTemplateContext(dict):
                    """
                    Secure context for template variable access.

                    Only `lazy_vars` attributes decorated with `@property` can be accessed from templates.
                    Unknown or not allowed variables are returned as literal placeholders.
                    """

                    def __init__(self, lazy_vars, emoji_formatter, markup):
                        self.lazy_vars = lazy_vars
                        self.emoji_formatter = emoji_formatter
                        self.markup = markup

                        # Only variables of lazy_vars decorated with @property are allowed
                        self.allowed_vars = {
                            name for name, attr in type(lazy_vars).__dict__.items() if isinstance(attr, property)
                        }

                    def __getitem__(self, key):
                        # If it is an emoji, format it with emoji_formatter
                        if key == "emo":
                            return self.emoji_formatter

                        # If variable is not in allowed_vars, return it as a literal
                        if key not in self.allowed_vars:
                            return "{" + key + "}"

                        # Get the lazy value and wrap it with markup escaping
                        try:
                            lazy_value = getattr(self.lazy_vars, key)
                            return MarkupEscapedValue(lazy_value, self.markup)
                        except Exception:
                            _logger.exception("Caught an exception getting lazy_vars property")
                            # Return an error placeholder if getting the lazy_vars property raised an exception
                            return "[ERROR]"

                emoji_formatter = EmojiFormatter()
                context = SecureTemplateContext(lazy_vars, emoji_formatter, markup)

                message_template = self.main._settings.get(["messages", event, "text"])
                message = message_template.format_map(context)
            except Exception:
                self._logger.exception("Caught an exception while formatting the message")
                message = (
                    f"{get_emoji('attention')} I was not able to format the Notification for the event '{event}' properly.\n"
                    f"Please open your OctoPrint settings for {self.main._plugin_name} and check message settings for the event '{event}'."
                )

            # Send the message
            self._logger.debug("Sending notification: %s | kwargs: %r", message, kwargs)
            self.main.send_msg(message, **kwargs)
        except Exception:
            self._logger.exception("Exception in _sendNotification")

    # Helper to determine if notification will be send on gcode ZChange event.
    # Depends on notification time and notification height.
    def is_notification_necessary(self, new_z, old_z):
        timediff = self.main._settings.get_int(["notification_time"])
        if timediff and timediff > 0:
            # Check the timediff
            if self.last_notification_time + timediff * 60 <= time.time():
                self.last_notification_time = time.time()
                return True
        zdiff = self.main._settings.get_float(["notification_height"])
        if zdiff and zdiff > 0.0:
            if old_z is None or new_z < 0:
                return False
            # Check the zdiff
            if abs(new_z - (old_z or 0.0)) >= 1.0:
                # Big changes in height are not interesting for notifications - we ignore them
                self.last_z = new_z
                return False
            if new_z >= self.last_z + zdiff or new_z < self.last_z:
                self.last_z = new_z
                return True
        return False
