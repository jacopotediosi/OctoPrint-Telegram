import datetime
import time

import octoprint.util

from .emoji.emoji import Emoji

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
    },
    "PrinterShutdown": {
        "text": "{emo:shutdown} Shutting down. Goodbye.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "PrintStarted": {
        "text": "{emo:play} Started printing {file}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "PrintPaused": {
        "text": "{emo:pause} Paused printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "PrintResumed": {
        "text": "{emo:resume} Resumed printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "PrintFailed": {
        "text": "{emo:attention} Printing {file} failed.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "ZChange": {
        "text": "Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}% done, {time_left} remaining.\nCompleted time {time_finish}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "PrintDone": {
        "text": "{emo:finish} Finished printing {file}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "StatusNotPrinting": {
        "text": "Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
        "no_setting": True,
    },
    "StatusPrinting": {"bind_msg": "ZChange", "no_setting": True},
    "plugin_pause_for_user_event_notify": {
        "text": "{emo:warning} User interaction required.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "gCode_M600": {
        "text": "{emo:warning} Color change requested.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "Error": {
        "text": "{emo:attention} Printer Error {error_msg}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "plugin_octolapse_movie_done": {"bind_msg": "MovieDone", "no_setting": True},
    "MovieDone": {
        "text": "{emo:movie} Movie done.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "Connected": {
        "text": "{emo:online} Printer Connected.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "Disconnected": {
        "text": "{emo:offline} Printer Disconnected.",
        "image": False,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "Home": {
        "text": "{emo:home} Printer received home command\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "Alert": {
        "text": "{emo:notify} Printer received alert command\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
    },
    "UserNotif": {
        "text": "{emo:notify} User Notification: {UserNotif_Text}.",
        "image": True,
        "silent": False,
        "gif": False,
        "markup": "off",
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
        self.main.shut_up = {}
        kwargs["delay"] = self.main._settings.get_int(["message_at_print_done_delay"])
        self._sendNotification(payload, **kwargs)

    def msgPrintFailed(self, payload, **kwargs):
        self.main.shut_up = {}
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
            # Remember to add new variables to allowed_vars when adding them

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
            bed_temp = temps.get("bed", {}).get("actual", 0.0)
            bed_target = temps.get("bed", {}).get("target", 0.0)
            e1_temp = temps.get("tool0", {}).get("actual", 0.0)
            e1_target = temps.get("tool0", {}).get("target", 0.0)
            e2_temp = temps.get("tool1", {}).get("actual", 0.0)
            e2_target = temps.get("tool1", {}).get("target", 0.0)

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

            kwargs["markup"] = self.main._settings.get(["messages", event, "markup"])

            kwargs["inline"] = False

            # Log locals
            self._logger.debug(f"_sendNotification locals: {locals()}")

            # Format the message
            try:
                # TODO: escape html/markdown entities from the formatted variables

                class EmojiFormatter:
                    def __format__(self, fmt):
                        # Replace with corresponding emoji
                        return get_emoji(fmt)

                class AllowlistedContext(dict):
                    def __init__(self, allowed_vars, emoji_formatter):
                        self.allowed_vars = allowed_vars
                        self.emoji_formatter = emoji_formatter

                    def __getitem__(self, key):
                        # Replace user-defined variable if it is allowed, else fallback to literal
                        if key == "emo":
                            return self.emoji_formatter
                        return self.allowed_vars.get(key, "{" + key + "}")

                emoji_formatter = EmojiFormatter()
                context = AllowlistedContext(allowed_vars, emoji_formatter)

                message_template = self.main._settings.get(["messages", event, "text"])
                message = message_template.format_map(context)
            except Exception:
                self._logger.exception("caught an exception while formatting the message")
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
