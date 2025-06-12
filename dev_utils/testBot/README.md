# Standalone bot listener

This bot listener is extracted from the plugin for standalone use without OctoPrint. It is able to receive commands and send notifications. Also detecting new users is possible (data of new users will be lost when listener stops).

## Things that do not work:
* short: all Octoprint related
* no printer status or simmilar things
* no file up/download or execution
* no web frontend
* no settings management

## Setup and run
* open _settings_example.py_
* insert your bot token
* create one or more chat entries
* save as _settings.py_
* start botListener with `python __init__.py`
* to stop the listener hit `Ctrl + C`

## Settings
Setup token and one or more chats. The structure of a chat should look something like this:
```
'1234567890':{
			'private' : True,
			'allow_user' : True,
			'accept_commands' : True,
			'send_notifications' : True,
			'title' : 'ExampleUser',
			'commands':{
				'/print': False
			},
			'notifications':{
				'PrinterStarted': False
			}
		}
```

The `comamnds` and `notifications` sub directories are only needed, if you want to disable some rights for a user.
By default the bot listener will allow every command and notification for every user. `allow_commands` and `send_notifications` have to be enabled too. Otherwise no command/notification will work. It's like in the 'real' settings.
