import html

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdTune(BaseCommand):
    TEMP_INCREMENTS = [100, 50, 10, 5, 1]
    RATE_INCREMENTS = [25, 10, 1]
    ENCLOSURE_INCREMENTS = [20, 10, 5, 1]

    temp_target_temps = dict()
    temp_tune_rates = dict(feedrate=100, flowrate=100)

    def execute(self, context: CommandContext):
        if context.parameter and context.parameter != "back":
            params = context.parameter.split("_")

            if params[0] == "feed":
                self._handle_rate_control(context, "feed", "feedrate", "feedrate")

            elif params[0] == "flow":
                self._handle_rate_control(context, "flow", "flowrate", "flowrate")

            elif params[0] == "e":
                tool_number = int(params[1])
                tool_key = f"tool{tool_number}"
                self._handle_temp_control(context, tool_key, f"tool {tool_number}", "tool", f"e_{params[1]}")

            elif params[0] == "b":
                tool_key = "bed"
                self._handle_temp_control(context, tool_key, "bed", "hotbed", "b")

            elif params[0] == "enc":
                self._handle_enclosure_control(context)
        else:
            msg = render_emojis("{emo:settings} <b>Tune print settings</b>")

            profile = self.main._printer_profile_manager.get_current()

            command_buttons = [
                [
                    [render_emojis("{emo:feedrate} Feedrate"), f"{context.cmd}_feed"],
                    [render_emojis("{emo:flowrate} Flowrate"), f"{context.cmd}_flow"],
                ]
            ]

            if self.main._printer.is_operational():
                tool_command_buttons = []

                extruder = profile["extruder"]
                shared_nozzle = extruder.get("sharedNozzle", False)
                count = extruder.get("count", 1)

                if shared_nozzle:
                    tool_command_buttons.append([render_emojis("{emo:tool} Tool"), f"{context.cmd}_e_0"])
                else:
                    tool_command_buttons.extend(
                        [[render_emojis(f"{{emo:tool}} Tool {i}"), f"{context.cmd}_e_{i}"] for i in range(count)]
                    )

                if profile["heatedBed"]:
                    tool_command_buttons.append([render_emojis("{emo:hotbed} Bed"), f"{context.cmd}_b"])

                if tool_command_buttons:
                    command_buttons.append(tool_command_buttons)

            try:
                enclosure_plugin_id = "enclosure"
                enclosure_module = self.main._plugin_manager.get_plugin(enclosure_plugin_id, True)
                if enclosure_module:
                    enclosure_implementation = self.main._plugin_manager.plugins[enclosure_plugin_id].implementation

                    enclosure_buttons = []
                    for rpi_output in enclosure_implementation.rpi_outputs:
                        if rpi_output["output_type"] == "temp_hum_control":
                            index_id = rpi_output["index_id"]
                            label = rpi_output["label"]
                            enclosure_buttons.append(
                                [render_emojis(f"{{emo:plugin}} {label}"), f"{context.cmd}_enc_{index_id}"]
                            )

                    if enclosure_buttons:
                        command_buttons.append(enclosure_buttons)
            except Exception:
                self._logger.exception("Caught an exception getting enclosure data")

            command_buttons.append([[render_emojis("{emo:cancel} Close"), "close"]])

            self.main.send_msg(
                msg,
                responses=command_buttons,
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )

    def _go_back(self, context):
        """Helper method to handle back navigation"""
        self(
            cmd=context.cmd,
            chat_id=context.chat_id,
            from_id=context.from_id,
            parameter="back",
            msg_id_to_update=context.msg_id_to_update,
            user=context.user,
        )

    def _create_rate_buttons(self, rate_type, context):
        """Create increment/decrement buttons for rate controls (feed/flow)"""
        buttons = []

        increment_row = []
        for inc in self.RATE_INCREMENTS:
            increment_row.extend(
                [[f"+{inc}", f"{context.cmd}_{rate_type}_+{inc}"], [f"-{inc}", f"{context.cmd}_{rate_type}_-{inc}"]]
            )
        buttons.append(increment_row)

        buttons.append(
            [
                [render_emojis("{emo:back} Back"), f"{context.cmd}_back"],
            ]
        )

        return buttons

    def _create_temp_buttons(self, tool_identifier, context):
        """Create increment/decrement buttons for temperature controls"""
        buttons = []

        increment_row = []
        decrement_row = []
        for inc in self.TEMP_INCREMENTS:
            increment_row.append([f"+{inc}", f"{context.cmd}_{tool_identifier}_+{inc}"])
            decrement_row.append([f"-{inc}", f"{context.cmd}_{tool_identifier}_-{inc}"])
        buttons.extend([increment_row, decrement_row])

        action_buttons = [[render_emojis("{emo:check} Set"), f"{context.cmd}_{tool_identifier}_s"]]
        action_buttons.append([render_emojis("{emo:cooldown} Off"), f"{context.cmd}_{tool_identifier}_off"])
        action_buttons.append([render_emojis("{emo:back} Back"), f"{context.cmd}_back"])
        buttons.append(action_buttons)

        return buttons

    def _handle_enclosure_control(self, context):
        """Handle enclosure temperature controls"""
        params = context.parameter.split("_")
        index_id = int(params[1])
        tool_key = f"enc{index_id}"

        enclosure_plugin_id = "enclosure"
        enclosure_module = self.main._plugin_manager.get_plugin(enclosure_plugin_id, True)

        if not enclosure_module:
            self.main.send_msg(
                render_emojis("{emo:attention} Enclosure plugin not available"),
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )
            return

        enclosure_implementation = self.main._plugin_manager.plugins[enclosure_plugin_id].implementation

        selected_rpi_output = None
        for rpi_output in enclosure_implementation.rpi_outputs:
            if rpi_output["output_type"] == "temp_hum_control" and rpi_output["index_id"] == index_id:
                selected_rpi_output = rpi_output
                break

        if not selected_rpi_output:
            self.main.send_msg(
                render_emojis("{emo:attention} Enclosure plugin output not found"),
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )
            return

        if len(params) <= 2:
            self.temp_target_temps[tool_key] = selected_rpi_output["temp_ctr_set_value"]
        else:
            delta_str = params[2]

            if delta_str.startswith(("+", "-")):
                self.temp_target_temps[tool_key] = max(self.temp_target_temps[tool_key] + int(delta_str), 0)
            elif delta_str.startswith("s"):
                selected_rpi_output["temp_ctr_set_value"] = self.temp_target_temps[tool_key]
                enclosure_implementation.handle_temp_hum_control()
            else:
                self.temp_target_temps[tool_key] = 0
                selected_rpi_output["temp_ctr_set_value"] = 0
                enclosure_implementation.handle_temp_hum_control()

        current_target = selected_rpi_output["temp_ctr_set_value"]
        pending_selection = self.temp_target_temps[tool_key]

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
            + f"Pending selection: <b>{pending_selection}°C</b>"
        )

        command_buttons = []

        increment_row = []
        decrement_row = []
        for inc in self.ENCLOSURE_INCREMENTS:
            increment_row.append([f"+{inc}", f"{context.cmd}_enc_{params[1]}_+{inc}"])
            decrement_row.append([f"-{inc}", f"{context.cmd}_enc_{params[1]}_-{inc}"])
        command_buttons.extend([increment_row, decrement_row])

        command_buttons.append(
            [
                [render_emojis("{emo:check} Set"), f"{context.cmd}_enc_{params[1]}_s"],
                [render_emojis("{emo:cooldown} Off"), f"{context.cmd}_enc_{params[1]}_off"],
                [render_emojis("{emo:back} Back"), f"{context.cmd}_back"],
            ]
        )

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def _handle_rate_control(self, context, rate_type, rate_key, emoji_name):
        """Handle feedrate and flowrate controls"""
        params = context.parameter.split("_")

        if len(params) > 1:
            delta_str = params[1]

            if delta_str.startswith(("+", "-")):
                self.temp_tune_rates[rate_key] = max(50, min(self.temp_tune_rates[rate_key] + int(delta_str), 200))
            else:
                getattr(self.main._printer, f"{rate_type}_rate")(int(self.temp_tune_rates[rate_key]))
                return self._go_back(context)

        msg = render_emojis(
            f"{{emo:{emoji_name}}} Set {rate_type}rate.\nCurrent: <b>{self.temp_tune_rates[rate_key]}%</b>"
        )

        command_buttons = self._create_rate_buttons(rate_type, context)

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def _handle_temp_control(self, context, tool_key, tool_display_name, emoji_name, tool_identifier):
        """Handle temperature controls"""
        params = context.parameter.split("_")
        temps = self.main._printer.get_current_temperatures()

        if len(params) <= len(tool_identifier.split("_")):
            self.temp_target_temps[tool_key] = temps[tool_key]["target"]
        else:
            delta_str = params[len(tool_identifier.split("_"))]

            if delta_str.startswith(("+", "-")):
                self.temp_target_temps[tool_key] = max(self.temp_target_temps[tool_key] + int(delta_str), 0)
            elif delta_str.startswith("s"):
                self.main._printer.set_temperature(tool_key, self.temp_target_temps[tool_key])
                return self._go_back(context)
            else:
                self.temp_target_temps[tool_key] = 0
                self.main._printer.set_temperature(tool_key, 0)
                return self._go_back(context)

        current_temp = temps[tool_key]["actual"]
        target_temp = self.temp_target_temps[tool_key]

        msg = render_emojis(
            f"{{emo:{emoji_name}}} Set temperature for <code>{html.escape(tool_display_name)}</code>.\n"
            f"Current: {current_temp:.02f}/<b>{target_temp}°C</b>"
        )

        command_buttons = self._create_temp_buttons(tool_identifier, context)

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )
