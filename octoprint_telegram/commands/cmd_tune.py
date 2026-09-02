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


class TuneTemperatureMenuState(MenuState):
    """The temperature being edited."""

    def __init__(self, temperature: float) -> None:
        """Set up the temperature being edited.

        Args:
            temperature (float): The temperature, in degrees Celsius.
        """
        self.temperature = temperature


class CmdTune(BaseCommand):
    TEMP_INCREMENTS: ClassVar[list[int]] = [100, 50, 10, 5, 1]
    RATE_INCREMENTS: ClassVar[list[int]] = [25, 10, 1]
    ENCLOSURE_INCREMENTS: ClassVar[list[int]] = [20, 10, 5, 1]

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Adjust feed rate, flow rate and temperatures.

        Possible callback queries, where {n} stands for the number of a tool, {id} for the index of an
        enclosure output and {step} for one of the increments offered by the menu:

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
        - /tune_tool_{n} -> show the temperature of that tool
        - /tune_tool_{n}_+{step} -> raise the temperature being edited for that tool
        - /tune_tool_{n}_-{step} -> lower the temperature being edited for that tool
        - /tune_tool_{n}_set -> send the temperature being edited to that tool
        - /tune_tool_{n}_off -> switch that tool off
        - /tune_bed -> show the temperature of the bed
        - /tune_bed_+{step} -> raise the temperature being edited for the bed
        - /tune_bed_-{step} -> lower the temperature being edited for the bed
        - /tune_bed_set -> send the temperature being edited to the bed
        - /tune_bed_off -> switch the bed off
        - /tune_enclosure_{id} -> show the temperature of that enclosure output
        - /tune_enclosure_{id}_+{step} -> raise the temperature being edited for that enclosure output
        - /tune_enclosure_{id}_-{step} -> lower the temperature being edited for that enclosure output
        - /tune_enclosure_{id}_set -> send the temperature being edited to that enclosure output
        - /tune_enclosure_{id}_off -> switch that enclosure output off
        """
        if command_context.parameter and command_context.parameter != "back":
            params = command_context.parameter.split("_")

            if params[0] == "feedrate":
                self._handle_rate_control(command_context, "feedrate", self.plugin_context.printer.feed_rate)

            elif params[0] == "flowrate":
                self._handle_rate_control(command_context, "flowrate", self.plugin_context.printer.flow_rate)

            elif params[0] == "tool":
                tool_number = int(params[1])
                tool_key = f"tool{tool_number}"
                self._handle_temp_control(command_context, tool_key, f"tool {tool_number}", "tool", f"tool_{params[1]}")

            elif params[0] == "bed":
                tool_key = "bed"
                self._handle_temp_control(command_context, tool_key, "bed", "hotbed", "bed")

            elif params[0] == "enclosure":
                self._handle_enclosure_control(command_context)
        else:
            msg = render_emojis("{emo:settings} <b>Tune print settings</b>")

            profile = self.plugin_context.printer_profiles.get_current()

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row(("{emo:feedrate} Feedrate", "feedrate"), ("{emo:flowrate} Flowrate", "flowrate"))

            if self.plugin_context.printer.is_operational():
                tool_buttons = []

                extruder = profile["extruder"]
                shared_nozzle = extruder.get("sharedNozzle", False)
                count = extruder.get("count", 1)

                if shared_nozzle:
                    tool_buttons.append(("{emo:tool} Tool", "tool_0"))
                else:
                    tool_buttons.extend([(f"{{emo:tool}} Tool {i}", f"tool_{i}") for i in range(count)])

                if profile["heatedBed"]:
                    tool_buttons.append(("{emo:hotbed} Bed", "bed"))

                if tool_buttons:
                    keyboard.add_row(*tool_buttons)

            try:
                enclosure_plugin_id = "enclosure"
                enclosure_available = self.plugin_context.plugins.is_enabled(enclosure_plugin_id)
                if enclosure_available:
                    enclosure_implementation = self.plugin_context.plugins.implementation(enclosure_plugin_id)

                    enclosure_buttons = []
                    for rpi_output in enclosure_implementation.rpi_outputs:
                        if rpi_output["output_type"] == "temp_hum_control":
                            index_id = rpi_output["index_id"]
                            label = rpi_output["label"]
                            enclosure_buttons.append((f"{{emo:plugin}} {label}", f"enclosure_{index_id}"))

                    if enclosure_buttons:
                        keyboard.add_row(*enclosure_buttons)
            except Exception:
                self._logger.exception("Caught an exception getting enclosure data")

            keyboard.add_row(CLOSE_BUTTON)

            self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

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

    def _create_temp_keyboard(self, tool_identifier: str, command_context: CommandContext) -> Keyboard:
        """Create increment/decrement buttons for temperature controls."""
        keyboard = Keyboard(command_context.cmd)

        keyboard.add_row(*((f"+{inc}", f"{tool_identifier}_+{inc}") for inc in self.TEMP_INCREMENTS))
        keyboard.add_row(*((f"-{inc}", f"{tool_identifier}_-{inc}") for inc in self.TEMP_INCREMENTS))

        keyboard.add_row(
            ("{emo:check} Set", f"{tool_identifier}_set"),
            ("{emo:cooldown} Off", f"{tool_identifier}_off"),
            (BACK_LABEL, "back"),
        )

        return keyboard

    def _handle_enclosure_control(self, command_context: CommandContext) -> None:
        """Handle enclosure temperature controls."""
        params = command_context.parameter.split("_")
        index_id = int(params[1])

        enclosure_plugin_id = "enclosure"
        enclosure_available = self.plugin_context.plugins.is_enabled(enclosure_plugin_id)

        if not enclosure_available:
            self.send_answer(
                command_context,
                render_emojis("{emo:attention} Enclosure plugin not available"),
                None,
                markup=Markup.HTML,
            )
            return

        enclosure_implementation = self.plugin_context.plugins.implementation(enclosure_plugin_id)

        selected_rpi_output = None
        for rpi_output in enclosure_implementation.rpi_outputs:
            if rpi_output["output_type"] == "temp_hum_control" and rpi_output["index_id"] == index_id:
                selected_rpi_output = rpi_output
                break

        if not selected_rpi_output:
            self.send_answer(
                command_context,
                render_emojis("{emo:attention} Enclosure plugin output not found"),
                None,
                markup=Markup.HTML,
            )
            return

        if len(params) <= 2:
            menu_state = TuneTemperatureMenuState(selected_rpi_output["temp_ctr_set_value"])
        else:
            menu_state = self.require_menu_state(command_context, TuneTemperatureMenuState)
            delta_str = params[2]

            if delta_str.startswith(("+", "-")):
                menu_state.temperature = max(menu_state.temperature + int(delta_str), 0)
            elif delta_str == "set":
                selected_rpi_output["temp_ctr_set_value"] = menu_state.temperature
                enclosure_implementation.handle_temp_hum_control()
            else:
                menu_state.temperature = 0
                selected_rpi_output["temp_ctr_set_value"] = 0
                enclosure_implementation.handle_temp_hum_control()

        current_target = selected_rpi_output["temp_ctr_set_value"]

        linked_temp_sensor = selected_rpi_output["linked_temp_sensor"]
        current_sensor = None
        for rpi_input in enclosure_implementation.rpi_inputs:
            if rpi_input["input_type"] == "temperature_sensor" and rpi_input["index_id"] == linked_temp_sensor:
                current_sensor = rpi_input["temp_sensor_temp"]
                break

        msg = render_emojis(
            f"{{emo:plugin}} Set temperature for <code>{html.escape(selected_rpi_output['label'])}</code>.\n"
            + (f"Sensor reading: {current_sensor}°C\n" if current_sensor is not None else "")
            + f"Current target: {current_target}°C\n"
            + f"Pending selection: <b>{menu_state.temperature}°C</b>"
        )

        keyboard = Keyboard(command_context.cmd)

        keyboard.add_row(*((f"+{inc}", f"enclosure_{params[1]}_+{inc}") for inc in self.ENCLOSURE_INCREMENTS))
        keyboard.add_row(*((f"-{inc}", f"enclosure_{params[1]}_-{inc}") for inc in self.ENCLOSURE_INCREMENTS))

        keyboard.add_row(
            ("{emo:check} Set", f"enclosure_{params[1]}_set"),
            ("{emo:cooldown} Off", f"enclosure_{params[1]}_off"),
            (BACK_LABEL, "back"),
        )

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _handle_rate_control(
        self, command_context: CommandContext, rate_name: str, apply_rate: Callable[[int], None]
    ) -> None:
        """Handle feedrate and flowrate controls.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            rate_name (str): Either "feedrate" or "flowrate".
            apply_rate (Callable): Callback that sends the rate to the printer.
        """
        params = command_context.parameter.split("_")

        if len(params) > 1:
            menu_state = self.require_menu_state(command_context, TuneRateMenuState)
            delta_str = params[1]

            if delta_str.startswith(("+", "-")):
                menu_state.rate = max(50, min(menu_state.rate + int(delta_str), 200))
            else:
                apply_rate(menu_state.rate)
                self._go_back(command_context)
                return
        else:
            menu_state = TuneRateMenuState(100)

        msg = render_emojis(f"{{emo:{rate_name}}} Set {rate_name}.\nSelection: <b>{menu_state.rate}%</b>")

        keyboard = self._create_rate_keyboard(rate_name, command_context)

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _handle_temp_control(
        self,
        command_context: CommandContext,
        tool_key: str,
        tool_display_name: str,
        emoji_name: str,
        tool_identifier: str,
    ) -> None:
        """Handle temperature controls."""
        params = command_context.parameter.split("_")
        temps = self.plugin_context.printer.get_current_temperatures()

        if len(params) <= len(tool_identifier.split("_")):
            menu_state = TuneTemperatureMenuState(temps[tool_key]["target"])
        else:
            menu_state = self.require_menu_state(command_context, TuneTemperatureMenuState)
            delta_str = params[len(tool_identifier.split("_"))]

            if delta_str.startswith(("+", "-")):
                menu_state.temperature = max(menu_state.temperature + int(delta_str), 0)
            elif delta_str == "set":
                self.plugin_context.printer.set_temperature(tool_key, menu_state.temperature)
                self._go_back(command_context)
                return
            else:
                self.plugin_context.printer.set_temperature(tool_key, 0)
                self._go_back(command_context)
                return

        current_temp = temps[tool_key]["actual"]

        msg = render_emojis(
            f"{{emo:{emoji_name}}} Set temperature for <code>{html.escape(tool_display_name)}</code>.\n"
            f"Current: {current_temp:.02f}/<b>{menu_state.temperature}°C</b>"
        )

        keyboard = self._create_temp_keyboard(tool_identifier, command_context)

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
