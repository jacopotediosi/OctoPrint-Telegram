---
layout: plugin

id: telegram
title: OctoPrint-Telegram
description: A plugin to send and react on messages before, during and after a print
  via Telegram Messenger.
author: Jacopo Tediosi
license: AGPLv3

date: 2016-02-25

homepage: https://github.com/jacopotediosi/OctoPrint-Telegram
source: https://github.com/jacopotediosi/OctoPrint-Telegram
archive: https://github.com/jacopotediosi/OctoPrint-Telegram/archive/master.zip

# Set this to true if your plugin uses the dependency_links setup parameter to include
# library versions not yet published on PyPi. SHOULD ONLY BE USED IF THERE IS NO OTHER OPTION!
follow_dependency_links: false

tags:
- notification
- mobile
- progress
- control

screenshots:
- url: /assets/img/plugins/telegram/features1.png
  alt: Telegram notifications during print
  caption: You can receive current status with a webcam picture in user-definable
    intervals.
- url: /assets/img/plugins/telegram/features3.png
  alt: Requesting the current status
  caption: You can control octoprint via messages. E.g. sending /status lets the Plugin
    send you the current status.
- url: /assets/img/plugins/telegram/features4.png
  alt: Custom keyboards
  caption: You can also abort the current print with /abort. A custom keyboard is
    shown for confirmation.
- url: /assets/img/plugins/telegram/features5.png
  alt: Settings
  caption: You can configure lots of settings via Octoprint's settings. (Or you can
    use /settings to change them via Telegram.)
featuredimage: /assets/img/plugins/telegram/features3.png

compatibility:
  octoprint:
  - 1.4.0
  python: '>=3.6,<4'

attributes:
- cloud

---

This plugin integrates Telegram Messenger into Octoprint.

You can receive automatic notifications with webcam images before and after a print -
and even during a print at customizable heights or after a certain time (e.g. after every
5mm of height OR after 10 minutes - whatever happened first).

You can also control Octoprint via messages. Send /status to receive the current status,
/abort to abort the currently running print or /help to receive a list of available commands.

Please have a look at [the documentation at github](https://github.com/jacopotediosi/OctoPrint-Telegram/blob/master/README.md)
to learn how to register a Telegram bot. This is a needed step in order to make this plugin work.

If you have any questions or problems feel free to contact me to jacopotediosi@gmail.com.
