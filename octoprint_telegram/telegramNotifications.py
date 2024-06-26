import time, datetime
import octoprint.util


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
        "combined": True,
        "markup": "off",
    },
    "PrinterShutdown": {
        "text": "{emo:octopus} {emo:shutdown} Shutting down. Goodbye.",
        "image": False,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "PrintStarted": {
        "text": "Started printing {file}.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "PrintPaused": {
        "text": "Paused printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "PrintResumed": {
        "text": "Resumed printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "PrintFailed": {
        "text": "Printing {file} failed.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "ZChange": {
        "text": "Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}% done, {time_left} remaining.\nCompleted time {time_finish}.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "PrintDone": {
        "text": "Finished printing {file}.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "StatusNotPrinting": {
        "text": "Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
        "no_setting": True,
    },
    "StatusPrinting": {"bind_msg": "ZChange", "no_setting": True},
    "plugin_octolapse_movie_done": {"bind_msg": "MovieDone", "no_setting": True},
    "plugin_pause_for_user_event_notify": {
        "text": "{emo:warning} User interaction required.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "gCode_M600": {
        "text": "{emo:warning} Color change requested.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "Error": {
        "text": "{emo:warning} {emo:warning} {emo:warning} Printer Error {error_msg}",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "MovieDone": {
        "text": "{emo:movie} Movie done",
        "image": False,
        "silent": False,
        "gif": True,
        "combined": True,
        "markup": "off",
    },
    "Connected": {
        "text": "{emo:link symbol} Printer Connected",
        "image": False,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "Disconnected": {
        "text": "{emo:broken heart} Printer Disconnected",
        "image": False,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "Home": {
        "text": "{emo:house building} Printer received home command \nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "Alert": {
        "text": "{emo:bell} Printer received alert command \nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
    "UserNotif": {
        "text": "{emo:waving hand sign} User Notification {UserNotif_Text}",
        "image": True,
        "silent": False,
        "gif": False,
        "combined": True,
        "markup": "off",
    },
}


# Class to handle emojis on notification message format
class EmojiFormatter:
    def __init__(self, main):
        self.main = main

    def __format__(self, format):
        self.main._logger.debug(f"Formatting emoticon: '{format}'")
        if format in self.main.emojis:
            return self.main.gEmo(format)
        return ""


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
        if not status["state"]["flags"][
            "printing"
        ] or not self.is_notification_necessary(payload["new"], payload["old"]):
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
        if kwargs["event"] == "plugin_octolapse_movie_done":
            kwargs["event"] == "MovieDone"
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
        if (
            not self.is_usernotification_necessary()
        ):  # 18/11/2019 try to not send this message too much
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
            status = self.main._printer.get_current_data()
            event = kwargs["event"]
            self._logger.debug(f"event: {event}")
            try:
                kwargs["event"] = (
                    telegramMsgDict[event]["bind_msg"]
                    if "bind_msg" in telegramMsgDict[event]
                    else event
                )
            except Exception:
                self._logger.exception("Exception on get bind_msg")
                kwargs["event"] = event

            kwargs["with_image"] = self.main._settings.get(
                ["messages", str(kwargs["event"]), "image"]
            )
            self._logger.debug(
                f"send_gif = {self.main._settings.get(['send_gif'])} "
                f"and this message would send gif = {self.main._settings.get(['messages', str(kwargs['event']), 'gif'])}"
            )
            if self.main._settings.get(["send_gif"]):
                kwargs["with_gif"] = self.main._settings.get(
                    ["messages", str(kwargs["event"]), "gif"]
                )
            else:
                kwargs["with_gif"] = 0
            kwargs["silent"] = self.main._settings.get(
                ["messages", str(kwargs["event"]), "silent"]
            )

            self._logger.debug(f"Printer Status: {status}")
            # define locals for string formatting
            z = self.z
            temps = self.main._printer.get_current_temperatures()
            self._logger.debug(f"TEMPS - {temps}")
            bed_temp = temps["bed"]["actual"] if "bed" in temps else 0.0
            bed_target = temps["bed"]["target"] if "bed" in temps else 0.0
            e1_temp = temps["tool0"]["actual"] if "tool0" in temps else 0.0
            e1_target = temps["tool0"]["target"] if "tool0" in temps else 0.0
            e2_temp = temps["tool1"]["actual"] if "tool1" in temps else 0.0
            e2_target = temps["tool1"]["target"] if "tool1" in temps else 0.0
            percent = int(status["progress"]["completion"] or 0)

            try:
                Layers = self.main.get_current_layers()
                self._logger.debug(f"Layers - {Layers}")
                if not Layers is None:
                    currentLayer = Layers["layer"]["current"]
                    totalLayer = Layers["layer"]["total"]
                else:
                    currentLayer = "?"
                    totalLayer = "?"
            except Exception:
                self._logger.exception("Exception on get_current_layers")

            time_done = octoprint.util.get_formatted_timedelta(
                datetime.timedelta(seconds=(status["progress"]["printTime"] or 0))
            )
            if status["progress"]["printTimeLeft"] is None:
                time_left = "[Unknown]"
                time_finish = "[Unknown]"
            else:
                time_left = octoprint.util.get_formatted_timedelta(
                    datetime.timedelta(
                        seconds=(status["progress"]["printTimeLeft"] or 0)
                    )
                )
                try:
                    time_finish = self.main.calculate_ETA(time_left)
                except Exception as e:
                    time_finish = str(e)
                    self._logger.exception("Exception on formatting message")
            file = status["job"]["file"]["name"]
            path = status["job"]["file"]["path"]
            owner = status["job"]["user"]
            if owner is None:
                owner = ""
                if owner == "_api":
                    owner = ""

            try:
                if event == "PrintStarted":
                    # get additional metadata and thumbnail
                    self._logger.debug(f"get thumbnail url for path={path}")
                    meta = self.main._file_manager.get_metadata(
                        octoprint.filemanager.FileDestinations.LOCAL, path
                    )
                    if meta is not None and "thumbnail" in meta:
                        kwargs["thumbnail"] = meta["thumbnail"]
                    else:
                        kwargs["thumbnail"] = None
                    self._logger.debug(f"thumbnail = {kwargs['thumbnail']}")
                    self._logger.debug(f"meta = {meta}")
                else:
                    kwargs["thumbnail"] = None
            except Exception:
                self._logger.exception("Exception on getting thumbnail")

            try:
                if event == "plugin_octolapse_movie_done":
                    event = "MovieDone"
                if event == "MovieDone":
                    if "movie" in payload:
                        kwargs["movie"] = payload["movie"]
            except Exception:
                self._logger.exception("Exception on getting movie for MovieDone")

            if "user" in payload:
                user = payload["user"]
                if user is None:
                    user = ""
                if user == "_api":
                    user = "API"
            else:
                user = ""

            if "file" in payload:
                file = payload["file"]
            if "gcode" in payload:
                file = payload["gcode"]
            if "filename" in payload:
                file = payload["filename"]
            if "error" in payload:
                error_msg = payload["error"]
            if "UserNotif" in payload:
                UserNotif_Text = payload["UserNotif"]

            self._logger.debug(f"VARS - {locals()}")
            emo = EmojiFormatter(self.main)
            try:
                message = self.main._settings.get(
                    ["messages", kwargs["event"], "text"]
                ).format(emo, **locals())
            except Exception:
                self._logger.exception("Exception on formatting message")
                message = (
                    f"{self.main.gEmo('warning')} ERROR: I was not able to format the Notification for the event '{event}' properly.\n"
                    f"Please open your OctoPrint settings for {self.main._plugin_name} and check message settings for the event '{event}'."
                )
            self._logger.debug(f"Sending Notification: {message}")
            self._logger.debug(kwargs)
            # Do we want to send with Markup?
            kwargs["markup"] = self.main._settings.get(
                ["messages", kwargs["event"], "markup"]
            )
            # Finally send MSG
            kwargs["inline"] = False
            self.main.send_msg(message, **kwargs)
        except Exception:
            self._logger.exception("Exception on send notification")

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
