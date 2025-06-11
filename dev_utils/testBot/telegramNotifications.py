import time

###################################################################################################
# Here you find the known notification messages and their handles.
# The only way to start a messageHandle should be via on_event() in __init__.py
# If you want to add/remove notifications read the following:
# SEE DOCUMENTATION IN WIKI: https://github.com/jacopotediosi/OctoPrint-Telegram/wiki/Add%20commands%20and%20notifications
#####################################################################################################################################################

telegramMsgDict = {
    "PrinterStart": {
        "text": "{emo:rocket} Hello. I'm online and ready to receive your commands.",
        "image": False,
        "combined": True,
        "markup": "off",
    },
    "PrinterShutdown": {
        "text": "{emo:octo} {emo:shutdown} Shutting down. Goodbye.",
        "image": False,
        "combined": True,
        "markup": "off",
    },
    "PrintStarted": {
        "text": "Started printing {file}.",
        "image": True,
        "combined": True,
        "markup": "off",
    },
    "PrintPaused": {
        "text": "Paused printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "combined": True,
        "markup": "off",
    },
    "PrintResumed": {
        "text": "Resumed printing {file} at {percent}%. {time_left} remaining.",
        "image": True,
        "combined": True,
        "markup": "off",
    },
    "PrintFailed": {
        "text": "Printing {file} failed.",
        "image": True,
        "combined": True,
        "markup": "off",
    },
    "ZChange": {
        "text": "Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}% done, {time_left} remaining.",
        "image": True,
        "combined": True,
        "markup": "off",
    },
    "PrintDone": {
        "text": "Finished printing {file}.",
        "image": True,
        "combined": True,
        "markup": "off",
    },
    "StatusNotPrinting": {
        "text": "Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.",
        "image": True,
        "combined": True,
        "markup": "off",
        "no_setting": True,
    },
    "StatusPrinting": {"bind_msg": "ZChange", "no_setting": True},
}


# class to handle emojis on notifigation message format
class EmojiFormatter:
    def __init__(self, main):
        self.main = main

    def __format__(self, format):
        if format in self.main.emojis:
            return self.main.gEmo(format).encode("utf-8")
        return ""


class TMSG:
    def __init__(self, main):
        self.main = main
        self.last_z = 0.0
        self.last_notification_time = 0
        self.z = ""
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
        }

    def startEvent(self, event, payload, **kwargs):
        self.z = 0.0
        kwargs["event"] = event
        self.msgCmdDict[event](payload, **kwargs)

    def msgPrinterStart_Shutdown(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgZChange(self, payload, **kwargs):
        status = {}
        if not status["state"]["flags"][
            "printing"
        ] or not self.is_notification_necessary(0.2, 0.3):
            return
        self.z = 0.3
        print("Z-Change. new_z=old_z=last_z= notification_height= notification_time=")

        self._sendNotification(payload, **kwargs)

    def msgPrintStarted(self, payload, **kwargs):
        self.last_z = 0.0
        self.last_notification_time = time.time()
        self._sendNotification(payload, **kwargs)

    def msgPrintDone(self, payload, **kwargs):
        self.main.shut_up = {}
        kwargs["delay"] = self.main._settings["message_at_print_done_delay"]
        self._sendNotification(payload, **kwargs)

    def msgPrintFailed(self, payload, **kwargs):
        self.main.shut_up = {}
        self._sendNotification(payload, **kwargs)

    def msgPaused(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgResumed(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgStatusPrinting(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def msgStatusNotPrinting(self, payload, **kwargs):
        self._sendNotification(payload, **kwargs)

    def _sendNotification(self, payload, **kwargs):
        status = []
        event = kwargs["event"]
        kwargs["event"] = (
            telegramMsgDict[event]["bind_msg"]
            if "bind_msg" in telegramMsgDict[event]
            else event
        )
        kwargs["with_image"] = self.main._settings["messages"][str(kwargs["event"])][
            "image"
        ]
        print(f"Printer Status{str(status)}")
        # define locals for string formatting
        z = self.z
        temps = []
        print(f"TEMPS - {str(temps)}")
        bed_temp = 0.0
        bed_target = 0.0
        e1_temp = 0.0
        e1_target = 0.0
        e2_temp = 0.0
        e2_target = 0.0
        percent = 0
        time_done = 0
        time_left = 0
        file = ""
        if "file" in payload:
            file = payload["file"]
        if "gcode" in payload:
            file = payload["gcode"]
        if "filename" in payload:
            file = payload["filename"]
        emo = EmojiFormatter(self.main)
        try:
            # call format with emo class object to handle emojis, otherwise use locals
            message = self.main._settings["messages"][kwargs["event"]]["text"].format(
                emo, **locals()
            )
        except Exception as ex:
            print(f"Exception on formatting message: {str(ex)}")
            message = (
                self.main.gEmo("warning")
                + " ERROR: I was not able to format the Notification for '"
                + event
                + "' properly. Please open your OctoPrint settings for  and check message settings for '"
                + event
                + "'."
            )
        print(f"Sending Notification: {message}")
        # Do we want to send with Markup?
        kwargs["markup"] = self.main._settings["messages"][kwargs["event"]]["markup"]
        # finally send MSG
        self.main.send_msg(message, **kwargs)

    # Helper to determine if notification will be send on gcode ZChange event
    # depends on notification time and notification height
    def is_notification_necessary(self, new_z, old_z):
        timediff = self.main._settings["notification_time"]
        if timediff and timediff > 0:
            # check the timediff
            if self.last_notification_time + timediff * 60 <= time.time():
                self.last_notification_time = time.time()
                return True
        zdiff = self.main._settings["notification_height"]
        if zdiff and zdiff > 0.0:
            if old_z is None:
                return False
            # check the zdiff
            if abs(new_z - (old_z or 0.0)) >= 1.0:
                # big changes in height are not interesting for notifications - we ignore them
                self.last_z = new_z
                return False
            if new_z >= self.last_z + zdiff or new_z < self.last_z:
                self.last_z = new_z
                return True
        return False
