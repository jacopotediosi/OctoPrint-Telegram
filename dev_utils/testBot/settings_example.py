# rename this file to settings.py when you are done with setup in this file
from telegramNotifications import telegramMsgDict  # dict of known notification messages

settingsDict = {
    "token": "1234567890:xxXXxx1xXxX1x11x1xXXXxXXXXXXxXXXX!",  # <===== insert your bot token here
    "notification_height": 5.0,
    "notification_time": 15,
    "message_at_print_done_delay": 0,
    "messages": telegramMsgDict,
    "debug": True,
    "send_icon": True,
    "chats": {
        "1234567890": {  # <===== insert user account id here
            "private": True,
            "allow_user": True,
            "accept_commands": True,
            "send_notifications": True,
            "title": "ExampleUser",
            "commands": {  # commands dict is only needed if you want to deactivate...
                "/print": False  # ...a command (like /print here). By default they are ALL activated
            },
            # do the same for notifications if you want
            "notifications": {"PrinterStarted": False},
        },
        # insert as many users you want before zBOTTOMOFCHATS
        "zBOTTOMOFCHATS": {
            "send_notifications": False,
            "accept_commands": False,
            "private": False,
        },
    },
}
