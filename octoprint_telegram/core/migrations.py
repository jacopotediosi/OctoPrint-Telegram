from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Callable

from ..commands import registry
from ..domain.chats import PLACEHOLDER_CHAT_ID
from ..notifications import NOTIFICATION_DEFINITIONS

if TYPE_CHECKING:
    import logging

    from octoprint.plugin import PluginSettings


def migrate_settings(
    target: int,
    current: int | None,
    settings: PluginSettings,
    build_new_chat_settings: Callable[[], dict],
    logger: logging.Logger,
) -> None:
    """Bring the stored settings up to a newer settings version.

    Args:
        target (int): The settings version to migrate to.
        current (int | None): The settings version in storage, or None if it was never written.
        settings (PluginSettings): The settings to migrate, updated in place.
        build_new_chat_settings (Callable): Callback that returns the settings a new chat starts with,
            good to fill in what a stored chat is missing.
        logger (logging.Logger): The logger to write to.
    """
    logger.warning("Migration - start migration from %s to %s", current, target)

    chats = {k: v for k, v in settings.get(["chats"]).items() if k != PLACEHOLDER_CHAT_ID}
    logger.info("Migration - loaded chats: %s", chats)

    messages = settings.get(["messages"])
    logger.info("Migration - loaded notification messages: %s", messages)

    # Migrate from plugin versions < 1.10.0
    if current is None or current < 7:
        # In previous versions, "type" was stored in uppercase
        for chat_settings in chats.values():
            if "type" in chat_settings and isinstance(chat_settings["type"], str):
                chat_settings["type"] = chat_settings["type"].lower()

    # General migration from all previous versions
    if current is None or current < target:
        # Rename mappings (old:new)
        commands_to_rename = {"/list": "/files", "/imsorrydontshutup": "/dontshutup", "/on": "/power"}
        notifications_to_rename = {
            "TelegramSendNotPrintingStatus": "StatusNotPrinting",
            "TelegramSendPrintingStatus": "StatusPrinting",
            "plugin_pause_for_user_event_notify": "PausedForUser",
        }
        notification_vars_to_rename = {"currentLayer": "current_layer", "totalLayer": "total_layer"}
        settings_to_rename = {"fileOrder": "sort_files_by_date", "selectFileUpload": "select_file_after_upload"}

        # Settings to delete
        settings_to_delete = [
            "chat",
            "message_at_startup",
            "message_at_shutdown",
            "message_at_print_started",
            "message_at_print_done",
            "message_at_print_failed",
            "image_not_connected",
            "gif_not_connected",
        ]

        # Update chats
        for chat_settings in chats.values():
            # Add new chat settings
            for setting, default_value in build_new_chat_settings().items():
                if setting not in chat_settings:
                    chat_settings[setting] = copy.deepcopy(default_value)

            # Get references
            chat_commands = chat_settings["commands"]
            chat_notifications = chat_settings["notifications"]

            # Rename commands (copy, not move)
            for old_command, new_command in commands_to_rename.items():
                if old_command in chat_commands:
                    chat_commands[new_command] = chat_commands[old_command]

            # Remove obsolete commands (available to everyone or no longer existing)
            for command in list(chat_commands):
                command_definition = registry.get(command)
                if command_definition is None or command_definition.available_to_everyone:
                    chat_commands.pop(command, None)

            # Add new commands
            for command_definition in registry.configurable_per_chat():
                if command_definition.name not in chat_commands:
                    chat_commands[command_definition.name] = False

            # Rename notifications (copy, not move)
            for old_notification, new_notification in notifications_to_rename.items():
                if old_notification in chat_notifications:
                    chat_notifications[new_notification] = chat_notifications[old_notification]

            # Remove obsolete notifications (no longer present in NOTIFICATION_DEFINITIONS)
            for msg in list(chat_notifications):
                if msg not in NOTIFICATION_DEFINITIONS:
                    chat_notifications.pop(msg, None)

            # Add new notifications
            for notification in NOTIFICATION_DEFINITIONS:
                if notification not in chat_notifications:
                    chat_notifications[notification] = False

        # Rename notification messages (copy, not move)
        for message, message_props in list(messages.items()):
            mapped_key = notifications_to_rename.get(message, message)
            definition = NOTIFICATION_DEFINITIONS.get(mapped_key)
            messages[mapped_key] = (
                message_props
                if isinstance(message_props, dict)
                else {**(definition.as_settings() if definition else {}), "text": str(message_props)}
            )

        # Remove obsolete notification messages (no longer present in NOTIFICATION_DEFINITIONS)
        for message in list(messages):
            if message not in NOTIFICATION_DEFINITIONS:
                messages.pop(message, None)

        # Add new messages
        for message, definition in NOTIFICATION_DEFINITIONS.items():
            if message not in messages:
                messages[message] = definition.as_settings()

        # Rename vars in notification messages
        for message_props in messages.values():
            message_text = message_props.get("text")
            if message_text is not None:
                for old_var, new_var in notification_vars_to_rename.items():
                    message_text = message_text.replace("{" + old_var + "}", "{" + new_var + "}")
                message_props["text"] = message_text

        # Rename settings
        for old_setting, new_setting in settings_to_rename.items():
            old_setting_value = settings.get([old_setting])
            if old_setting_value is not None:
                settings.set([new_setting], old_setting_value)
                settings.set([old_setting], None)

        # Delete old settings
        for key in settings_to_delete:
            settings.set([key], None)

    # Save the settings after migration is done
    settings.set(["chats"], chats)
    logger.info("Migration - chats set: %s", chats)
    settings.set(["messages"], messages)
    logger.info("Migration - notification messages set: %s", messages)

    logger.warning("Migration - end")
