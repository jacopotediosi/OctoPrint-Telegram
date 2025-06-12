<!-- omit in toc -->
# OctoPrint-Telegram

<img src="https://raw.githubusercontent.com/jacopotediosi/OctoPrint-Telegram/screenshots/logo/octoprint_telegram_logo.png" width="25%" align="left">

This plugin integrates Telegram Messenger with Octoprint. It sends messages (with photos if available) on print start, end and failure. Also it sends messages during the print at configurable intervals. That way you don't have to remember to regularly have a look at the printing process.
Also, you can control Octoprint via messages (settings, start a print and much more). Send `/status` to get the current printer status or `/abort` to abort the current print. Send `/help` for a list of all recognized commands. You may also use this bot in groups.

**Latest release: [1.6.5](https://github.com/jacopotediosi/OctoPrint-Telegram/releases)**

<!-- omit in toc -->
## Contents

- [Screenshots](#screenshots)
- [Installation](#installation)
	- [Create Telegram Bot](#create-telegram-bot)
	- [Plugin setup](#plugin-setup)
	- [User setup](#user-setup)
- [Configuration](#configuration)
	- [General](#general)
	- [Users](#users)
	- [Notifications](#notifications)
- [Available Commands](#available-commands)
- [Info / Contact / Help](#info--contact--help)

## Screenshots

![Screenshot](https://raw.githubusercontent.com/jacopotediosi/OctoPrint-Telegram/screenshots/telegram_screen.png)

## Installation

To set up Octoprint Telegram, you have to follow the following three steps.

### Create Telegram Bot

To allow the plugin to send messages via telegram, you need to register a telegram bot.

If you already have a bot, you only need your bot token to proceed. GOTO `4.` (optional) or go dirctly over to [Plugin Setup](#plugin-setup).

1. Contact [@botfather](http://telegram.me/botfather) in Telegram Messenger. Either click the link or use the "new chat" / "search" feature of your telegram client to search for "@botfather".


2. Send `/newbot` to @botfather. Enter a name for the bot, e.g. "JoeDoe Octoprinter Bot". Then enter a username for the bot, e.g. "JoeDoeOctoprinterBot". This username has to end in "bot".


3. The botfather hands you a token. You need this to use your bot. Keep this token secret!

	<img src="https://raw.githubusercontent.com/jacopotediosi/OctoPrint-Telegram/screenshots/bot_new.png" alt="Register new bot" width="35%" align="center"/>

<!-- omit in toc -->
#### OPTIONAL

	While you're there, you could also do the following steps:


4. Give your bot a nice profile picture. Send `/setuserpic` to @botfather, select the bot and send the Octoprint logo or any other image you like.


5. Tell the botfather which commands are available. This enables Telegram to auto-complete commands to your bot. Send `/setcommands` to @botfather, select the bot and then send the lines in the box below (one message with multiple lines).
	```markdown
	abort - Aborts the currently running print. A confirmation is required.
	shutup - Disables automatic notifications till the next print ends.
	dontshutup - The opposite of /shutup - Makes the bot talk again.
	status - Sends the current status including a current photo.
	settings - Displays the current notification settings and allows you to change them.
	files - Lists all the files available for printing.
	filament - Shows you your filament spools or lets you change it.
	print - Lets you start a print. A confirmation is required.
	togglepause - Pause/Resume current Print.
	home - Home the printer print head.
	con - Connect/disconnect printer.
	upload - You can just send me a gcode file to save it to my library. Also accept zip file.
	sys - Execute Octoprint System Commands.
	ctrl - Use self defined controls from Octoprint.
	tune - Set feed- and flowrate. Control temperatures.
	user - get user info.
	help - show list of commands.
	gif - send a gif of 5 seconds
	supergif - send a gif of 10 seconds
	on - Turns on the printer power via the PSUControl plugin API. Requires PSU Control plugin installation.
	off - Turns off the printer power via the PSUControl plugin API. Requires PSU Control plugin.
	gcode_XXX - Send the gcode to the printer where XXX is the gcode command (/gcode_M117 HelloWorld for exemple)
	```
	<img src="https://raw.githubusercontent.com/jacopotediosi/OctoPrint-Telegram/screenshots/bot_optional.png" alt="Optional bot settings" width="60%" align="center"/> <br><br><br>

### Plugin setup

1. Install the plugin via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager) or manually using this URL: `https://github.com/jacopotediosi/OctoPrint-Telegram/archive/master.zip`


2. Now enter Octoprint settings and select *Telegram* on the left.


3. Enter the token you got from botfather into the field "Telegram Token".


4. Hit the "Test this token" button. It should report success.


5. Hit "Save" at the bottom of the settings dialog.

6. If you want to create gif and receive them as notification we use ffmpeg like timelapse (if problem please check timelapse is configured).
you'll have to install CpuLimit to be able to create gif so please for raspberry connect to your raspberry with putty (for exemple) and execute
sudo apt-get install cpulimit

Congratulations! Your printer is now connected to your Telegram bot.

### User setup

1. Open your Octoprint settings and select *Telegram* on the left.


2. Send a start message (any message will do) to your new bot. You should receive a message from your bot which tells you something like "Now I know you".


3. Now hit the "reload" button under the known chats list. The chat should appear in the list.


4. Save settings to accept new user(s)/group(s) in list.


5. Now reopen octoprit settings and check/set the configurations for new users. (see [below](#users))

## Configuration

Configuration is done via the Octoprint settings dialog. Note that only admin users will be able to change user or token settings.

### General

**The paragraph numbers below correspond to the numbers in the picture!**

1. Token: Enter your bot token here. You got this from @botfather, when you [created](#create-telegram-bot) your bot there. *(admin users only)*


2. After hitting 'Test this token', the current connection status will be shown and the bot is connected on success. *(admin users only)*

3. Send notification every: Whenever the current z value grows by this value (or more) or the given time has passed since the last notification, a message will be sent.
   * Setting the height to 1.0mm would send messages at z=1.0, z=2.0, z=3.0 and so on.
   * Having the height at 1.0mm with a layer height of 0.3 would send messages at z=1.2, z=2.4, z=3.6 and so on.
   * Setting the time or height to `0` disables those checks. Setting both values to `0` completely disables automatic notifications while printing.

4. Set a delay to wait for print head moving out of camera view on end of print.


5. Choose if you want to send an image along with the "Not connected to a printer" message. (green = send image, yellow=no image)

6. If send emojis is enabled, emojis will be send within messages. If disabled, all emojis in messages will be changed to empty strings.

	<img src="https://raw.githubusercontent.com/jacopotediosi/OctoPrint-Telegram/screenshots/set_general.png" alt="General settings" width="70%" align="center"/><br><br><br>

### Users

There are users (private chat with single user) or groups you will see in the list of known chats. These settings are only accessible by admin users.

**The paragraph numbers below correspond to the numbers in the picture!**

1. When clicking the *command* icon, a dialog with a list of checkboxes for every accepted command will open. Check a box to enable the user/group to use the command. When done, close the dialog. Don't forget to enable general command execution in `3.`

2. By clicking on the *notification* icon, a dialog with a list of checkboxes for every known notification event will open. Checked notifications will be send to the user/group. When done, close the dialog. Don't forget to activate general notification in `3.`

3. **IMPORTANT**<br>**a)** By clicking the *pencil* icon, you are able to enable/disable commands and notifications for the user/group in general. This will not affect the settings you made in `1.` and `2.`. It's an easy way to quickly activate/deactivate a user/group withot changing the settings. You will find the following options:
	* For users:
	  * *Allow to send commands*: This option will give the user the ability to send commands you defined in `1.`
	* For groups:
	  * *Allow user commands*: This will allow *known* users to send commands. Settings of the specific users will be used. No other users in the group are allowed to send commands.
		```
		Example: User A, B and C are in one group. Only user A and B are known by the bot.
		User A has /print enabled and user B has not. Both have /status enabled.
		So user A is allowed to send /print and /status while user B is only allowed to
		send /status. User C is not allowed to send any command.
		```

	  * *Allow to send commands*: When this option is enabled, all users in the group are allowed to send commands. Choose the allowed commands by setting up `1.` for the group. If *Allow user commands* is enabled, known users will have the ability to send commands activated for them but not for the group.
		```
		Example: 'Allow user commands' is enabled for the group. User A and B are in the group.
		Only user A is known by the bot. User A has /print enabled and the group has not.
		The group has /status enabled but user A not. So user A is allowed to send
		/print (user rights) and /status (group rights) while user B is only allowed to send
		/status. If 'Allow user commands' is disabled, also A will only be able to send /status.
		```
	* For both:
	  * *Send notifications*: This will allow the bot to send the notifications you enabled in `2.` to the user/group.

	**b)** Click the *trash bin*, to delete the user. The user is only deleted if you hit 'Save' on settings dialog.

	<img src="https://raw.githubusercontent.com/jacopotediosi/OctoPrint-Telegram/screenshots/set_user.png" alt="User settings" width="70%" align="center"/><br><br><br>

### Notifications

In this section you can configure the content of the notification messages.

**The paragraph numbers below correspond to the numbers in the picture!**

1. These three buttons will open dialogs which provide you informations about using markup, variables and emojis in the messages.

2. Enter the text you want to send when the specific event happens.

3. Choose if you want to send an image along with the notification message. (green = send image, yellow=no image)

4. ~~With this option you select if the image and the text are send in one message or in two separated messages. Only available if you choose to send an image.~~ **NOT AVAILABLE ANYMORE**

5. This buttons sets the markup options for the message text. Only available when no image will be send or if image will be send in a separate message.

6. You can use variables in the messages :
   * `{file}`, `{path}` (only usable while printing) - The currently printing file, with or without path information.
   * `{z}` (only for height change events) - The current z value.
   * `{percent}` (only useful for height change notifications) - The current percentage of the print progress.
   * `{time_done}`, `{time_left}`, `{time_finish}` (only useful for height change events) - Time done / left in the print and ETA.
   * `{bed_temp}`, `{e1_temp}`, `{e2_temp}` - Temperatures of bed, extruder 1 and extruder 2.
   * `{bed_target}`, `{e1_target}`, `{e2_target}` - Target temperatures of bed, extruder 1 and extruder 2.
   * `{currentLayer}`, `{totalLayer}` - the current and total layers number (need the plugin [DisplayLayerProgress](https://github.com/OllisGit/OctoPrint-DisplayLayerProgress))
   * You are also able to access the current printer state data. See [here](./dev_utils/datastructures/octoprint/_printer.get_current_data.py) for datastructure of this data. The base variable is `{status}`.
	```
	Example: {status[progress][filepos]} - will insert the actual position in the printed file.
	```

	<img src="https://raw.githubusercontent.com/jacopotediosi/OctoPrint-Telegram/screenshots/set_messages.png" alt="Optional bot settings" width="70%" align="center"/><br><br><br>

## Available Commands

**`/abort`** - Aborts the currently running print. A confirmation is required.

**`/shutup`** - Disables automatic notifications till the print ends.

**`/dontshutup`** - The opposite of /shutup - Makes the bot talk again.

**`/status`** - Sends the current status. (printing/not printing/disconnected)

**`/settings`** - Displays the current notification settings (time and height) and allows you to change them.

**`/files`** - Lists all the files available for printing in upload folder and allows you download and delete them. You also can view detailed informations of the file like print history.

**`/filament`** - Shows your filament spools and the percentage of usage. In addition you can change the filament spool with this command. Requires the [Filament Manager Plugin](https://plugins.octoprint.org/plugins/filamentmanager/)

**`/print`** - Will open a file dialog showing the files stored in octoprint. You can select a file to print it.

**`/togglepause`** - Pause/resume the current print.

**`/home`** - Home the printer print head.

**`/con`** - Connect/disconnect printer. Choose between auto connect, use defaults to connect or manual connect (select port/baudrate/printer profile). You are also able to change the connection defaults and turn auto connect on/off.

**`/upload`** - You can just send a gcode file or a zip file to the bot to save it in upload folder of Octoprint. If you send this command, the bot will tell you the same :) NOTE: This will NOT work in groups.

**`/sys`** - Execute Octoprint System Commands you defined in *config.yaml*. If a confirmation is defined for the system command, it will be displayed before execution. See [Octoprint documentation](http://docs.octoprint.org/en/master/configuration/config_yaml.html#system) for details on setting up system commands. There is also a [plugin](http://plugins.octoprint.org/plugins/systemcommandeditor/) for doing this.

**`/ctrl`** - Use self defined controls from Octoprint. Only plain controls (without input or output) will be used. If a confirmation is defined for the control, it will be displayed before execution. See [Octoprint documentation](http://docs.octoprint.org/en/master/configuration/config_yaml.html#controls) for details on setting up controls. There is also a [plugin](http://plugins.octoprint.org/plugins/customControl/) for doing this.

**`/tune`** - Set feed- and flowrate. Also set temperature of extruder(s) and bed or switch them off.

**`/user`** - Get user/group information. This will contain saved user/group data, allowed comamnds and the notifications send to the user/group.

**`/help`** - Displays a help message with all accepted commands and a short description.

**`/gif`** - Send a gif create from 20 images. You'll have to install CpuLimit to be able to create gif so please for raspberry connect to your raspberry with putty (for exemple) and execute
sudo apt-get install cpulimit

**`/supergif`** - Send a gif create from 60 images. You'll have to install CpuLimit to be able to create gif so please for raspberry connect to your raspberry with putty (for exemple) and execute
sudo apt-get install cpulimit

**`/on`** - Turns on the Printer power via - the PSUControl plugin API. Requires the [PSU Control plugin](https://github.com/kantlivelong/OctoPrint-PSUControl)
										   - the TuyaSmartplug plugin API. Requires the [TuyaSmartplug plugin](https://github.com/ziirish/OctoPrint-TuyaSmartplug/) sadly for now wait on accept the push request to get the list of plug

**`/off`** - Turns off the Printer power via - the PSUControl plugin API. Requires the [PSU Control plugin](https://github.com/kantlivelong/OctoPrint-PSUControl)
                                             - the TuyaSmartplug plugin API. Requires the [TuyaSmartplug plugin](https://github.com/ziirish/OctoPrint-TuyaSmartplug/)
											 sadly for now wait on accept the push request to get the list of plug

**`/gcode`** - Send the gcode to the printer where XXX is the gcode command (/gcode_M117 HelloWorld for exemple)

<!-- omit in toc -->
#### Notes:

* the `/help` command is always allowed


* `/files` and `/print` will basically show the same file dialog. If `/print` is disabled, no print button will be shown. If `/files` is disabled, no download and delete buttons will be shown. If both commands are enabled, all buttons will be shown regardles wether the user entered the dialog by `/files` or `/print`.

<br><br><br>

## Info / Contact / Help

If you want to talk to other users of this plugin and maybe have some influence in the development of this plugin,
you can join the [Octoprint-Telegram-Users-Group](https://telegram.me/joinchat/CXFirQjl9XTp5dr4OZqH9Q).

This software is licensed under [AGPLv3](http://www.gnu.org/licenses/agpl-3.0.txt)
