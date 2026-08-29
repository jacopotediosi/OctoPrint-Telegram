from octoprint.util.version import is_octoprint_compatible

from .plugin import TelegramPlugin


# Check that we are running on OctoPrint >= 1.4.0, which introduced the granular permissions system
def _get_plugin_implementation() -> TelegramPlugin:
    if not is_octoprint_compatible(">=1.4.0"):
        raise Exception("OctoPrint 1.4.0 or greater required.")

    return TelegramPlugin()


__plugin_name__ = "Telegram"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_privacypolicy__ = "https://github.com/jacopotediosi/OctoPrint-Telegram/blob/master/PRIVACY.md"
__plugin_implementation__ = _get_plugin_implementation()
__plugin_hooks__ = {
    "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
    "octoprint.server.http.routes": __plugin_implementation__.route_hook,
    "octoprint.comm.protocol.gcode.received": __plugin_implementation__.hook_gcode_received,
    "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.hook_gcode_sent,
    "octoprint.events.register_custom_events": __plugin_implementation__.register_custom_events,
}
