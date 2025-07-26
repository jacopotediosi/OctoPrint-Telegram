/*
 * View model for OctoPrint-Telegram
 *
 * Author: Jacopo Tediosi, Fabian Schlenz
 * License: AGPLv3
 */

/* global $, _, ko, OctoPrint, OCTOPRINT_VIEWMODELS, showConfirmationDialog, ItemListHelper, moment */
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
          const aTitle = (a.title || '').toLocaleLowerCase()
          const bTitle = (b.title || '').toLocaleLowerCase()
          return aTitle.localeCompare(bTitle)
        }
      },
      {},
      'title',
      [],
      [],
      999
    )

    self.connection_state_str = ko.observable('Unknown')
    self.token_state_str = ko.observable('Unknown')
    self.errored = ko.observable(false)

    self.currChatID = 'Unknown'
    self.currChatTitle = ko.observable('Unknown')
    self.bind_cmd = {}
    self.markupFrom = []
    self.requirements = ko.observable({})

    self.isChatsTableLoading = ko.observable(false)
    self.isTestingToken = ko.observable(false)
    self.onBindLoad = false

    self.enrollmentCountdownRemaining = ko.observable(0)
    self.enrollmentCountdownInterval = undefined

    self.editChatDialog = undefined
    self.varInfoDialog = undefined
    self.emoInfoDialog = undefined
    self.mupInfoDialog = undefined
    self.timeInfoDialog = undefined
    self.proxyInfoDialog = undefined

    self.requestData = function () {
      OctoPrint.simpleApiGet(self.pluginIdentifier).done(
        (response) => self.fromResponse(response)
      )
    }

    self.requestRequirements = function () {
      OctoPrint.simpleApiGet(self.pluginIdentifier + '?requirements')
        .done((response) => {
          self.requirements(response)
        })
    }

    self.requestBindings = function () {
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
      $('#telegram-settings-msg-list').empty()

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
        $('#telegram-settings-msg-list').append(msgListEntry)
        ko.applyBindings(self, $('#telegramMsgText' + index)[0])
      })

      self.onBindLoad = false
    }

    self.toggleMarkup = function (data, sender, msg) {
      if (self.onBindLoad) return

      if (self.markupFrom[data] !== sender) {
        $('#' + sender + data).toggleClass('active')
        $('#' + self.markupFrom[data] + data).toggleClass('active')
        self.settings.settings.plugins.telegram.messages[msg].markup(sender)
        self.markupFrom[data] = sender
      }
    }

    self.updateChat = function (data) {
      OctoPrint.simpleApiCommand(
        self.pluginIdentifier,
        'editUser',
        {
          chat_id: self.currChatID,
          accept_commands: $('#telegram-acccmd-chkbox-box').prop('checked'),
          send_notifications: $('#telegram-notify-chkbox-box').prop('checked'),
          allow_users: $('#telegram-user-allowed-chkbox-box').prop('checked')
        }
      ).done(function () {
        self.requestData()
        self.editChatDialog.modal('hide')
      })
    }

    self.testToken = function (token) {
      self.isTestingToken(true)
      OctoPrint.simpleApiCommand(self.pluginIdentifier, 'testToken', {
        token
      }).done((response) => self.fromTestToken(response))
    }

    self.fromTestToken = function (response) {
      if (!response) return

      self.token_state_str(response.connection_state_str)
      self.errored(!response.ok)
      self.isTestingToken(false)
      if (!response.ok) {
        $('#telegram-settings-token-state').addClass('text-error')
        $('#telegram-settings-token-state').removeClass('text-success')
        $('#telegram-wizard-token-state').addClass('text-error')
        $('#telegram-wizard-token-state').removeClass('text-success')
      } else {
        $('#telegram-settings-token-state').addClass('text-success')
        $('#telegram-settings-token-state').removeClass('text-error')
        $('#telegram-wizard-token-state').addClass('text-success')
        $('#telegram-wizard-token-state').removeClass('text-error')
      }
    }

    self.fromResponse = function (response) {
      if (!response) return

      if (Object.prototype.hasOwnProperty.call(response, 'connection_state_str')) {
        self.connection_state_str(response.connection_state_str)
      }
      if (Object.prototype.hasOwnProperty.call(response, 'connection_ok')) {
        // self.errored(!response.connection_ok);
      }

      const entries = response.chats
      if (!entries) return

      self.updateChatsTable(entries)
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
      $('#telegram-cmddialog-control-label').html(`<strong>${labelText}</strong>`)

      const keyLabel = option === 'commands' ? 'Command' : 'Event'
      $('#telegram-cmddialog-key-header').text(keyLabel)

      $('#telegram-cmddialog-tbody').empty()

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

        const $element = $(checkboxHtml).appendTo('#telegram-cmddialog-tbody')
        ko.applyBindings(self, $element[0])
      })

      $('#telegram-cmddialog-enable-all').off('click').on('click', function () {
        const chat = self.settings.settings.plugins.telegram.chats[data.id][option]
        for (const key in chat) {
          if (Object.prototype.hasOwnProperty.call(chat, key)) {
            chat[key](true)
          }
        }
      })
      $('#telegram-cmddialog-disable-all').off('click').on('click', function () {
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
      if (!data || !data.id) return

      const title = _.escape(data.title || 'this chat')
      const message = `Do you really want to delete ${title}?`

      showConfirmationDialog(message, function () {
        OctoPrint.simpleApiCommand(
          self.pluginIdentifier,
          'delChat',
          { chat_id: data.id }
        ).done(self.fromResponse)
      })
    }

    self.onWizardShow = function () {
      self.requestRequirements()
    }

    self.onSettingsShown = function () {
      self.requestData()
      self.requestRequirements()
      self.requestBindings()

      self.testToken($('#telegram-settings-token').val())

      self.fetchEnrollmentCountdownRemaining(function (remaining) {
        if (remaining > 0) {
          self.startEnrollmentCountdown(remaining)
        }
      })

      self.editChatDialog = $('#settings-telegramDialogEditChat')
      self.editCmdDialog = $('#settings-telegramDialogEditCommands')
      self.varInfoDialog = $('#settings-telegramDialogVarInfo')
      self.emoInfoDialog = $('#settings-telegramDialogEmoInfo')
      self.mupInfoDialog = $('#settings-telegramDialogMupInfo')
      self.timeInfoDialog = $('#settings-telegramDialogTimeInfo')
      self.proxyInfoDialog = $('#settings-telegramDialogProxyInfo')
    }

    self.isNumeric = function (value) {
      return /^-?\d+(\.\d+)?$/.test(value)
    }

    self.onSettingsBeforeSave = function () {
      // Ensure numeric settings are valid numbers; if not, reset them to 0
      const pluginSettings = self.settings.settings.plugins.telegram
      const numericFields = [
        'notification_height',
        'notification_time',
        'message_at_print_done_delay',
        'PreImgDelay',
        'PostImgDelay'
      ]
      numericFields.forEach(field => {
        const observable = pluginSettings[field]
        if (!self.isNumeric(observable())) {
          observable(0)
        }
      })
    }

    self.onDataUpdaterPluginMessage = function (plugin, data) {
      if (plugin !== self.pluginIdentifier || !data || !data.type) return

      switch (data.type) {
        case 'enrollment_countdown': {
          const remaining = data.remaining
          if (remaining > 0) {
            self.startEnrollmentCountdown(remaining)
          } else {
            self.stopEnrollmentCountdown()
          }
          break
        }

        case 'update_known_chats': {
          self.updateChatsTable(data.chats)
          break
        }
      }
    }

    self.updateChatsTable = function (incomingChats) {
      const existingChats = self.settings.settings.plugins.telegram.chats

      self.isChatsTableLoading(true)

      function createObservableRecursive (obj) {
        if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
          return ko.observable(obj)
        }

        const observableObj = {}
        for (const [key, value] of Object.entries(obj)) {
          observableObj[key] = createObservableRecursive(value)
        }
        return observableObj
      }

      for (const [id, newChat] of Object.entries(incomingChats)) {
        if (!existingChats[id]) {
          existingChats[id] = createObservableRecursive(newChat)
        } else {
          if ('image' in newChat && existingChats[id].image) {
            existingChats[id].image(newChat.image)
          }
          if ('title' in newChat && existingChats[id].title) {
            existingChats[id].title(newChat.title)
          }
        }
      }

      for (const id of Object.keys(existingChats)) {
        if (!(id in incomingChats)) {
          delete existingChats[id]
        }
      }

      const newChatsItems = Object.entries(existingChats)
        .filter(([id]) => id !== 'zBOTTOMOFCHATS')
        .map(([id, chat]) => {
          const item = { id }
          for (const [key, observable] of Object.entries(chat)) {
            item[key] = ko.isObservable(observable) ? observable() : observable
          }
          return item
        })

      self.chatListHelper.updateItems(newChatsItems)

      self.isChatsTableLoading(false)
    }

    self.fetchEnrollmentCountdownRemaining = function (callback) {
      OctoPrint.simpleApiGet(self.pluginIdentifier + '?enrollmentCountdown')
        .done(function (response) {
          callback(response.remaining)
        })
    }

    self.toggleEnrollmentCountdown = function () {
      if (self.enrollmentCountdownRemaining() > 0) {
        OctoPrint.simpleApiCommand(self.pluginIdentifier, 'stopEnrollmentCountdown', {})
      } else {
        OctoPrint.simpleApiCommand(self.pluginIdentifier, 'startEnrollmentCountdown', {})
      }
    }

    self.startEnrollmentCountdown = function (duration) {
      self.enrollmentCountdownRemaining(duration)

      clearInterval(self.enrollmentCountdownInterval)

      self.enrollmentCountdownInterval = setInterval(function () {
        const current = self.enrollmentCountdownRemaining()
        if (current <= 1) {
          self.stopEnrollmentCountdown()
        } else {
          self.enrollmentCountdownRemaining(current - 1)
        }
      }, 1000)
    }

    self.stopEnrollmentCountdown = function () {
      self.enrollmentCountdownRemaining(0)
      clearInterval(self.enrollmentCountdownInterval)
    }

    self.enrollmentCountdownButtonText = ko.pureComputed(function () {
      const remaining = self.enrollmentCountdownRemaining()
      if (remaining <= 0) {
        const warningEmoji = String.fromCodePoint(0x26A0, 0xFE0F)
        return `${warningEmoji} Enable`
      }

      const timerEmoji = String.fromCodePoint(0x23F1, 0xFE0F)
      const duration = moment.duration(remaining, 'seconds')
      const formatted = moment.utc(duration.asMilliseconds()).format('m:ss')

      return `Disable (${timerEmoji} ${formatted})`
    })

    // Reveal password buttons
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

  // View model class, parameters for constructor, containers to bind to
  OCTOPRINT_VIEWMODELS.push({
    construct: TelegramViewModel,
    dependencies: ['settingsViewModel'],
    elements: ['#settings_plugin_telegram', '#wizard_plugin_telegram']
  })
})
