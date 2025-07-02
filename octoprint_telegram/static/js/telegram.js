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

    self.cmdCnt = 1
    self.msgCnt = 1
    self.reloadPending = 0
    self.reloadUsr = ko.observable(false)
    self.connection_state_str = ko.observable('Unknown')
    self.isloading = ko.observable(false)
    self.errored = ko.observable(false)
    self.token_state_str = ko.observable('Unknown')
    self.setCommandList_state_str = ko.observable('')
    self.editChatDialog = undefined
    self.varInfoDialog = undefined
    self.emoInfoDialog = undefined
    self.mupInfoDialog = undefined
    self.timeInfoDialog = undefined
    self.currChatID = 'Unknown'
    self.currChatTitle = ko.observable('Unknown')
    self.bind_cmd = {}
    self.markupFrom = []
    self.onBindLoad = false

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

    self.requestBindings = function () {
      self.isloading(true)
      OctoPrint.simpleApiGet(self.pluginIdentifier, {
        data: { bindings: true }
      }).done((response) => self.fromBindings(response))
    }

    self.fromBindings = function (response) {
      self.bind = {}
      self.bind.commands = response.bind_cmd
      self.bind.notifications = response.bind_msg
      self.bind.no_setting = response.no_setting
      self.bind.bind_text = response.bind_text

      self.onBindLoad = true
      $('#telegram_msg_list').empty()
      const keys = self.bind.notifications.sort()
      for (const id in keys) {
        let bind_text = ''
        if (keys[id] in self.bind.bind_text) {
          bind_text = '<span class="muted"><br /><small>Also for:'
          const ks = self.bind.bind_text[keys[id]].sort()
          for (const k in ks) { bind_text += '<br>' + ks[k] }
          bind_text += '</small></span>'
        }

        const btnImg = `
          <div class="switch-container" style="margin: 5px 0;">
            <label class="switch-label" style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer;">
              <span>&#x1F4F7; Send with image</span>
              <input
                type="checkbox"
                style="display:none"
                class="switch-input"
                data-bind="checked: settings.settings.plugins.telegram.messages.${keys[id]}.image"
              />
              <span class="switch-slider"></span>
            </label>
          </div>
        `

        const btnGif = `
          <div class="switch-container" style="margin: 5px 0;">
            <label
              class="switch-label"
              style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer;"
              data-bind="attr: {
                title: !settings.settings.plugins.telegram.send_gif() ? 'Enable \\'Send gif\\' globally to use this option' : null
              }"
            >
              <span>&#x1F3A5; Send with gif</span>
              <input
                type="checkbox"
                style="display:none"
                class="switch-input"
                data-bind="
                  checked: settings.settings.plugins.telegram.messages.${keys[id]}.gif,
                  enable: settings.settings.plugins.telegram.send_gif,
                "
              />
              <span class="switch-slider"></span>
            </label>
          </div>
        `

        const btnSilent = `
          <div class="switch-container" style="margin: 5px 0;">
            <label class="switch-label" style="display: inline-flex; align-items: center; gap: 8px; cursor: pointer;">
              <span>&#128263; Send silently</span>
              <input
                type="checkbox"
                style="display:none"
                class="switch-input"
                data-bind="checked: settings.settings.plugins.telegram.messages.${keys[id]}.silent"
              />
              <span class="switch-slider"></span>
            </label>
          </div>
        `

        const currentMarkup = self.settings.settings.plugins.telegram.messages[keys[id]].markup() || 'off'
        self.markupFrom[self.msgCnt] = currentMarkup

        const btnMarkupGrp = `
          <span>
            <span>Markup Selection</span><br>
            <span class="btn-group" data-toggle="buttons-radio">
              <button
                type="button"
                class="btn btn-mini${currentMarkup === 'off' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${self.msgCnt}','off','${keys[id]}')"
              >Off</button>
              <button
                type="button"
                class="btn btn-mini${currentMarkup === 'HTML' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${self.msgCnt}','HTML','${keys[id]}')"
              >HTML</button>
              <button
                type="button"
                class="btn btn-mini${currentMarkup === 'Markdown' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${self.msgCnt}','Markdown','${keys[id]}')"
              >Markdown</button>
              <button
                type="button"
                class="btn btn-mini${currentMarkup === 'MarkdownV2' ? ' active' : ''}"
                data-bind="click: toggleMarkup.bind($data,'${self.msgCnt}','MarkdownV2','${keys[id]}')"
              >MarkdownV2</button>
            </span><br>
          </span>
        `

        const msgEdt = `
          <div class="control-group">
            <div class="controls">
              <hr style="margin:0px 0px 0px -90px;">
            </div>
          </div>
          <div id="telegramMsgText${self.msgCnt}" style="margin-bottom: 20px;">
            <label for="textarea${self.msgCnt}" style="display: block; font-weight: bold; margin-bottom: 6px;">
              ${keys[id]}${bind_text}
            </label>
            <textarea
              id="textarea${self.msgCnt}"
              rows="5"
              style="width: 100%; box-sizing: border-box; margin-bottom: 10px;"
              data-bind="value: settings.settings.plugins.telegram.messages.${keys[id]}.text"
            ></textarea>
            <div style="text-align: center;">
              ${btnImg}${btnGif}${btnSilent}${btnMarkupGrp}
            </div>
          </div>
        `

        $('#telegram_msg_list').append(msgEdt)
        ko.applyBindings(self, $('#telegramMsgText' + self.msgCnt++)[0])
      }
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
      }).done((response) => self.testResponse(response))
    }

    self.testResponse = function (response) {
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

    self.setCommandResponse = function (response) {
      self.setCommandList_state_str(response.setMyCommands_state_str)
      self.errored(!response.ok)
      if (!response.ok) {
        $('#CmdteleErrored').removeClass('text-warning')
        $('#CmdteleErrored').addClass('text-error')
      } else {
        $('#CmdteleErrored').removeClass('text-warning')
        $('#CmdteleErrored').addClass('text-success')
      }
    }

    self.setCommandList = function (data, event) {
      $('#CmdteleErrored').addClass('text-warning')
      $('#CmdteleErrored').removeClass('text-danger')
      $('#CmdteleErrored').removeClass('text-sucess')
      self.setCommandList_state_str('Please wait ...')
      const callback = function () {
        OctoPrint.simpleApiCommand(
          self.pluginIdentifier,
          'setCommandList',
          {}
        ).done((response) => self.setCommandResponse(response))
      }
      showConfirmationDialog('Do you really want to set default commands?', callback)
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
        if (data.new) {
          data.newUsr = true
        } else {
          data.newUsr = false
        }
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
      if (data === undefined) return

      // ko.cleanNode($("#telegram-acccmd-chkbox-box")[0]);
      $('#telegram-acccmd-chkbox').empty()
      $('#telegram-acccmd-chkbox').append('<input id="telegram-acccmd-chkbox-box" type="checkbox" data-bind="checked: settings.settings.plugins.telegram.chats[\'' + data.id + '\'][\'accept_commands\']"> Allow to send commands <span class="help-block"><small id="telegram-groupNotify-hint"></small></span>')
      ko.applyBindings(self, $('#telegram-acccmd-chkbox-box')[0])

      // ko.cleanNode($("#telegram-notify-chkbox-box")[0]);
      $('#telegram-notify-chkbox').empty()
      $('#telegram-notify-chkbox').append('<input id="telegram-notify-chkbox-box" type="checkbox" data-bind="checked: settings.settings.plugins.telegram.chats[\'' + data.id + '\'][\'send_notifications\']"> Send notifications<span class="help-block"><small>After enabling this option, the enabled notifications will be received. You have to enable individual notifications by clicking the blue notify button in the list after closing this dialog.</small></span>')
      ko.applyBindings(self, $('#telegram-notify-chkbox-box')[0])

      self.currChatTitle(data.title)
      self.currChatID = data.id

      $('#telegram-groupNotify-hint').empty()
      $('#telegram-user-allowed-chkbox').empty()
      if (!data.private) {
        $('#telegram-groupNotify-hint').append("After enabling this option, EVERY user of this group is allowed to send enabled commands. You have to set permissions for individual commands by clicking the blue command icon in the list after closing this dialog. If 'Allow user commands' is enabled, these users still use their private settings in addition to the group settings.")
        $('#telegram-user-allowed-chkbox').append("<div class=\"control-group\"><div class=\"controls\"><label class=\"checkbox\"><input id=\"telegram-user-allowed-chkbox-box\" type=\"checkbox\" data-bind=\"checked: settings.settings.plugins.telegram.chats['" + data.id + "']['allow_users']\"> Allow user commands <span class=\"help-block\"><small>When this is enabled, users with command access are allowed to send their individual enabled commands from this group. No other user in this group is allowed to send commands.</small></span></label></div></div>")
        ko.applyBindings(self, $('#telegram-user-allowed-chkbox-box')[0])
      } else {
        $('#telegram-groupNotify-hint').append('After enabling this option, you have to set permissions for individual commands by clicking the blue command icon in the list after closing this dialog.')
        $('#telegram-user-allowed-chkbox').append("<input id=\"telegram-user-allowed-chkbox-box\" style=\"display:none\" type=\"checkbox\" data-bind=\"checked: settings.settings.plugins.telegram.chats['" + data.id + "']['allow_users']\"> ")
        ko.applyBindings(self, $('#telegram-user-allowed-chkbox-box')[0])
      }

      self.editChatDialog.modal('show')
    }

    self.showEditCmdDialog = function (data, option) {
      if (data === undefined) return
      self.currChatTitle('Edit ' + option + ': ' + data.title)
      for (self.cmdCnt; self.cmdCnt > 0; self.cmdCnt--) { $('#telegram-cmd-chkbox' + (self.cmdCnt - 1)).remove() }
      const keys = self.bind[option].sort()
      for (const id in keys) {
        if (self.bind.no_setting.indexOf(keys[id]) < 0) {
          $('#telegram-cmd-chkbox-grp').append('<span id="telegram-cmd-chkbox' + self.cmdCnt + '"><label class="checkbox"><input  type="checkbox" data-bind="checked: settings.settings.plugins.telegram.chats[\'' + data.id + '\'][\'' + option + '\'][\'' + keys[id] + '\']"> <span>' + keys[id] + '</span><label></span>')
          ko.applyBindings(self, $('#telegram-cmd-chkbox' + self.cmdCnt++)[0])
        }
      }
      $('#tele-edit-control-label').empty()
      if (option === 'commands') { $('#tele-edit-control-label').append('<strong>Allowed commands:</strong>') } else { $('#tele-edit-control-label').append('<strong>Get Notification at...</strong>') }
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
      self.requestBindings()
      self.testToken()
      self.editChatDialog = $('#settings-telegramDialogEditChat')
      self.editCmdDialog = $('#settings-telegramDialogEditCommands')
      self.varInfoDialog = $('#settings-telegramDialogVarInfo')
      self.emoInfoDialog = $('#settings-telegramDialogEmoInfo')
      self.mupInfoDialog = $('#settings-telegramDialogMupInfo')
      self.timeInfoDialog = $('#settings-telegramDialogTimeInfo')
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
