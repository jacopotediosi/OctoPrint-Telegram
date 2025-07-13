/*
 * View model for OctoPrint-Telegram
 *
 * Author: Jacopo Tediosi, Fabian Schlenz
 * License: AGPLv3
 */

/* global $, _, ko, OctoPrint, OCTOPRINT_VIEWMODELS, showConfirmationDialog, ItemListHelper */
/* eslint camelcase: "off" */

$(function () {
  function TelegramViewModel (parameters) {
    const self = this

    self.settings = parameters[0]

    self.pluginIdentifier = 'telegram'

    self.chatListHelper = new ItemListHelper(
      'known_chats',
      {
        title: function (a, b) {
          if (a.title.toLocaleLowerCase() < b.title.toLocaleLowerCase()) return -1
          if (a.title.toLocaleLowerCase() > b.title.toLocaleLowerCase()) return 1
          return 0
        }
      },
      {},
      'title',
      [],
      [],
      999)

    self.reloadPending = 0
    self.reloadUsr = ko.observable(false)
    self.connection_state_str = ko.observable('Unknown')
    self.isloading = ko.observable(false)
    self.errored = ko.observable(false)
    self.token_state_str = ko.observable('Unknown')
    self.editChatDialog = undefined
    self.varInfoDialog = undefined
    self.emoInfoDialog = undefined
    self.mupInfoDialog = undefined
    self.timeInfoDialog = undefined
    self.proxyInfoDialog = undefined
    self.currChatID = 'Unknown'
    self.currChatTitle = ko.observable('Unknown')
    self.bind_cmd = {}
    self.markupFrom = []
    self.onBindLoad = false

    self.ffmpegPath = ko.observable(null)
    self.cpulimiterPath = ko.observable(null)

    self.requestData = function (ignore = false, update = false) {
      if (self.reloadUsr() || ignore) {
        self.isloading(true)

        if (update) {
          OctoPrint.simpleApiCommand(
            self.pluginIdentifier,
            'editUser',
            {
              chat_id: self.currChatID,
              accept_commands: $('#telegram-acccmd-chkbox-box').prop('checked'),
              send_notifications: $('#telegram-notify-chkbox-box').prop('checked'),
              allow_users: $('#telegram-user-allowed-chkbox-box').prop('checked')
            }
          ).done((response) => self.fromResponse(response))
        } else {
          OctoPrint.simpleApiGet(self.pluginIdentifier).done(
            (response) => self.fromResponse(response)
          )
        }

        if (!ignore) {
          self.reloadPending = setTimeout(self.requestData, 20000)
        }
      } else {
        self.reloadPending = setTimeout(self.requestData, 500)
      }
    }

    self.requestRequirements = function () {
      OctoPrint.simpleApiGet(self.pluginIdentifier + '?requirements')
        .done((response) => {
          self.ffmpegPath(response.ffmpeg_path)
          self.cpulimiterPath(response.cpulimiter_path)
        })
    }

    self.requestBindings = function () {
      self.isloading(true)
      OctoPrint.simpleApiGet(self.pluginIdentifier + '?bindings')
        .done((response) => self.fromBindings(response))
    }

    self.fromBindings = function (response) {
      self.bind = {
        commands: response.bind_cmd,
        notifications: response.bind_msg,
        no_setting: response.no_setting,
        bind_text: response.bind_text
      }

      self.onBindLoad = true
      $('#telegram_msg_list').empty()

      const keys = Object.keys(self.bind.notifications).sort()

      // For each event
      keys.forEach((eventName, index) => {
        const eventDesc = self.bind.notifications[eventName] || 'No description provided'

        // Event aliases
        let eventAliases = ''
        if (eventName in self.bind.bind_text) {
          const aliasList = self.bind.bind_text[eventName]
            .map(obj => {
              const aliasName = Object.keys(obj)[0]
              const aliasDesc = obj[aliasName]
              const descPart = aliasDesc ? ` (${aliasDesc.charAt(0).toLowerCase() + aliasDesc.slice(1)})` : ''
              return `<li>${aliasName}${descPart}</li>`
            })
            .join('')
          eventAliases = `<br /><br /><small>Also for:<ul>${aliasList}</ul></small>`
        }

        // Img switch
        const imgSwitch = `
          <div class="switch-container" style="margin: 5px 0;">
            <label class="switch-label" style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer;">
              <span>&#x1F4F7; Send camera photos</span>
              <input
                type="checkbox"
                style="display:none"
                class="switch-input"
                data-bind="checked: settings.settings.plugins.telegram.messages.${eventName}.image"
              />
              <span class="switch-slider"></span>
            </label>
          </div>
        `

        // Gif switch
        const gifSwitch = `
          <div class="switch-container" style="margin: 5px 0;">
            <label
              class="switch-label"
              style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer;"
              data-bind="attr: {
                title: !settings.settings.plugins.telegram.send_gif() ? 'Check \\'Enable gifs\\' setting to use this option' : null
              }"
            >
              <span>&#x1F3A5; Send camera gifs</span>
              <input
                type="checkbox"
                style="display:none"
                class="switch-input"
                data-bind="
                  checked: settings.settings.plugins.telegram.messages.${eventName}.gif,
                  enable: settings.settings.plugins.telegram.send_gif
                "
              />
              <span class="switch-slider"></span>
            </label>
          </div>
        `

        // Silent switch
        const silentSwitch = `
          <div class="switch-container" style="margin: 5px 0;">
            <label class="switch-label" style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer;">
              <span>&#128263; Send silently</span>
              <input
                type="checkbox"
                style="display:none"
                class="switch-input"
                data-bind="checked: settings.settings.plugins.telegram.messages.${eventName}.silent"
              />
              <span class="switch-slider"></span>
            </label>
          </div>
        `

        // Markup buttons group
        const currentMarkup = self.settings.settings.plugins.telegram.messages[eventName].markup() || 'off'
        self.markupFrom[index] = currentMarkup
        const markupButtonsGroup = `
          <span>
            <span>Markup Selection</span><br>
            <span class="btn-group" data-toggle="buttons-radio">
              <button type="button" class="btn btn-mini${currentMarkup === 'off' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${index}','off','${eventName}')">Off</button>
              <button type="button" class="btn btn-mini${currentMarkup === 'HTML' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${index}','HTML','${eventName}')">HTML</button>
              <button type="button" class="btn btn-mini${currentMarkup === 'Markdown' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${index}','Markdown','${eventName}')">Markdown</button>
              <button type="button" class="btn btn-mini${currentMarkup === 'MarkdownV2' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${index}','MarkdownV2','${eventName}')">MarkdownV2</button>
            </span><br>
          </span>
        `

        // Append the notification message entry
        const msgListEntry = `
          <div id="telegramMsgText${index}" style="margin-bottom: 20px;">
            <label for="textarea${index}" style="display: block; font-weight: bold; margin-bottom: 6px;">
              ${eventName}<br />
              <span class="muted">
                ${eventDesc}
                ${eventAliases}
              </span>
            </label>
            <textarea id="textarea${index}" rows="5" style="width: 100%; box-sizing: border-box; margin-bottom: 10px;"
              data-bind="value: settings.settings.plugins.telegram.messages.${eventName}.text"></textarea>

            <div style="display: flex; justify-content: space-around; margin-bottom: 10px;">
              ${imgSwitch}
              ${gifSwitch}
              ${silentSwitch}
            </div>

            <div style="text-align: center;">
              ${markupButtonsGroup}
            </div>
          </div>
          <hr style="margin:20px">
        `
        $('#telegram_msg_list').append(msgListEntry)
        ko.applyBindings(self, $('#telegramMsgText' + index)[0])
      })

      self.isloading(false)
      self.onBindLoad = false
    }

    self.toggleMarkup = function (data, sender, msg) {
      if (!self.onBindLoad) {
        if (self.markupFrom[data] !== sender) {
          $('#' + sender + data).toggleClass('active')
          $('#' + self.markupFrom[data] + data).toggleClass('active')
          self.settings.settings.plugins.telegram.messages[msg].markup(sender)
          self.markupFrom[data] = sender
        }
      }
    }

    self.updateChat = function (data) {
      self.requestData(true, true)
      self.editChatDialog.modal('hide')
    }

    self.testToken = function (data, event) {
      self.isloading(true)
      OctoPrint.simpleApiCommand(self.pluginIdentifier, 'testToken', {
        token: $('#settings_plugin_telegram_token').val()
      }).done((response) => self.fromTestToken(response))
    }

    self.fromTestToken = function (response) {
      self.isloading(false)
      self.token_state_str(response.connection_state_str)
      self.errored(!response.ok)
      if (!response.ok) {
        $('#teleErrored').addClass('text-error')
        $('#teleErrored').removeClass('text-success')
        $('#teleErrored2').addClass('text-error')
        $('#teleErrored2').removeClass('text-success')
      } else {
        $('#teleErrored').addClass('text-success')
        $('#teleErrored').removeClass('text-error')
        $('#teleErrored2').addClass('text-success')
        $('#teleErrored2').removeClass('text-error')
      }
    }

    self.fromResponse = function (response) {
      if (response === undefined) return
      if (Object.prototype.hasOwnProperty.call(response, 'connection_state_str')) {
        self.connection_state_str(response.connection_state_str)
      }
      if (Object.prototype.hasOwnProperty.call(response, 'connection_ok')) {
        // self.errored(!response.connection_ok);
      }
      const entries = response.chats
      if (entries === undefined) return
      const array = []
      const formerChats = _.pluck(self.chatListHelper.allItems, 'id')
      const currentChats = []
      let newChats = false
      for (const id in entries) {
        const data = entries[id]
        data.id = id
        array.push(data)
        currentChats.push(id)
        newChats = newChats || !_.includes(formerChats, id)
      }

      const deletedChatIds = _.difference(formerChats, currentChats)
      if (newChats || (deletedChatIds && deletedChatIds.length)) {
        // Transfer the chats back to the server settings (because just hitting "save" on the Settings dialog
        // won't transfer anything we haven't explicitly set).

        // TODO: This whole workflow should be optimized!
        // Currently it takes two full server/client round trips to get the chats in sync, and just reusing
        // the plugin's API for that purpose would probably be way way more efficient and less error prone.
        self.settings.saveData({ plugins: { telegram: { chats: entries } } })
      }
      self.chatListHelper.updateItems(array)
      self.isloading(false)
    }

    self.showEditChatDialog = function (data) {
      if (!data) return

      self.currChatTitle(data.title)
      self.currChatID = data.id

      $('#telegram-acccmd-chkbox').empty()
      $('#telegram-notify-chkbox').empty()
      $('#telegram-user-allowed-chkbox').empty()

      if (!data.private) {
        $('#telegram-acccmd-chkbox').append(`
          <input
            id="telegram-acccmd-chkbox-box"
            type="checkbox"
            data-bind="checked: settings.settings.plugins.telegram.chats['${data.id}']['accept_commands']"
          >
          Allow all group members to send enabled commands
          <span class="help-block">
            <small>
              When enabled, <b>every user</b> in this group can send commands that have been enabled for the entire group chat. You must manually activate permissions for each command by clicking the blue command icon in the chat list. If 'Allow individual user command permissions' is also enabled, users can send commands enabled in their personal settings in addition to those enabled for the group.
            </small>
          </span>
        `)
        ko.applyBindings(self, $('#telegram-acccmd-chkbox-box')[0])

        $('#telegram-user-allowed-chkbox').append(`
          <div class="control-group">
            <div class="controls">
              <label class="checkbox">
                <input
                  id="telegram-user-allowed-chkbox-box"
                  type="checkbox"
                  data-bind="checked: settings.settings.plugins.telegram.chats['${data.id}']['allow_users']"
                >
                Allow individual user command permissions
                <span class="help-block">
                  <small>
                    When enabled, users with command access can send only the commands they have individually enabled in their personal settings.
                  </small>
                </span>
              </label>
            </div>
          </div>
        `)
        ko.applyBindings(self, $('#telegram-user-allowed-chkbox-box')[0])
      } else {
        $('#telegram-acccmd-chkbox').append(`
          <input
            id="telegram-acccmd-chkbox-box"
            type="checkbox"
            data-bind="checked: settings.settings.plugins.telegram.chats['${data.id}']['accept_commands']"
          >
          Allow to send commands
          <span class="help-block">
            <small>
              After enabling this option, enable or disable permissions for each command by clicking the blue command icon in the list once this dialog is closed.
            </small>
          </span>
        `)
        ko.applyBindings(self, $('#telegram-acccmd-chkbox-box')[0])

        $('#telegram-user-allowed-chkbox').append(`
          <input
            id="telegram-user-allowed-chkbox-box"
            style="display:none"
            type="checkbox"
            data-bind="checked: settings.settings.plugins.telegram.chats['${data.id}']['allow_users']"
          >
        `)
        ko.applyBindings(self, $('#telegram-user-allowed-chkbox-box')[0])
      }

      $('#telegram-notify-chkbox').append(`
        <input
          id="telegram-notify-chkbox-box"
          type="checkbox"
          data-bind="checked: settings.settings.plugins.telegram.chats['${data.id}']['send_notifications']"
        > Send notifications
        <span class="help-block">
          <small>
            After enabling this option, enable or disable individual notifications by clicking the blue "Notify" button in the chat list once this dialog is closed.
          </small>
        </span>
      `)
      ko.applyBindings(self, $('#telegram-notify-chkbox-box')[0])

      self.editChatDialog.modal('show')
    }

    self.showEditCmdDialog = function (data, option) {
      if (!data) return

      self.currChatTitle(`Edit ${option}: ${data.title}`)

      const labelText = option === 'commands' ? 'Allowed commands:' : 'Get notifications at:'
      $('#tele-edit-control-label').html(`<strong>${labelText}</strong>`)

      const keyLabel = option === 'commands' ? 'Command' : 'Event'
      $('#telegram-cmd-key-header').text(keyLabel)

      $('#telegram-cmd-chkbox-grp').empty()

      const entries = Object.entries(self.bind[option])
        .filter(([key]) => !self.bind.no_setting.includes(key))
        .sort(([a], [b]) => a.localeCompare(b))

      entries.forEach(([key, desc], index) => {
        desc = desc || 'No description provided'

        const allNames = [`<code>${key}</code>`]
        const allDescs = [desc]

        if (option === 'notifications' && key in self.bind.bind_text) {
          const aliases = self.bind.bind_text[key]
          aliases.forEach(obj => {
            const alias = Object.keys(obj)[0]
            allNames.push(`<code>${alias}</code>`)
            allDescs.push(obj[alias])
          })
        }

        const aliasNamesBlock = allNames.join('<hr style="margin:4px 0;">')
        const aliasDescsBlock = allDescs.join('<hr style="margin:4px 0;">')

        const checkboxHtml = `
          <tr id="telegram-cmd-chkbox${index}">
            <td style="text-align:center;">
              <input type="checkbox"
                    data-bind="checked: settings.settings.plugins.telegram.chats['${data.id}']['${option}']['${key}']">
            </td>
            <td>${aliasNamesBlock}</td>
            <td>${aliasDescsBlock}</td>
          </tr>
        `

        const $element = $(checkboxHtml).appendTo('#telegram-cmd-chkbox-grp')
        ko.applyBindings(self, $element[0])
      })

      $('#tele-enable-all').off('click').on('click', function () {
        const chat = self.settings.settings.plugins.telegram.chats[data.id][option]
        for (const key in chat) {
          if (Object.prototype.hasOwnProperty.call(chat, key)) {
            chat[key](true)
          }
        }
      })
      $('#tele-disable-all').off('click').on('click', function () {
        const chat = self.settings.settings.plugins.telegram.chats[data.id][option]
        for (const key in chat) {
          if (Object.prototype.hasOwnProperty.call(chat, key)) {
            chat[key](false)
          }
        }
      })

      self.editCmdDialog.modal('show')
    }

    self.delChat = function (data) {
      if (data === undefined) return
      const callback = function () {
        self.isloading(true)
        OctoPrint.simpleApiCommand(
          self.pluginIdentifier,
          'delChat',
          { chat_id: data.id }
        ).done((response) => self.fromResponse(response))
      }
      showConfirmationDialog('Do you really want to delete ' + _.escape(data.title), callback)
    }

    self.onSettingsHidden = function () {
      clearTimeout(self.reloadPending)
    }

    self.onSettingsShown = function () {
      self.requestData(true, false)
      self.requestData()
      self.requestRequirements()
      self.requestBindings()
      self.testToken()
      self.editChatDialog = $('#settings-telegramDialogEditChat')
      self.editCmdDialog = $('#settings-telegramDialogEditCommands')
      self.varInfoDialog = $('#settings-telegramDialogVarInfo')
      self.emoInfoDialog = $('#settings-telegramDialogEmoInfo')
      self.mupInfoDialog = $('#settings-telegramDialogMupInfo')
      self.timeInfoDialog = $('#settings-telegramDialogTimeInfo')
      self.proxyInfoDialog = $('#settings-telegramDialogProxyInfo')
    }

    self.isNumber = function (number) {
      return !isNaN(parseFloat(number)) && isFinite(number)
    }

    self.onSettingsBeforeSave = function () {
      // Check specific settings to be a number, not a null
      // In case it's not a number set it to be 0
      const settings = self.settings.settings.plugins.telegram
      const settings_to_check_number = [
        settings.notification_height,
        settings.notification_time,
        settings.message_at_print_done_delay
      ]
      for (let i = 0; i < settings_to_check_number.length; i++) {
        if (!self.isNumber(settings_to_check_number[i]())) {
          settings_to_check_number[i](0)
        }
      }
    }

    self.onServerDisconnect = function () {
      clearTimeout(self.reloadPending)
    }

    self.onDataUpdaterReconnect = function () {
      if (self.reloadUsr()) { self.requestData() } else { self.requestData(true, false) }
      self.requestData()
      self.requestBindings()
    }

    $(function () {
      $('button[data-toggle="reveal"]').on('click', function () {
        const $btn = $(this)
        const $input = $($btn.data('target'))
        const $icon = $btn.find('i')
        const isPassword = $input.attr('type') === 'password'

        $input.attr('type', isPassword ? 'text' : 'password')
        $icon.toggleClass('fa-eye fa-eye-slash')
        $btn.attr('title', isPassword ? 'Hide' : 'Show')
      })
    })
  }

  // view model class, parameters for constructor, container to bind to
  OCTOPRINT_VIEWMODELS.push([
    TelegramViewModel,

    // e.g. loginStateViewModel, settingsViewModel, ...
    ['settingsViewModel'],

    // e.g. #settings_plugin_telegram, #tab_plugin_telegram, ...
    ['#settings_plugin_telegram', '#wizard_plugin_telegram']
  ])
})
