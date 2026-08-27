from __future__ import annotations

from dataclasses import dataclass

from ..telegram import Markup


@dataclass(frozen=True)
class NotificationDefinition:
    """
    Describes a notification the bot can send: what it says and how it is presented.

    Every field but the description is a default the user can change from the plugin settings.

    Fields:

    - description (str):
        Human-readable description shown in settings/help.

    - text (str, optional):
        The text sent with the notification. Supports both emoji and variables,
        using the same format as the text that can be set from the plugin settings.

    - markup (Markup, optional):
        The markup Telegram parses in the text.

    - image (bool, optional):
        If true, the message will also include webcam snapshots.

    - gif (bool, optional):
        If true, the message will also include webcam videos.

    - silent (bool, optional):
        If true, the notification will be sent silently.

    - shown_in_settings (bool, optional):
        Whether a checkbox for this notification is shown in the plugin's notification settings.
        The notifications without one are triggered by users. You must pass chat_id when sending them;
        otherwise they will be sent to all users with notifications enabled.
        Example: StatusNotPrinting and StatusNotConnected are not shown.

    - bind_message (str, optional):
        Binds this message to another message by name. It shares text and other settings
        with the bound message. When this notification is sent, it contains the same content
        as the bound message, and no extra edit box is shown in the settings UI.
        Examples: StatusPrinting and ZChange.
    """

    description: str
    text: str = ""
    markup: Markup = Markup.OFF
    image: bool = False
    gif: bool = False
    silent: bool = False
    shown_in_settings: bool = True
    bind_message: str | None = None

    def __post_init__(self):
        if not self.description.strip():
            raise ValueError("A notification has no description")

    def as_settings(self) -> dict:
        """The notification as it is stored in the plugin settings."""
        if self.bind_message:
            return {"bind_msg": self.bind_message, "desc": self.description}

        settings = {
            "text": self.text,
            "image": self.image,
            "silent": self.silent,
            "gif": self.gif,
            "markup": self.markup.value,
            "desc": self.description,
        }

        if not self.shown_in_settings:
            settings["no_setting"] = True

        return settings


# IMPORTANT:
# If you add a new notification here, you must also add its name to
# `_event_handlers` in class Notifications to link it with its handler.
#
# Each time you add/remove a command or notification, please remember also
# to increment the settings version number in `get_settings_version`.
NOTIFICATION_DEFINITIONS: dict[str, NotificationDefinition] = {
    "PrinterStart": NotificationDefinition(
        text="{emo:rocket} Hello. I'm online and ready to receive your commands.",
        description="Triggered when OctoPrint starts",
    ),
    "PrinterShutdown": NotificationDefinition(
        text="{emo:shutdown} Shutting down. Goodbye.",
        description="Triggered when OctoPrint shuts down",
    ),
    "PrintStarted": NotificationDefinition(
        text="{emo:play} Started printing {file}.",
        image=True,
        description="Triggered when a print starts",
    ),
    "PrintPaused": NotificationDefinition(
        text="{emo:pause} Paused printing {file} at {percent}%. {time_left} remaining.",
        image=True,
        description="Triggered when a print is paused",
    ),
    "PrintResumed": NotificationDefinition(
        text="{emo:resume} Resumed printing {file} at {percent}%. {time_left} remaining.",
        image=True,
        description="Triggered when a print is resumed",
    ),
    "PrintFailed": NotificationDefinition(
        text="{emo:attention} Printing {file} failed.",
        image=True,
        description="Triggered when a print fails",
    ),
    "ZChange": NotificationDefinition(
        text="Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}% done, {time_left} remaining.\nCompleted time {time_finish}.",
        image=True,
        description="Triggered when the printer's Z-height changes (new layer)",
    ),
    "PrintDone": NotificationDefinition(
        text="{emo:finish} Finished printing {file}.",
        image=True,
        description="Triggered when a print completes successfully",
    ),
    "StatusNotPrinting": NotificationDefinition(
        text="Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        image=True,
        shown_in_settings=False,
        description="Triggered on user request when no print is running",
    ),
    "StatusNotConnected": NotificationDefinition(
        text="{emo:warning} Not connected to a printer. Use /con to connect.",
        image=True,
        shown_in_settings=False,
        description="Triggered on user request when printer is not connected",
    ),
    "StatusPrinting": NotificationDefinition(
        bind_message="ZChange",
        description="Triggered on user request when a print is running",
    ),
    "PausedForUser": NotificationDefinition(
        text="{emo:warning} User interaction required.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        image=True,
        description="Triggered when the printer requests user interaction, via 'echo:busy: paused for user' or '// action:paused' on the serial line",
    ),
    "gCode_M600": NotificationDefinition(
        text="{emo:warning} Color change requested.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        image=True,
        description="Triggered when OctoPrint sends the M600 G-code (filament change) to the printer - only for prints started via OctoPrint",
    ),
    "Error": NotificationDefinition(
        text="{emo:attention} Printer Error {error_msg}.",
        image=True,
        description="Triggered in case of an unrecoverable error (e.g., thermal runaway or connection loss)",
    ),
    "plugin_octolapse_movie_done": NotificationDefinition(
        bind_message="MovieDone",
        description="Triggered when the Octolapse plugin finishes rendering the movie",
    ),
    "MovieDone": NotificationDefinition(
        text="{emo:movie} Movie done.",
        description="Triggered when the timelapse movie is completed",
    ),
    "Connected": NotificationDefinition(
        text="{emo:online} Printer Connected.",
        description="Triggered when OctoPrint connects to the printer",
    ),
    "Disconnected": NotificationDefinition(
        text="{emo:offline} Printer Disconnected.",
        description="Triggered when the printer disconnects from OctoPrint",
    ),
    "Home": NotificationDefinition(
        text="{emo:home} Printer received home command\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        image=True,
        description="Triggered when OctoPrint sends the home command (G-code G28) to the printer",
    ),
    "Alert": NotificationDefinition(
        text="{emo:notify} Printer received alert command\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        image=True,
        description="Triggered when OctoPrint sends the M300 G-code to sound the printer buzzer",
    ),
    "UserNotif": NotificationDefinition(
        text="{emo:notify} User Notification: {UserNotif_Text}.",
        image=True,
        description="Triggered when the printer sends 'echo:UserNotif TEXT' over serial, e.g. from a G-code like 'M118 E1 UserNotif TEXT'",
    ),
    "PrusaMMU_Status": NotificationDefinition(
        text="Prusa MMU reported an update. Its status is: {prusammu[state]}. Previous tool: {prusammu[previousTool]}. Current tool: {prusammu[tool]}.",
        image=True,
        description="Triggered when the Prusa MMU plugin reports a status / tool change",
    ),
    "PrusaMMU_Error": NotificationDefinition(
        text="{emo:warning} Prusa MMU reported an error. Its status is: {prusammu[state]}.",
        image=True,
        description="Triggered when the Prusa MMU plugin reports an error",
    ),
}
"""
The notifications the bot can send, keyed by notification name.

Give a notification the name of an event, and that event will trigger it. Events are published
on OctoPrint's event bus, by OctoPrint itself or by any plugin.
See: http://docs.octoprint.org/en/master/events/index.html#sec-events-available-events
"""
