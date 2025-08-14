import datetime
import html
import time

import octoprint.util

from .emoji.emoji import Emoji
from .telegram_utils import escape_markdown

get_emoji = Emoji.get_emoji

##########################################################################################################################
# Here you find the known notification messages and their handles.
# The only way to start a messageHandle should be via on_event() in __init__.py
# If you want to add/remove notifications read the following:
# SEE DOCUMENTATION IN WIKI: https://github.com/jacopotediosi/OctoPrint-Telegram/wiki/Add%20commands%20and%20notifications
##########################################################################################################################

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
    "StatusPrinting": {
        "bind_msg": "ZChange",
        "no_setting": True,
        "desc": "Triggered on user request when a print is running",
    },
    "plugin_pause_for_user_event_notify": {
        "text": "{emo:warning} User interaction required.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "desc": "Triggered when the printer requests user interaction, via 'echo:busy: paused for user' or '//action:paused' on the serial line",
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
        "no_setting": True,
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
}


class TMSG:
    def __init__(self, main):
        self.main = main
        self.last_z = 0.0
        self.last_notification_time = 0
        self.z = ""
        self._logger = main._logger.getChild("TMSG")

        self.msgCmdDict = {
            "PrinterStart": self.msgPrinterStart_Shutdown,
            "PrinterShutdown": self.msgPrinterStart_Shutdown,
            "PrintStarted": self.msgPrintStarted,
            "PrintFailed": self.msgPrintFailed,
            "PrintPaused": self.msgPaused,
            "PrintResumed": self.msgResumed,
            "ZChange": self.msgZChange,
            "PrintDone": self.msgPrintDone,
            "StatusNotPrinting": self.msgStatusNotPrinting,
            "StatusPrinting": self.msgStatusPrinting,
            "plugin_pause_for_user_event_notify": self.msgPauseForUserEventNotify,
            "gCode_M600": self.msgColorChangeRequested,
            "Error": self.msgPrinterError,
            "MovieDone": self.msgMovieDone,
            "plugin_octolapse_movie_done": self.msgMovieDone,
            "UserNotif": self.msgUserNotif,
            "Connected": self.msgConnected,
            "Disconnected": self.msgConnected,
            "Alert": self.msgConnected,
            "Home": self.msgConnected,
        }

    def startEvent(self, event, payload, **kwargs):
        status = self.main._printer.get_current_data()
        self.z = status["currentZ"] or 0.0
        kwargs["event"] = event
        self.msgCmdDict[event](payload, **kwargs)

    def msgPrinterStart_Shutdown(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgZChange(self, payload, **kwargs):
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

    def msgPrintStarted(self, payload, **kwargs):
        self.last_z = 0.0
        self.last_notification_time = time.time()
        self._sendNotification(payload, **kwargs)

    def msgPrintDone(self, payload, **kwargs):
        self.main.shut_up = set()
        kwargs["delay"] = self.main._settings.get_int(["message_at_print_done_delay"])
        self._sendNotification(payload, **kwargs)

    def msgPrintFailed(self, payload, **kwargs):
        self.main.shut_up = set()
        self._sendNotification(payload, **kwargs)

    def msgMovieDone(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgPrinterError(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgPaused(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgResumed(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgStatusPrinting(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgStatusNotPrinting(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgPauseForUserEventNotify(self, payload, **kwargs):
        if payload is None:
            payload = {}
        if not self.is_usernotification_necessary():  # 18/11/2019 try to not send this message too much
            return
        self._sendNotification(payload, **kwargs)

    def msgColorChangeRequested(self, payload, **kwargs):
        if payload is None:
            payload = {}
        self._sendNotification(payload, **kwargs)

    def msgUserNotif(self, payload, **kwargs):
        if payload is None:
            payload = {}
        self._sendNotification(payload, **kwargs)

    def msgConnected(self, payload, **kwargs):
        if payload is None:
            payload = {}
        self._sendNotification(payload, **kwargs)

    def _sendNotification(self, payload, **kwargs):
        try:
            # --- Defines all formatted variables available for notification messages ---
            # Remember to add new variables to allowed_vars

            # Status
            status = self.main._printer.get_current_data()

            # Event
            event = str(kwargs.get("event"))
            event_bind_msg = telegramMsgDict.get(event, {}).get("bind_msg")
            if event_bind_msg:
                event = event_bind_msg

            # Z
            z = self.z

            # Temperatures
            temps = self.main._printer.get_current_temperatures()
            bed = temps.get("bed", {})
            bed_temp = bed.get("actual", 0.0)
            bed_target = bed.get("target", 0.0)
            tool0 = temps.get("tool0", {})
            e1_temp = tool0.get("actual", 0.0)
            e1_target = tool0.get("target", 0.0)
            tool1 = temps.get("tool1", {})
            e2_temp = tool1.get("actual", 0.0)
            e2_target = tool1.get("target", 0.0)
            tool2 = temps.get("tool2", {})
            e3_temp = tool2.get("actual", 0.0)
            e3_target = tool2.get("target", 0.0)
            tool3 = temps.get("tool3", {})
            e4_temp = tool3.get("actual", 0.0)
            e4_target = tool3.get("target", 0.0)
            tool4 = temps.get("tool4", {})
            e5_temp = tool4.get("actual", 0.0)
            e5_target = tool4.get("target", 0.0)

            # Percent
            progress = status.get("progress", {})
            completion = progress.get("completion")
            percent = int(completion if completion is not None else 0)

            # Time done
            print_time = progress.get("printTime") or 0
            time_done = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=print_time))

            # Time left and ETA
            time_left = "[Unknown]"
            time_finish = "[Unknown]"
            print_time_left = progress.get("printTimeLeft")
            if print_time_left is not None:
                time_left = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=print_time_left))
                try:
                    time_finish = self.main.calculate_ETA(print_time_left)
                except Exception:
                    self._logger.exception("Caught an exception calculating ETA")

            # Layer data
            layer_data = self.main.get_layer_progress_values() or {}
            layer_info = layer_data.get("layer") or {}
            currentLayer = layer_info.get("current", "?")
            totalLayer = layer_info.get("total", "?")

            # Who started the print
            owner = status["job"].get("user") or ""

            # Who performed the action causing the notification (e.g., pause, abort)
            user = payload.get("user") or ""

            # File and file path
            file = status.get("job", {}).get("file", {}).get("name", "")
            for key in ("filename", "gcode", "file"):
                value = payload.get(key)
                if value:
                    file = value
                    break
            path = status.get("job", {}).get("file", {}).get("path", "")

            # For "Error" event
            error_msg = payload.get("error", "")

            # Serial echo:UserNotif, e.g.: M118 E1 UserNotif XXXXX
            UserNotif_Text = payload.get("UserNotif", "")

            enclosure = {"current_temps": {}, "humidity": {}, "target_temps": {}}
            try:
                enclosure_plugin_id = "enclosure"
                enclosure_module = self.main._plugin_manager.get_plugin(enclosure_plugin_id, True)
                if enclosure_module:
                    enclosure_implementation = self.main._plugin_manager.plugins[enclosure_plugin_id].implementation

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
            except Exception:
                self._logger.exception("Caught an exception getting enclosure data")

            # Variables allowed in the message formatting context
            allowed_vars = dict(
                status=status,
                event=event,
                z=z,
                temps=temps,
                bed_temp=bed_temp,
                bed_target=bed_target,
                e1_temp=e1_temp,
                e1_target=e1_target,
                e2_temp=e2_temp,
                e2_target=e2_target,
                e3_temp=e3_temp,
                e3_target=e3_target,
                e4_temp=e4_temp,
                e4_target=e4_target,
                e5_temp=e5_temp,
                e5_target=e5_target,
                percent=percent,
                currentLayer=currentLayer,
                totalLayer=totalLayer,
                time_done=time_done,
                time_left=time_left,
                time_finish=time_finish,
                owner=owner,
                user=user,
                file=file,
                path=path,
                error_msg=error_msg,
                UserNotif_Text=UserNotif_Text,
                enclosure=enclosure,
            )

            # --- Set additional kwargs to send the message ---

            thumbnail = None
            try:
                if event == "PrintStarted":
                    metadata = self.main._file_manager.get_metadata(octoprint.filemanager.FileDestinations.LOCAL, path)
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

            kwargs["inline"] = False

            # Log locals
            self._logger.debug(f"_sendNotification locals: {locals()}")

            # Format the message
            try:

                class EmojiFormatter:
                    def __format__(self, fmt):
                        # Replace with corresponding emoji
                        return get_emoji(fmt)

                class LazyEscaped:
                    def __init__(self, value, markup):
                        self.value = value
                        self.markup = markup

                    def __getitem__(self, key):
                        return LazyEscaped(self.value[key], self.markup)

                    def __str__(self):
                        val = str(self.value)
                        if self.markup == "HTML":
                            return html.escape(val)
                        elif self.markup == "Markdown":
                            return escape_markdown(val, 1)
                        elif self.markup == "MarkdownV2":
                            return escape_markdown(val, 2)
                        return val

                class AllowlistedContext(dict):
                    def __init__(self, allowed_vars, emoji_formatter, markup):
                        self.allowed_vars = allowed_vars
                        self.emoji_formatter = emoji_formatter
                        self.markup = markup

                    def __getitem__(self, key):
                        # If it is an emoji, format it with emoji_formatter
                        if key == "emo":
                            return self.emoji_formatter

                        # If variable is not in allowed_vars, return it as a literal
                        if key not in self.allowed_vars:
                            return "{" + key + "}"

                        # Return variable within wrapper that applies markup escaping when the value is formatted
                        return LazyEscaped(self.allowed_vars[key], self.markup)

                emoji_formatter = EmojiFormatter()
                context = AllowlistedContext(allowed_vars, emoji_formatter, markup)

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

    def is_usernotification_necessary(self):
        timediff = 30  # Force to every 30 seconds
        # Check the timediff
        self._logger.debug(
            f"self.last_notification_time + timediff: {self.last_notification_time + timediff} <= time.time(): {time.time()}"
        )
        if self.last_notification_time + timediff <= time.time():
            self.last_notification_time = time.time()
            return True
        return False
