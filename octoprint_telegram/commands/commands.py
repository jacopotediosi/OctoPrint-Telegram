from .cmd_abort import CmdAbort
from .cmd_cancelobject import CmdCancelObject
from .cmd_close import CmdClose
from .cmd_con import CmdCon
from .cmd_ctrl import CmdCtrl
from .cmd_dontshutup import CmdDontShutup
from .cmd_filament import CmdFilament
from .cmd_files import CmdFiles
from .cmd_gcode import CmdGcode
from .cmd_gif import CmdGif
from .cmd_help import CmdHelp
from .cmd_home import CmdHome
from .cmd_photo import CmdPhoto
from .cmd_power import CmdPower
from .cmd_print import CmdPrint
from .cmd_settings import CmdSettings
from .cmd_shutup import CmdShutup
from .cmd_start import CmdStart
from .cmd_status import CmdStatus
from .cmd_supergif import CmdSuperGif
from .cmd_sys import CmdSys
from .cmd_togglepause import CmdTogglePause
from .cmd_tune import CmdTune
from .cmd_upload import CmdUpload
from .cmd_user import CmdUser


class Commands:
    def __init__(self, main):
        self.main = main

        cmd_abort = CmdAbort(main)
        cmd_cancelobject = CmdCancelObject(main)
        cmd_close = CmdClose(main)
        cmd_con = CmdCon(main)
        cmd_ctrl = CmdCtrl(main)
        cmd_dontshutup = CmdDontShutup(main)
        cmd_filament = CmdFilament(main)
        cmd_files = CmdFiles(main)
        cmd_gcode = CmdGcode(main)
        cmd_gif = CmdGif(main)
        cmd_help = CmdHelp(main)
        cmd_home = CmdHome(main)
        cmd_photo = CmdPhoto(main)
        cmd_power = CmdPower(main)
        cmd_print = CmdPrint(main)
        cmd_settings = CmdSettings(main)
        cmd_shutup = CmdShutup(main)
        cmd_start = CmdStart(main)
        cmd_status = CmdStatus(main)
        cmd_supergif = CmdSuperGif(main)
        cmd_sys = CmdSys(main)
        cmd_togglepause = CmdTogglePause(main)
        cmd_tune = CmdTune(main)
        cmd_upload = CmdUpload(main)
        cmd_user = CmdUser(main)

        # commands_dict contains the command settings.
        # Each entry has the following structure:
        #
        #   <commandName>: {fields}
        #
        # - commandName (str):
        #     The command name, usually starts with /.
        #
        # Fields:
        #
        # - 'cmd' (class):
        #     The command class. The functional part must be in its execute() method.
        #
        # - 'desc' (str):
        #     Human-readable description shown in settings/help.
        #
        # - 'param' (bool, optional):
        #     Whether the command accepts parameters (separated from the command by _),
        #     for example if it uses inline buttons that make use of them. Defaults to False.
        #
        # - 'bind_none' (bool, optional):
        #     If True, the command is unprivileged and everyone can use it (e.g. /start, /help).
        #
        # IMPORTANT:
        # Each time you add/remove a command or notification, please remember to increment the
        # settings version number in `get_settings_version`.

        self.commands_dict = {
            "/status": {"cmd": cmd_status, "desc": "Show current status"},
            "/togglepause": {
                "cmd": cmd_togglepause,
                "desc": "Pause or resume the current print",
            },
            "/home": {
                "cmd": cmd_home,
                "desc": "Home the printer's print head",
            },
            "/files": {
                "cmd": cmd_files,
                "param": True,
                "desc": "List and manage print files",
            },
            "/print": {
                "cmd": cmd_print,
                "param": True,
                "desc": "Print the loaded file (confirmation required) or browse files",
            },
            "/tune": {
                "cmd": cmd_tune,
                "param": True,
                "desc": "Adjust feed rate, flow, and temperatures",
            },
            "/ctrl": {
                "cmd": cmd_ctrl,
                "param": True,
                "desc": "Trigger custom OctoPrint controls",
            },
            "/con": {
                "cmd": cmd_con,
                "param": True,
                "desc": "Connect or disconnect the printer",
            },
            "/sys": {
                "cmd": cmd_sys,
                "param": True,
                "desc": "Run OctoPrint system commands",
            },
            "/abort": {
                "cmd": cmd_abort,
                "param": True,
                "desc": "Abort current print (confirmation required)",
            },
            "/cancelobject": {
                "cmd": cmd_cancelobject,
                "param": True,
                "desc": "Cancel an object (Cancelobject plugin required)",
            },
            "/power": {"cmd": cmd_power, "param": True, "desc": "Monitor and control power switches"},
            "/settings": {"cmd": cmd_settings, "param": True, "desc": "Show and change notification settings"},
            "/upload": {"cmd": cmd_upload, "desc": "Upload a file to OctoPrint library"},
            "/filament": {"cmd": cmd_filament, "param": True, "desc": "Manage filament spools"},
            "/user": {"cmd": cmd_user, "desc": "Get information about chat, user and permissions"},
            "/gcode": {
                "cmd": cmd_gcode,
                "param": True,
                "desc": "Send G-code commands to the printer (use like /gcode_XXX)",
            },
            "/gif": {
                "cmd": cmd_gif,
                "desc": "Show GIFs from the webcams",
            },
            "/supergif": {
                "cmd": cmd_supergif,
                "desc": "Show longer GIFs from the webcams",
            },
            "/photo": {
                "cmd": cmd_photo,
                "desc": "Show photos from the webcams",
            },
            "/shutup": {
                "cmd": cmd_shutup,
                "desc": "Disable automatic notifications until the print ends",
            },
            "/dontshutup": {
                "cmd": cmd_dontshutup,
                "desc": "Make the bot talk again (opposite of /shutup)",
            },
            "/help": {"cmd": cmd_help, "bind_none": True, "desc": "Show available commands"},
            "/start": {"cmd": cmd_start, "bind_none": True, "desc": "Start the bot"},
            "close": {"cmd": cmd_close, "bind_none": True, "desc": "Cancel action"},
        }

    def run_command(self, command, chat_id, from_id, parameter, msg_id_to_update, user):
        """
        Run a command by its textual name.

        Raises:
            KeyError: If the command doesn't exist.
            Exception: Any exception raised by the command's execute method.
        """
        return self.commands_dict[command]["cmd"](command, chat_id, from_id, parameter, msg_id_to_update, user)
