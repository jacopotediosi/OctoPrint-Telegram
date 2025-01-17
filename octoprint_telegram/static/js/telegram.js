/*
 * View model for OctoPrint-Telegram
 *
 * Author: Fabian Schlenz
 * License: AGPLv3
 */
$(function() {
    function TelegramViewModel(parameters) {
        var self = this;

        // assign the injected parameters, e.g.:
        // self.loginStateViewModel = parameters[0];
        self.settings = parameters[0];
        //else
         //   self.settings=self.settings;
        console.log(String(self.settings));

        // TODO: Implement your plugin's view model here.
        
        self.chatListHelper = new ItemListHelper(
            "known_chats",
            {
                "title": function(a, b) {
                    if(a.title.toLocaleLowerCase() < b.title.toLocaleLowerCase()) return -1;
                    if(a.title.toLocaleLowerCase() > b.title.toLocaleLowerCase()) return 1;
                    return 0;
                }
            },
            {},
            "title",
            [],
            [],
            999);

        self.cmdCnt = 1;
        self.msgCnt = 1;
        self.reloadPending = 0;
        self.reloadUsr = ko.observable(false);
        self.connection_state_str = ko.observable("Unknown");
        self.isloading = ko.observable(false);
        self.errored = ko.observable(false);
        self.token_state_str = ko.observable("Unknown");
        self.setCommandList_state_str = ko.observable("");
    	self.editChatDialog = undefined;  
        self.varInfoDialog = undefined;      
        self.emoInfoDialog = undefined;
        self.mupInfoDialog = undefined;  
        self.timeInfoDialog = undefined;  
    	self.currChatID = "Unknown";
        self.currChatTitle = ko.observable("Unknown");
        self.bind_cmd = {}; 
        self.markupFrom = [];
        self.onBindLoad = false;
    
        self.requestData = function(ignore,update) {

            ignore = typeof ignore !== 'undefined' ? ignore : false;
            update = typeof update !== 'undefined' ? update : false;

            if (update)
                urlPath = "plugin/telegram?id="+self.currChatID+"&cmd="+$('#telegram-acccmd-chkbox-box').prop( "checked" )+"&note="+$('#telegram-notify-chkbox-box').prop( "checked" )+"&allow="+$('#telegram-user-allowed-chkbox-box').prop( "checked" );
            else
                urlPath = "plugin/telegram";
            if(self.reloadUsr() || ignore){
                self.isloading(true);
                $.ajax({
                    url: API_BASEURL + urlPath,
                    type: "GET",
                    dataType: "json",
                    success: self.fromResponse
                });
                
               if(!ignore) self.reloadPending = setTimeout(self.requestData,20000);
            }
            else
                self.reloadPending = setTimeout(self.requestData,500);
        };

        self.requestBindings = function() {
            self.isloading(true);
            $.ajax({
                url: API_BASEURL + "plugin/telegram?bindings=true",
                type: "GET",
                dataType: "json",
                success: self.fromBindings
            });      
        };

        self.fromBindings = function(response){
            self.bind = {}
            self.bind["commands"] = response.bind_cmd;
            self.bind["notifications"] = response.bind_msg;
            self.bind['no_setting'] = response.no_setting;
            self.bind['bind_text'] = response.bind_text;
            var ShowGifBtn = self.settings.settings.plugins.telegram.send_gif()
            var ShowGifBtn = self.settings.settings.plugins.telegram.send_gif()

            if (ShowGifBtn)
            {
                $('.gif-options').toggle();
            }

            
            
            if (ShowGifBtn)
            {
                $('.gif-options').toggle();
            }

            self.onBindLoad = true;
            $("#telegram_msg_list").empty();
            keys = self.bind["notifications"].sort();
            for(var id in keys) {
                bind_text = '';
                if(keys[id] in self.bind['bind_text']){
                    bind_text = '<span class="muted"><br /><small>Also for:';
                    ks = self.bind['bind_text'][keys[id]].sort();
                    for (var k in ks)
                        bind_text += "<br>" + ks[k];
                    bind_text += "</small></span>";
                }
                img = "camera";
                hideMup = "";
                hideComb = "";
                if(self.settings.settings.plugins.telegram.messages[keys[id]].image()){
                    img = "camera";
                    btn = "success";
                    txt = "Send Image";
                    hideMup = "display:none";
                    hideComb = "";
                }
                else{
                    img = "ban-circle";
                    btn = "warning";
                    txt = "No Image";
                    hideMup = "";
                    hideComb = "display:none"
                }

                if(self.settings.settings.plugins.telegram.messages[keys[id]].silent()) {
                  imgSilent = "volume-off";
                  bSilent = "warning";
                  txtSilent = "Silent";
                  hideMup = "";
                  hideComb = "";
                } else{
                  imgSilent = "volume-up";
                  bSilent = "success";
                  txtSilent = "Notification";
                  hideMup = "";
                  hideComb = ""
                }
                if(self.settings.settings.plugins.telegram.messages[keys[id]].gif()){
                    imgGif = "camera";
                    bGif = "success";
                    txtGif = "Send Gif";
                    hideMup = "";
                    hideComb = "";
                }
                else{
                    imgGif = "ban-circle";
                    bGif = "warning";
                    txtGif = "No Gif";
                    hideMup = "";
                    hideComb = ""
                }
                if (ShowGifBtn)
                {
                    showGif = ""
                }
                else
                {
                    showGif = "display:none"
                }
                // TODO set to second message setting
                if(self.settings.settings.plugins.telegram.messages[keys[id]].combined()){
                    img2 = "comment";
                    btn2 = "danger";
                    txt2 = "Combined";
                    if(hideComb === "")
                        hideMup = "display:none";
                }
                else{
                    img2 = "comments";
                    btn2 = "info";
                    txt2 = "Separated";
                    hideMup = "";
                }
                if(self.settings.settings.plugins.telegram.messages[keys[id]].markup()==="HTML"){
                    bOff = "info";
                    bHtml = "danger active";
                    bMd = "info";
                    self.markupFrom[self.msgCnt] = 'HTML';
                }
                else if(self.settings.settings.plugins.telegram.messages[keys[id]].markup()==="Markdown"){
                    bOff = "info";
                    bHtml = "info";
                    bMd = "danger active";
                    self.markupFrom[self.msgCnt] = 'Markdown';
                }
                else{
                    bOff = "danger active"
                    bHtml = "info"
                    bMd = "info"
                    self.markupFrom[self.msgCnt] = 'off';
                }
                var btnGrp = '<span id="mupBut'+self.msgCnt+'" style="' + hideMup + '"><span class="muted"><small>Markup Selection<br></small></span><span class="btn-group" data-toggle="buttons-radio">';
                btnGrp += '<button id="off'+self.msgCnt+'" type="button" class="btn btn-'+bOff+' btn-mini" data-bind="click: toggleMarkup.bind($data,\''+self.msgCnt+'\',\'off\',\''+keys[id]+'\')">Off</button>';
                btnGrp += '<button id="HTML'+self.msgCnt+'" type="button" class="btn btn-'+bHtml+' btn-mini" data-bind="click: toggleMarkup.bind($data,\''+self.msgCnt+'\',\'HTML\',\''+keys[id]+'\')">HTML</button>';
                btnGrp += '<button id="Markdown'+self.msgCnt+'" type="button" class="btn btn-'+bMd+' btn-mini" data-bind="click: toggleMarkup.bind($data,\''+self.msgCnt+'\',\'Markdown\',\''+keys[id]+'\')">MD</button>';
                btnGrp += '</span><br></span>';

                var btnImg = '<span class="muted"><small>Send with image?<br></small></span>';
                btnImg += '<label id="chkBtn'+self.msgCnt+'" class="btn btn-'+btn+' btn-mini" title="Toggle \'Send with image\'">';
                btnImg += '<input type="checkbox" style="display:none" data-bind="checked: settings.settings.plugins.telegram.messages.'+keys[id]+'.image, click: toggleImg(\''+self.msgCnt+'\')"/>';
                btnImg += '<i id="chkImg'+self.msgCnt+'" class="icon-'+img+'"></i> ';
                btnImg += '<span id="chkTxt'+self.msgCnt+'">'+txt+'</span></label><br>';

                var btnSilent = '<span class="muted"><small>Send silently?<br></small></span>';
                btnSilent += '<label id="chkSilentBtn'+self.msgCnt+'" class="btn btn-'+bSilent+' btn-mini" title="Toggle \'Silence\'">';
                btnSilent += '<input type="checkbox" style="display:none" data-bind="checked: settings.settings.plugins.telegram.messages.'+keys[id]+'.silent, click: toggleSilent(\''+self.msgCnt+'\')"/>';
                btnSilent += '<i id="chkSilent'+self.msgCnt+'" class="icon-'+imgSilent+'"></i> ';
                btnSilent += '<span id="chkSilentTxt'+self.msgCnt+'">'+txtSilent+'</span></label><br>';

                var btnGif = '<span class="muted" id="chkGifLbl'+self.msgCnt+'" style="' + showGif + '" ><small>Send with gif?<br></small></span>';
                btnGif += '<label id="chkGifBtn'+self.msgCnt+'"  style="' + showGif + '" class="btn btn-'+bGif+' btn-mini" title="Toggle \'Send with gif\'">';
                btnGif += '<input type="checkbox" style="display:none" data-bind="checked: settings.settings.plugins.telegram.messages.'+keys[id]+'.gif, click: toggleGif(\''+self.msgCnt+'\')"/>';
                btnGif += '<i id="chkGif'+self.msgCnt+'"  style="' + showGif + '" class="icon-'+imgGif+'"></i> ';
                btnGif += '<span id="chkGifTxt'+self.msgCnt+'"  style="' + showGif + '">'+txtGif+'</span></label><br>';

                var btnSecMsg = '<span id="combBut'+self.msgCnt+'" style="' + hideComb + '"> <span class="muted"><small>Combined message?<br></small></span>';
                btnSecMsg += '<label id="chk2Btn'+self.msgCnt+'" class="btn btn-'+btn2+' btn-mini" title="Toggle \'Send image in a second message\'">';
                btnSecMsg += '<input type="checkbox" style="display:none" data-bind="checked: settings.settings.plugins.telegram.messages.'+keys[id]+'.combined, click: toggleImg2(\''+self.msgCnt+'\')"/>';
                btnSecMsg += '<i id="chk2Img'+self.msgCnt+'" class="icon-'+img2+'"></i> ';
                btnSecMsg += '<span id="chk2Txt'+self.msgCnt+'">'+txt2+'</span></label><br></span>';

                var msgEdt = '<div class="control-group"><div class="controls " ><hr style="margin:0px 0px 0px -90px;"></div></div><div class="control-group" id="telegramMsgText'+self.msgCnt+'">';
                    msgEdt += '<label class="control-label"><strong>'+keys[id]+ '</strong>'+bind_text + '</label>';
                    msgEdt += '<div class="controls " >';
                        msgEdt += '<div class="row">';
                            msgEdt += '<div class="span9"><textarea rows="4" style="margin-left:7px;" class="block" data-bind="value: settings.settings.plugins.telegram.messages.'+keys[id]+'.text"></textarea></div>';
                            msgEdt += '<div class="span3" style="text-align:center;">' + btnImg + btnGif + btnSecMsg + btnSilent + btnGrp + '</div>';
                        msgEdt += '</div></div></div>';

                $('#telegram_msg_list').append(msgEdt);
                ko.applyBindings(self, $("#telegramMsgText"+self.msgCnt++)[0]);
            }
            self.isloading(false);
            $('#chkImg0').removeClass("icon-camera");
            $('#chkImg0').removeClass("icon-ban-circle");
            $('#chkGif0').removeClass("icon-camera");
            $('#chkGif0').removeClass("icon-ban-circle");
            $('#chkBtn0').removeClass("btn-success");
            $('#chkBtn0').removeClass("btn-warning");
            $('#chkTxt0').text("");
            $('#chkGifBtn0').removeClass("btn-success");
            $('#chkGifBtn0').removeClass("btn-warning");
            $('#chkGifTxt0').text("");
            if(self.settings.settings.plugins.telegram.image_not_connected()){
                $('#chkImg0').addClass("icon-camera");
                $('#chkBtn0').addClass("btn-success");
                $('#chkTxt0').text("Send Image");
            }
            else{
                $('#chkImg0').addClass("icon-ban-circle");
                $('#chkBtn0').addClass("btn-warning");
                $('#chkTxt0').text("No Image");
            }
            /*if(self.settings.settings.plugins.telegram.gif_not_connected()){
                $('#chkGif0').addClass("icon-camera");
                $('#chkGifBtn0').addClass("btn-success");
                $('#chkGifTxt0').text("Send Gif");
            }
            else{
                $('#chkGif0').addClass("icon-ban-circle");
                $('#chkGifBtn0').addClass("btn-warning");
                $('#chkGifTxt0').text("No Gif");
            }*/
            
            self.onBindLoad = false;
        }


        self.toggleMarkup = function(data,sender,msg){
            if(!self.onBindLoad){
                if(self.markupFrom[data] !== sender){
                    $('#'+sender+data).toggleClass("btn-info btn-danger");
                    $('#'+self.markupFrom[data]+data).toggleClass("btn-info btn-danger");
                    self.settings.settings.plugins.telegram.messages[msg].markup(sender);
                }
                self.markupFrom[data] = sender;
            }
        }


        self.toggleImg = function(data){
            if(!self.onBindLoad){
                $('#chkImg'+data).toggleClass("icon-ban-circle icon-camera");
                $('#chkBtn'+data).toggleClass("btn-success btn-warning");
                if($('#chkTxt'+data).text()==="Send Image"){
                    $('#chkTxt'+data).text("No Image");
                    if(data !== "0"){
                        $('#mupBut'+data).show();
                        $('#combBut'+data).hide();
                    }
                }
                else{
                    $('#chkTxt'+data).text("Send Image");
                    if(data !== "0"){
                        if($('#chk2Txt'+data).text()==="Combined")
                            $('#mupBut'+data).hide();    
                        else
                            $('#mupBut'+data).show();   
                    
                        $('#combBut'+data).show();
                    }
                }
            }
        }

        self.toggleSilent = function(data){
          if(!self.onBindLoad){
              $('#chkSilent'+data).toggleClass("icon-volume-off icon-volume-up");
              $('#chkSilentBtn'+data).toggleClass("btn-success btn-warning");
              if($('#chkSilentTxt'+data).text()==="Silent"){
                  $('#chkSilentTxt'+data).text("Notification");
              }
              else{
                  $('#chkSilentTxt'+data).text("Silent");
              }
          }
      }

        self.toggleGif = function(data){
            if(!self.onBindLoad){
                $('#chkGif'+data).toggleClass("icon-ban-circle icon-camera");
                $('#chkGifBtn'+data).toggleClass("btn-success btn-warning");
                $('#lblGifwar'+data).toggle();
                if($('#chkGifTxt'+data).text()==="Send Gif"){
                    $('#chkGifTxt'+data).text("No Gif");
                }
                else{
                    $('#chkGifTxt'+data).text("Send Gif");
                    
                }
            }
        }

        self.toggleGifGen = function(){
            if(!self.onBindLoad){
                $('[id*="chkGifBtn"]').toggle();
                $('[id*="chkGifTxt"]').toggle();
                $('[id*="chkGifLbl"]').toggle();
                $('.gif-options').toggle();
            }
        }
        

        self.toggleImg2 = function(data){
            if(!self.onBindLoad){
                $('#chk2Img'+data).toggleClass("icon-comment icon-comments");
                $('#chk2Btn'+data).toggleClass("btn-info btn-danger");
                if($('#chk2Txt'+data).text()==="Separated"){
                    $('#chk2Txt'+data).text("Combined"); 
                    $('#mupBut'+data).hide();   
                }
                else{
                    $('#chk2Txt'+data).text("Separated");  
                    $('#mupBut'+data).show();
                }
            }
        }

        self.updateChat = function(data) {
            self.requestData(true,true);
            self.editChatDialog.modal("hide");
        }
    
        self.testToken = function(data, event) {
            self.isloading(true);
            console.log("Testing token " + $('#settings_plugin_telegram_token').val());
            $.ajax({
                url: API_BASEURL + "plugin/telegram",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({ "command": "testToken", "token": $('#settings_plugin_telegram_token').val()}),
                contentType: "application/json",
                success: self.testResponse
            });
        }
        
        self.testResponse = function(response) {
            self.isloading(false);
            self.token_state_str(response.connection_state_str);
            self.errored(!response.ok);
            if(!response.ok){
                $('#teleErrored').addClass("text-error");
                $('#teleErrored').removeClass("text-success");
                $('#teleErrored2').addClass("text-error");
                $('#teleErrored2').removeClass("text-success");
            }
            else{
                $('#teleErrored').addClass("text-success");
                $('#teleErrored').removeClass("text-error");
                $('#teleErrored2').addClass("text-success");
                $('#teleErrored2').removeClass("text-error");
            }

        }

        self.setCommandResponse = function(response) {
            self.setCommandList_state_str(response.setMyCommands_state_str);
            self.errored(!response.ok);
            if(!response.ok){
                $('#CmdteleErrored').removeClass("text-warning");
                $('#CmdteleErrored').addClass("text-error");
            }
            else{
                $('#CmdteleErrored').removeClass("text-warning");
                $('#CmdteleErrored').addClass("text-success");
            }

        }

        self.setCommandList = function(data, event) {
            console.log("StartSetCommandList");
            $('#CmdteleErrored').addClass("text-warning"); 
            $('#CmdteleErrored').removeClass("text-danger"); 
            $('#CmdteleErrored').removeClass("text-sucess"); 
            self.setCommandList_state_str("Please wait ...")
            var callback = function() {
                $.ajax({ 
                    url: API_BASEURL + "plugin/telegram",
                    type: "POST",
                    dataType: "json",
                    data: JSON.stringify({ "command": "setCommandList", "force": 'True'}),
                    contentType: "application/json",
                    success: self.setCommandResponse
                });
            };
            showConfirmationDialog('Do you really want to set default commands ', function (e) {
                callback();
            });
        }
        
        self.fromResponse = function(response) {
            if(response === undefined) return;
            if(response.hasOwnProperty("connection_state_str"))
                self.connection_state_str(response.connection_state_str);
            if(response.hasOwnProperty("connection_ok"))
                //self.errored(!response.connection_ok);
            var entries = response.chats;
            if (entries === undefined) return;
            var array = [];
            var formerChats = _.pluck(self.chatListHelper.allItems, 'id');
            var currentChats = [];
            var newChats = false;
            for(var id in entries) {
                var data = entries[id];
                data['id'] = id;
                data['image'] = data['image'];
                if(data['new']) {
                    data['newUsr'] = true;
                } else {
                    data['newUsr'] = false;
                }
                array.push(data);
                currentChats.push(id);
                newChats = newChats || !_.includes(formerChats, id);
            }

            var deletedChatIds = _.difference(formerChats, currentChats);
            if (newChats || (deletedChatIds && deletedChatIds.length)) {
                // Transfer the chats back to the server settings (because just hitting "save" on the Settings dialog
                // won't transfer anything we haven't explicitely set).

                // TODO: This whole workflow should be optimized!
                // Currently it takes two full server/client round trips to get the chats in sync, and just reusing
                // the plugin's API for that purpose would probably be way way more efficient and less error prone.
                self.settings.saveData({plugins: {telegram: {chats: entries}}});
            }
            self.chatListHelper.updateItems(array);
            self.isloading(false);
        };



        self.showEditChatDialog = function(data) {
            if (data === undefined) return;
            //ko.cleanNode($("#telegram-acccmd-chkbox-box")[0]);
            $("#telegram-acccmd-chkbox").empty();
            $('#telegram-acccmd-chkbox').append('<input id="telegram-acccmd-chkbox-box" type="checkbox" data-bind="checked: settings.settings.plugins.telegram.chats[\''+data['id']+'\'][\'accept_commands\']"> Allow to send commands <span class="help-block"><small id="telegram-groupNotify-hint"></small></span>');
            ko.applyBindings(self, $("#telegram-acccmd-chkbox-box")[0]);

            //ko.cleanNode($("#telegram-notify-chkbox-box")[0]);
            $("#telegram-notify-chkbox").empty();
            $('#telegram-notify-chkbox').append('<input id="telegram-notify-chkbox-box" type="checkbox" data-bind="checked: settings.settings.plugins.telegram.chats[\''+data['id']+'\'][\'send_notifications\']"> Send notifications<span class=\"help-block\"><small>After enabling this option, the enabled notifications will be received. You have to enable individual notifications by clicking the blue notify button in the list after closing this dialog.</small></span>');
            ko.applyBindings(self, $("#telegram-notify-chkbox-box")[0]);

            self.currChatTitle(data.title);
            self.currChatID = data.id;

            $('#telegram-groupNotify-hint').empty();
            $('#telegram-user-allowed-chkbox').empty();
            if(!data.private){
                $('#telegram-groupNotify-hint').append("After enabling this option, EVERY user of this group is allowed to send enabled commands. You have to set permissions for individual commands by clicking the blue command icon in the list after closing this dialog. If 'Allow user commands' is enabled, these users still use their private settings in addition to the group settings.");
                $('#telegram-user-allowed-chkbox').append("<div class=\"control-group\"><div class=\"controls\"><label class=\"checkbox\"><input id=\"telegram-user-allowed-chkbox-box\" type=\"checkbox\" data-bind=\"checked: settings.settings.plugins.telegram.chats['"+data['id']+"']['allow_users']\"> Allow user commands <span class=\"help-block\"><small>When this is enabled, users with command access are allowed to send their individual enabled commands from this group. No other user in this group is allowed to send commands.</small></span></label></div></div>");
                ko.applyBindings(self, $("#telegram-user-allowed-chkbox-box")[0]);
            }
            else{
                $('#telegram-groupNotify-hint').append("After enabling this option, you have to set permissions for individual commands by clicking the blue command icon in the list after closing this dialog.");
                $('#telegram-user-allowed-chkbox').append("<input id=\"telegram-user-allowed-chkbox-box\" style=\"display:none\" type=\"checkbox\" data-bind=\"checked: settings.settings.plugins.telegram.chats['"+data['id']+"']['allow_users']\"> ");
                ko.applyBindings(self, $("#telegram-user-allowed-chkbox-box")[0]);
            }
            
	        self.editChatDialog.modal("show");
        }

        self.showEditCmdDialog = function(data,option) {
            if (data === undefined) return;
            self.currChatTitle("Edit " + option + ": " +data.title);
            for(self.cmdCnt;self.cmdCnt>0;self.cmdCnt--)
                $("#telegram-cmd-chkbox"+(self.cmdCnt-1)).remove();
            keys = self.bind[option].sort();
            for(var id in keys) {
                if( self.bind['no_setting'].indexOf(keys[id]) < 0) {
                    $("#telegram-cmd-chkbox-grp").append('<span id="telegram-cmd-chkbox'+self.cmdCnt+'"><label class="checkbox"><input  type="checkbox" data-bind="checked: settings.settings.plugins.telegram.chats[\''+data['id']+'\'][\''+option+'\'][\''+keys[id]+'\']"> <span>'+keys[id]     +'</span><label></span>');
                    ko.applyBindings(self, $("#telegram-cmd-chkbox"+self.cmdCnt++)[0]);
                }
            }
            $('#tele-edit-control-label').empty();
            if (option == "commands")
                $('#tele-edit-control-label').append("<strong>Allowed commands:</strong>");
            else
                $('#tele-edit-control-label').append("<strong>Get Notification at...</strong>")
            self.editCmdDialog.modal("show");
        }

        self.delChat = function(data) {
            if (data === undefined) return;
            var callback = function() {
                    self.isloading(true);
                    data['command'] = "delChat";
                    data['ID'] = data.id
                    console.log("Delete Chat Data " + String(data['ID']));
                    $.ajax({
                        url: API_BASEURL + "plugin/telegram",
                        type: "POST",
                        dataType: "json",
                        data: JSON.stringify(data),
                        contentType: "application/json",
                        success: self.fromResponse
                    });
                };
            showConfirmationDialog('Do you really want to delete ' + data.title, function (e) {
                callback();
            });
  
        }

        self.onSettingsHidden = function() {
            clearTimeout(self.reloadPending);
        }

        self.onSettingsShown = function() {
            self.requestData(true,false);
            self.requestData();
            self.requestBindings();
            self.testToken();
            self.editChatDialog = $("#settings-telegramDialogEditChat");
            self.editCmdDialog = $("#settings-telegramDialogEditCommands");
            self.varInfoDialog = $('#settings-telegramDialogVarInfo');
            self.emoInfoDialog = $('#settings-telegramDialogEmoInfo');
            self.mupInfoDialog = $('#settings-telegramDialogMupInfo');
            self.timeInfoDialog = $('#settings-telegramDialogTimeInfo');
            $('.teleEmojiImg').each( function(){
                $(this).attr('src','/plugin/telegram/static/img/'+$(this).attr('id')+".png")
            });
            
        }

        self.isNumber = function(number) {
            return !isNaN(parseFloat(number)) && isFinite(number);
        }

        self.onSettingsBeforeSave = function() {
	        // Check specific settings to be a number, not a null
	        // In case it's not a number set it to be 0
            var settings = self.settings.settings.plugins.telegram;
            var settings_to_check_number = [
                settings.notification_height,
                settings.notification_time,
                settings.message_at_print_done_delay,
                setting.precommand_delay,
                setting.postcommand_delay
            ];
            for (var i = 0; i < settings_to_check_number.length; i++) {
                if (!self.isNumber(settings_to_check_number[i]())) {
                    settings_to_check_number[i](0);
                }
            }
        }

        self.onServerDisconnect = function(){
            clearTimeout(self.reloadPending);
        }

        self.onDataUpdaterReconnect = function(){
            if(self.reloadUsr())
                self.requestData();
            else
                self.requestData(true,false);
                self.requestData();
            self.requestBindings();
        }

    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        TelegramViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        [ "settingsViewModel" ],

        // e.g. #settings_plugin_telegram, #tab_plugin_telegram, ...
        [ '#settings_plugin_telegram','#wizard_plugin_telegram']
    ]);
});
