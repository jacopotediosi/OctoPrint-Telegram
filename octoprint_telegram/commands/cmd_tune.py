from __future__ import annotations

import html
from dataclasses import replace
from typing import Callable, ClassVar

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class TuneRateMenuState(MenuState):
    """The feed rate or flow rate being edited."""

    def __init__(self, rate: int) -> None:
        """Set up the rate being edited.

        Args:
            rate (int): The rate, as a percentage.
        """
        self.rate = rate


class TuneHeaterChoiceMenuState(MenuState):
    """The heaters offered in the menu."""

    def __init__(self, heaters: list[tuple[str, str | int, str]]) -> None:
        """Set up the heaters offered in the menu.

        Args:
            heaters (list[tuple[str, str | int, str]]): The kind of each heater, either "tool", "bed" or
                "enclosure", then its identifier and the name it is shown under, in the order they are offered.
        """
        self.heaters = heaters


class TuneHeaterTemperatureMenuState(MenuState):
    """The temperature being edited and the heater it applies to."""

    def __init__(self, temperature: float, heater: tuple[str, str | int, str]) -> None:
        """Set up the temperature being edited and the heater it applies to.

        Args:
            temperature (float): The temperature, in degrees Celsius.
            heater (tuple[str, str | int, str]): The kind of the heater, either "tool", "bed" or "enclosure",
                then its identifier and the name it is shown under.
        """
        self.temperature = temperature
        self.heater = heater


class CmdTune(BaseCommand):
    TEMP_INCREMENTS: ClassVar[list[int]] = [100, 50, 10, 5, 1]
    RATE_INCREMENTS: ClassVar[list[int]] = [25, 10, 1]
    ENCLOSURE_INCREMENTS: ClassVar[list[int]] = [20, 10, 5, 1]

    HEATER_EMOJI_NAMES: ClassVar[dict[str, str]] = {"tool": "tool", "bed": "hotbed", "enclosure": "plugin"}

    ENCLOSURE_PLUGIN_ID = "enclosure"

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Adjust feed rate, flow rate and temperatures.

        Possible callback queries, where {position} stands for the position of a heater in the list and
        {step} for one of the increments offered by the menu:

        - /tune -> show what can be tuned
        - /tune_back -> go back to what can be tuned
        - /tune_feedrate -> show the feed rate being edited
        - /tune_feedrate_+{step} -> raise the feed rate being edited
        - /tune_feedrate_-{step} -> lower the feed rate being edited
        - /tune_feedrate_set -> send the feed rate being edited to the printer
        - /tune_flowrate -> show the flow rate being edited
        - /tune_flowrate_+{step} -> raise the flow rate being edited
        - /tune_flowrate_-{step} -> lower the flow rate being edited
        - /tune_flowrate_set -> send the flow rate being edited to the printer
        - /tune_heater_{position} -> show the temperature of the heater at that position
        - /tune_temp_+{step} -> raise the temperature being edited
        - /tune_temp_-{step} -> lower the temperature being edited
        - /tune_temp_set -> send the temperature being edited to the heater
        - /tune_temp_off -> switch the heater off
        """
        if command_context.parameter and command_context.parameter != "back":
            action, _, argument = command_context.parameter.partition("_")

            if action == "feedrate":
                self._handle_rate_control(command_context, "feedrate", argument, self.plugin_context.printer.feed_rate)

            elif action == "flowrate":
                self._handle_rate_control(command_context, "flowrate", argument, self.plugin_context.printer.flow_rate)

            elif action == "heater":
                menu_state = self.require_menu_state(command_context, TuneHeaterChoiceMenuState)
                heater = self.require_menu_chosen_item(menu_state.heaters, argument)
                self._handle_temperature_control(command_context, heater, "")

            elif action == "temp":
                menu_state = self.require_menu_state(command_context, TuneHeaterTemperatureMenuState)
                self._handle_temperature_control(command_context, menu_state.heater, argument, menu_state)
        else:
            msg = render_emojis("{emo:settings} <b>Tune print settings</b>")

            profile = self.plugin_context.printer_profiles.get_current()

            heaters: list[tuple[str, str | int, str]] = []

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row(("{emo:feedrate} Feedrate", "feedrate"), ("{emo:flowrate} Flowrate", "flowrate"))

            if self.plugin_context.printer.is_operational():
                tool_buttons = []

                extruder = profile["extruder"]
                shared_nozzle = extruder.get("sharedNozzle", False)
                count = extruder.get("count", 1)

                for tool_number in [0] if shared_nozzle else range(count):
                    heaters.append(("tool", f"tool{tool_number}", f"tool {tool_number}"))
                    tool_label = "{emo:tool} Tool" if shared_nozzle else f"{{emo:tool}} Tool {tool_number}"
                    tool_buttons.append((tool_label, f"heater_{len(heaters) - 1}"))

                if profile["heatedBed"]:
                    heaters.append(("bed", "bed", "bed"))
                    tool_buttons.append(("{emo:hotbed} Bed", f"heater_{len(heaters) - 1}"))

                if tool_buttons:
                    keyboard.add_row(*tool_buttons)

            try:
                if self.plugin_context.plugins.is_enabled(self.ENCLOSURE_PLUGIN_ID):
                    enclosure_implementation = self.plugin_context.plugins.implementation(self.ENCLOSURE_PLUGIN_ID)

                    enclosure_buttons = []
                    for rpi_output in enclosure_implementation.rpi_outputs:
                        if rpi_output["output_type"] == "temp_hum_control":
                            label = rpi_output["label"]
                            heaters.append(("enclosure", rpi_output["index_id"], label))
                            enclosure_buttons.append((f"{{emo:plugin}} {label}", f"heater_{len(heaters) - 1}"))

                    if enclosure_buttons:
                        keyboard.add_row(*enclosure_buttons)
            except Exception:
                self._logger.exception("Caught an exception getting enclosure data")

            keyboard.add_row(CLOSE_BUTTON)

            self.send_answer(
                command_context, msg, TuneHeaterChoiceMenuState(heaters), markup=Markup.HTML, keyboard=keyboard
            )

    def _go_back(self, command_context: CommandContext) -> None:
        """Handle back navigation."""
        self.execute(replace(command_context, parameter="back"))

    def _create_rate_keyboard(self, rate_name: str, command_context: CommandContext) -> Keyboard:
        """Create increment/decrement buttons for rate controls (feed/flow)."""
        keyboard = Keyboard(command_context.cmd)

        increment_row = []
        for inc in self.RATE_INCREMENTS:
            increment_row.extend([(f"+{inc}", f"{rate_name}_+{inc}"), (f"-{inc}", f"{rate_name}_-{inc}")])
        keyboard.add_row(*increment_row)

        keyboard.add_row(("{emo:check} Set", f"{rate_name}_set"), (BACK_LABEL, "back"))

        return keyboard

    def _create_temp_keyboard(self, increments: list[int], command_context: CommandContext) -> Keyboard:
        """Create increment/decrement buttons for temperature controls."""
        keyboard = Keyboard(command_context.cmd)

        keyboard.add_row(*((f"+{inc}", f"temp_+{inc}") for inc in increments))
        keyboard.add_row(*((f"-{inc}", f"temp_-{inc}") for inc in increments))

        keyboard.add_row(
            ("{emo:check} Set", "temp_set"),
            ("{emo:cooldown} Off", "temp_off"),
            (BACK_LABEL, "back"),
        )

        return keyboard

    def _get_enclosure_output(self, index_id: str | int) -> dict | None:
        """Return an output of the Enclosure plugin, or None when the plugin no longer offers it.

        Args:
            index_id (str | int): The identifier the Enclosure plugin gave the output.

        Returns:
            dict | None: The output as the Enclosure plugin holds it.
        """
        if not self.plugin_context.plugins.is_enabled(self.ENCLOSURE_PLUGIN_ID):
            return None

        enclosure_implementation = self.plugin_context.plugins.implementation(self.ENCLOSURE_PLUGIN_ID)
        for rpi_output in enclosure_implementation.rpi_outputs:
            if rpi_output["output_type"] == "temp_hum_control" and rpi_output["index_id"] == index_id:
                return rpi_output
        return None

    def _get_enclosure_sensor_reading(self, rpi_output: dict) -> float | None:
        """Return the temperature read by the sensor linked to an output of the Enclosure plugin.

        Args:
            rpi_output (dict): The output as the Enclosure plugin holds it.

        Returns:
            float | None: The temperature, or None when no linked sensor reports one.
        """
        enclosure_implementation = self.plugin_context.plugins.implementation(self.ENCLOSURE_PLUGIN_ID)

        linked_temp_sensor = rpi_output["linked_temp_sensor"]
        for rpi_input in enclosure_implementation.rpi_inputs:
            if rpi_input["input_type"] == "temperature_sensor" and rpi_input["index_id"] == linked_temp_sensor:
                return rpi_input["temp_sensor_temp"]
        return None

    def _handle_temperature_control(
        self,
        command_context: CommandContext,
        heater: tuple[str, str | int, str],
        step: str,
        menu_state: TuneHeaterTemperatureMenuState | None = None,
    ) -> None:
        """Show the temperature of a heater, and change it when a step is given.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            heater (tuple[str, str | int, str]): The heater being edited, as the menu offers it.
            step (str): The increment to apply, "set", "off", or empty to only show the temperature.
            menu_state (TuneHeaterTemperatureMenuState, optional): The state the step applies to, or None when
                the heater has just been picked.
        """
        heater_kind, heater_identifier, heater_name = heater

        if heater_kind == "enclosure":
            self._handle_enclosure_temperature_control(command_context, heater, step, menu_state)
            return

        heater_temps = self.plugin_context.printer.get_current_temperatures().get(heater_identifier) or {}
        current_temp = heater_temps.get("actual")
        target_temp = heater_temps.get("target")

        if not isinstance(current_temp, (int, float)) or not isinstance(target_temp, (int, float)):
            self.send_answer(
                command_context,
                render_emojis(
                    f"{{emo:attention}} The printer reports no temperature for <code>{html.escape(heater_name)}</code>."
                ),
                None,
                markup=Markup.HTML,
            )
            return

        if menu_state is None:
            menu_state = TuneHeaterTemperatureMenuState(target_temp, heater)
        elif step.startswith(("+", "-")):
            menu_state.temperature = max(menu_state.temperature + int(step), 0)
        elif step == "set":
            self.plugin_context.printer.set_temperature(heater_identifier, menu_state.temperature)
            self._go_back(command_context)
            return
        elif step == "off":
            self.plugin_context.printer.set_temperature(heater_identifier, 0)
            self._go_back(command_context)
            return

        msg = render_emojis(
            f"{{emo:{self.HEATER_EMOJI_NAMES[heater_kind]}}} Set temperature for "
            f"<code>{html.escape(heater_name)}</code>.\n"
            f"Current: {current_temp:.02f}/<b>{menu_state.temperature}°C</b>"
        )

        keyboard = self._create_temp_keyboard(self.TEMP_INCREMENTS, command_context)

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _handle_enclosure_temperature_control(
        self,
        command_context: CommandContext,
        heater: tuple[str, str | int, str],
        step: str,
        menu_state: TuneHeaterTemperatureMenuState | None,
    ) -> None:
        """Show the temperature of an output of the Enclosure plugin, and change it when a step is given.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            heater (tuple[str, str | int, str]): The heater being edited, as the menu offers it.
            step (str): The increment to apply, "set", "off", or empty to only show the temperature.
            menu_state (TuneHeaterTemperatureMenuState | None): The state the step applies to, or None when the
                heater has just been picked.
        """
        _, index_id, heater_name = heater

        selected_rpi_output = self._get_enclosure_output(index_id)
        if selected_rpi_output is None:
            self.send_answer(
                command_context,
                render_emojis("{emo:attention} Enclosure plugin output not found"),
                None,
                markup=Markup.HTML,
            )
            return

        enclosure_implementation = self.plugin_context.plugins.implementation(self.ENCLOSURE_PLUGIN_ID)

        if menu_state is None:
            menu_state = TuneHeaterTemperatureMenuState(selected_rpi_output["temp_ctr_set_value"], heater)
        elif step.startswith(("+", "-")):
            menu_state.temperature = max(menu_state.temperature + int(step), 0)
        elif step == "set":
            selected_rpi_output["temp_ctr_set_value"] = menu_state.temperature
            enclosure_implementation.handle_temp_hum_control()
        elif step == "off":
            menu_state.temperature = 0
            selected_rpi_output["temp_ctr_set_value"] = 0
            enclosure_implementation.handle_temp_hum_control()

        current_target = selected_rpi_output["temp_ctr_set_value"]
        current_sensor = self._get_enclosure_sensor_reading(selected_rpi_output)

        msg = render_emojis(
            f"{{emo:plugin}} Set temperature for <code>{html.escape(heater_name)}</code>.\n"
            + (f"Sensor reading: {current_sensor}°C\n" if current_sensor is not None else "")
            + f"Current target: {current_target}°C\n"
            + f"Pending selection: <b>{menu_state.temperature}°C</b>"
        )

        keyboard = self._create_temp_keyboard(self.ENCLOSURE_INCREMENTS, command_context)

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _handle_rate_control(
        self, command_context: CommandContext, rate_name: str, step: str, apply_rate: Callable[[int], None]
    ) -> None:
        """Handle feedrate and flowrate controls.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            rate_name (str): Either "feedrate" or "flowrate".
            step (str): The increment to apply, or empty to only show the rate.
            apply_rate (Callable): Callback that sends the rate to the printer.
        """
        if step:
            menu_state = self.require_menu_state(command_context, TuneRateMenuState)

            if step.startswith(("+", "-")):
                menu_state.rate = max(50, min(menu_state.rate + int(step), 200))
            elif step == "set":
                apply_rate(menu_state.rate)
                self._go_back(command_context)
                return
        else:
            menu_state = TuneRateMenuState(100)

        msg = render_emojis(f"{{emo:{rate_name}}} Set {rate_name}.\nSelection: <b>{menu_state.rate}%</b>")

        keyboard = self._create_rate_keyboard(rate_name, command_context)

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
