from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from octoprint.util import get_formatted_timedelta

from ..utils import Formatters
from .registry import NOTIFICATION_DEFINITIONS

if TYPE_CHECKING:
    from octoprint.filemanager import FileManager
    from octoprint.printer import PrinterInterface

    from ..core.settings import Settings
    from ..integrations.display_layer_progress import DisplayLayerProgress
    from ..integrations.octoprint_api import OctoPrintApi
    from ..integrations.plugins import Plugins


T = TypeVar("T")


class cached_property(Generic[T]):
    """Decorator that declares a template variable, using the attribute name as cache key.

    The cache prevents calculating the same template variable multiple times
    within a single notification message. The cache is local to each
    notification and does not persist between different notifications.
    """

    def __init__(self, function: Callable[[NotificationVariables], T]) -> None:
        """Set up the decorator.

        Args:
            function (Callable): Callback that returns the value of the template variable.
        """
        self._function = function
        self._name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        """Take the name the template variable is declared under.

        Args:
            owner (type): The class the variable is declared on.
            name (str): The attribute name the variable is declared under.
        """
        self._name = name

    def __get__(self, instance: NotificationVariables, owner: type) -> T:
        """Read the template variable.

        Args:
            instance (NotificationVariables): The variables the value is calculated from.
            owner (type): The class the variable is declared on.

        Returns:
            T: The value of the template variable.
        """
        if self._name not in instance._cache:
            instance._cache[self._name] = self._function(instance)
        return instance._cache[self._name]


class NotificationVariables:
    """Defines all template variables available for notification messages.

    Variables are calculated only when accessed.
    To add new template variables, just add them as a @cached_property.
    """

    def __init__(
        self,
        event: str,
        payload: dict,
        current_z: float,
        printer: PrinterInterface,
        file_manager: FileManager,
        plugins: Plugins,
        api: OctoPrintApi,
        display_layer_progress: DisplayLayerProgress,
        settings: Settings,
    ) -> None:
        """Set up the template variables of a single notification.

        Args:
            event (str): The event that triggered the notification.
            payload (dict): The payload the event carried.
            current_z (float): The Z value the print head is at.
            printer (PrinterInterface): The printer.
            file_manager (FileManager): The OctoPrint file manager.
            plugins (Plugins): The OctoPrint plugins installed.
            api (OctoPrintApi): The OctoPrint HTTP API.
            display_layer_progress (DisplayLayerProgress): The DisplayLayerProgress readings.
            settings (Settings): The plugin settings.
        """
        self._event = event
        self._payload = payload
        self._current_z = current_z
        self._printer = printer
        self._file_manager = file_manager
        self._plugins = plugins
        self._api = api
        self._display_layer_progress = display_layer_progress
        self._settings = settings

        self._cache = {}

    def accessed_names(self) -> list:
        """The names of the variables read so far."""
        return list(self._cache)

    @cached_property
    def status(self) -> dict:
        """Current printer data from OctoPrint API."""
        return self._printer.get_current_data()

    @cached_property
    def event(self) -> str:
        """Event that triggered the notification. If the event has an alias (bind_message), it resolves to that."""
        event = str(self._event)
        definition = NOTIFICATION_DEFINITIONS.get(event)
        return definition.bind_message if definition and definition.bind_message else event

    @cached_property
    def z(self) -> float:
        """Current Z value."""
        return self._current_z

    @cached_property
    def temps(self) -> dict:
        """Full temperature data for all tools and bed from OctoPrint API."""
        return self._printer.get_current_temperatures()

    @cached_property
    def bed_temp(self) -> float:
        """Current bed temperature."""
        return self.temps.get("bed", {}).get("actual", 0.0)

    @cached_property
    def bed_target(self) -> float:
        """Target bed temperature."""
        return self.temps.get("bed", {}).get("target", 0.0)

    @cached_property
    def e1_temp(self) -> float:
        """Current temperature of extruder 1 (tool0)."""
        return self.temps.get("tool0", {}).get("actual", 0.0)

    @cached_property
    def e1_target(self) -> float:
        """Target temperature of extruder 1 (tool0)."""
        return self.temps.get("tool0", {}).get("target", 0.0)

    @cached_property
    def e2_temp(self) -> float:
        """Current temperature of extruder 2 (tool1)."""
        return self.temps.get("tool1", {}).get("actual", 0.0)

    @cached_property
    def e2_target(self) -> float:
        """Target temperature of extruder 2 (tool1)."""
        return self.temps.get("tool1", {}).get("target", 0.0)

    @cached_property
    def e3_temp(self) -> float:
        """Current temperature of extruder 3 (tool2)."""
        return self.temps.get("tool2", {}).get("actual", 0.0)

    @cached_property
    def e3_target(self) -> float:
        """Target temperature of extruder 3 (tool2)."""
        return self.temps.get("tool2", {}).get("target", 0.0)

    @cached_property
    def e4_temp(self) -> float:
        """Current temperature of extruder 4 (tool3)."""
        return self.temps.get("tool3", {}).get("actual", 0.0)

    @cached_property
    def e4_target(self) -> float:
        """Target temperature of extruder 4 (tool3)."""
        return self.temps.get("tool3", {}).get("target", 0.0)

    @cached_property
    def e5_temp(self) -> float:
        """Current temperature of extruder 5 (tool4)."""
        return self.temps.get("tool4", {}).get("actual", 0.0)

    @cached_property
    def e5_target(self) -> float:
        """Target temperature of extruder 5 (tool4)."""
        return self.temps.get("tool4", {}).get("target", 0.0)

    @cached_property
    def percent(self) -> int:
        """Current percentage of the print progress."""
        progress = self.status.get("progress", {})
        completion = progress.get("completion")
        return int(completion if completion is not None else 0)

    @cached_property
    def time_done(self) -> str:
        """Elapsed time of the current print."""
        progress = self.status.get("progress", {})
        print_time = progress.get("printTime") or 0
        return get_formatted_timedelta(datetime.timedelta(seconds=print_time))

    @cached_property
    def time_left(self) -> str:
        """Remaining time of the current print."""
        progress = self.status.get("progress", {})
        print_time_left = progress.get("printTimeLeft")
        if print_time_left is not None:
            return get_formatted_timedelta(datetime.timedelta(seconds=print_time_left))
        return "[Unknown]"

    @cached_property
    def time_finish(self) -> str | None:
        """Estimated finish time of the current print."""
        progress = self.status.get("progress", {})
        print_time_left = progress.get("printTimeLeft")
        if print_time_left is not None:
            return Formatters.format_eta(self._settings, print_time_left)

    @cached_property
    def display_layer_progress(self) -> dict:
        """A dictionary containing data provided by the DisplayLayerProgress plugin."""
        return self._display_layer_progress.get_layer_progress_values() or {}

    @cached_property
    def current_layer(self) -> object:
        """Current layer number, provided by the DisplayLayerProgress plugin."""
        layer_info = self.display_layer_progress.get("layer") or {}
        return layer_info.get("current", "?")

    @cached_property
    def total_layer(self) -> object:
        """Total number of layers, provided by the DisplayLayerProgress plugin."""
        layer_info = self.display_layer_progress.get("layer") or {}
        return layer_info.get("total", "?")

    @cached_property
    def total_height(self) -> object:
        """Total height of the object being printed, provided by the DisplayLayerProgress plugin."""
        height_info = self.display_layer_progress.get("height") or {}
        return height_info.get("totalFormatted", "?")

    @cached_property
    def fan_speed(self) -> object:
        """Fan speed, provided by the DisplayLayerProgress plugin."""
        return self.display_layer_progress.get("fanSpeed", "?")

    @cached_property
    def change_filament_count(self) -> object:
        """Number of filament changes occurred, provided by the DisplayLayerProgress plugin."""
        print_info = self.display_layer_progress.get("print") or {}
        return print_info.get("changeFilamentCount", "?")

    @cached_property
    def change_filament_time_left(self) -> object:
        """Remaining time until the next filament change, provided by the DisplayLayerProgress plugin."""
        print_info = self.display_layer_progress.get("print") or {}
        return print_info.get("changeFilamentTimeLeft", "?")

    @cached_property
    def change_filament_next_time(self) -> object:
        """Estimated time of the next filament change, provided by the DisplayLayerProgress plugin."""
        print_info = self.display_layer_progress.get("print") or {}
        return print_info.get("estimatedChangedFilamentTime", "?")

    @cached_property
    def owner(self) -> str:
        """The name of the user who started the print."""
        return self.status["job"].get("user") or ""

    @cached_property
    def user(self) -> str:
        """The name of the user who performed the action that triggered the notification (e.g., paused or canceled the print)."""
        return self._payload.get("user") or ""

    @cached_property
    def storage(self) -> str:
        """Storage the file currently being printed is stored in."""
        return self._payload.get("origin") or self.status.get("job", {}).get("file", {}).get("origin") or ""

    @cached_property
    def path(self) -> str:
        """Full path of the file currently being printed."""
        return self._payload.get("path") or self.status.get("job", {}).get("file", {}).get("path") or ""

    @cached_property
    def file(self) -> str:
        """File name of the file currently being printed."""
        file = self.status.get("job", {}).get("file", {}).get("name") or ""
        for key in ("filename", "gcode", "file"):
            value = self._payload.get(key)
            if value:
                file = value
                break
        return file

    @cached_property
    def metadata(self) -> dict:
        """A dictionary containing metadata of the file currently being printed."""
        if not self.path or self.storage not in self._file_manager.registered_storages:
            return {}
        return self._file_manager.get_metadata(self.storage, self.path) or {}

    @cached_property
    def error_msg(self) -> str:
        """The error message string. Only useful for 'Error' event notifications."""
        return self._payload.get("error", "")

    @cached_property
    def UserNotif_Text(self) -> str:
        """The text received via the serial message echo:UserNotif TEXT, which is triggered by printing a G-code like: M118 E1 UserNotif TEXT."""
        return self._payload.get("UserNotif", "")

    @cached_property
    def prusammu(self) -> dict:
        """A dictionary containing the current state of the Prusa MMU, provided by the Prusa MMU plugin."""
        return self._api.send_simpleapi_command("prusammu", "getmmu").json()

    @cached_property
    def resource_monitor(self) -> dict:
        """A dictionary containing data provided by the Resource Monitor plugin."""
        return self._api.send_request("/plugin/resource_monitor/stats").json()

    @cached_property
    def enclosure(self) -> dict:
        """A dictionary containing the data provided by the Enclosure plugin, such as the temperatures measured by the sensors or the configured target temperature."""
        enclosure = {"current_temps": {}, "humidity": {}, "target_temps": {}}
        enclosure_plugin_id = "enclosure"

        if self._plugins.is_enabled(enclosure_plugin_id):
            enclosure_implementation = self._plugins.implementation(enclosure_plugin_id)

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
