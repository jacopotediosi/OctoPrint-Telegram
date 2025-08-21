---
layout: plugin

id: telegram
title: Telegram
description: Control your printer and receive notification messages via Telegram Messenger.
authors:
    - Jacopo Tediosi
    - Fabian Schlenz
license: AGPLv3

date: 2016-02-25

homepage: https://github.com/jacopotediosi/OctoPrint-Telegram
source: https://github.com/jacopotediosi/OctoPrint-Telegram
archive: https://github.com/jacopotediosi/OctoPrint-Telegram/archive/master.zip

privacypolicy: https://github.com/jacopotediosi/OctoPrint-Telegram/blob/master/PRIVACY.md

tags:
- control
- filament
- filament runout
- lights
- mobile
- monitor
- monitoring
- notification
- notifications
- power
- print status
- progress
- remote
- remote camera
- telegram
- webcam

screenshots:
- url: /assets/img/plugins/telegram/screen_1.png
  alt: Screenshot of the "Connection" tab in plugin settings
  caption: Screenshot of the "Connection" tab in plugin settings
- url: /assets/img/plugins/telegram/screen_2.png
  alt: Screenshot of the "General settings" tab in plugin settings
  caption: Screenshot of the "General settings" tab in plugin settings
- url: /assets/img/plugins/telegram/screen_3.png
  alt: Screenshot of the "Chats" tab in plugin settings
  caption: Screenshot of the "Chats" tab in plugin settings
- url: /assets/img/plugins/telegram/screen_4.png
  alt: Screenshot of the "Notification messages" tab in plugin settings
  caption: Screenshot of the "Notification messages" tab in plugin settings
- url: /assets/img/plugins/telegram/screen_5.png
  alt: Example of the /con and /files commands
  caption: Example of the /con and /files commands
- url: /assets/img/plugins/telegram/screen_6.png
  alt: Example of a notification message containing photos, videos, and details of the print in progress
  caption: Example of a notification message containing photos, videos, and details of the print in progress
- url: /assets/img/plugins/telegram/screen_7.png
  alt: Example of file details displayed in response to the /files command
  caption: Example of file details displayed in response to the /files command
- url: /assets/img/plugins/telegram/screen_8.png
  alt: Example of commands to start, pause, and abort a print job
  caption: Example of commands to start, pause, and abort a print job
- url: /assets/img/plugins/telegram/screen_9.png
  alt: Example of the /power and /cancelobject commands
  caption: Example of the /power and /cancelobject commands

featuredimage: /assets/img/plugins/telegram/logo.png

compatibility:
  octoprint:
  - 1.4.0
  python: '>=3.7,<4'

attributes:
- cloud

---

This plugin integrates Telegram Messenger with OctoPrint.

### Features

<ul style="list-style-type:none">
<li>🔔 Receive Telegram messages with print status, including snapshots and videos from your webcams</li>
<li>📡 Remotely control your printer from Telegram (e.g., browsing and uploading files, starting, pausing, and aborting prints, tuning temperatures, etc.)</li>
<li>🔌 Manage connected power devices (printers, lights, heaters, etc.) directly from Telegram</li>
<li>🔐 Configure allowed commands and active notifications for each chat</li>
<li>🧩 Integrations with many other plugins (e.g., manage filaments from Telegram, cancel single objects, control various brands of plugs, etc.)</li>
</ul>

### Documentation

For full installation and usage instructions, available features, configuration guidance, and common troubleshooting steps, please refer to the [plugin’s Wiki](https://github.com/jacopotediosi/OctoPrint-Telegram/wiki).

### Support the project

This project is distributed for free and maintained entirely by volunteers, who do their best to develop it in their spare time, gather feedback and reports from users, and fix issues.

If you'd like to support the maintainers of this project, you can donate via the [GitHub Sponsor page](https://github.com/sponsors/jacopotediosi) ❤️.
