# Copyright (C) 2003-2014 Yann Leboulanger <asterix AT lagaule.org>
# Copyright (C) 2004-2005 Vincent Hanquez <tab AT snarc.org>
# Copyright (C) 2005 Alex Podaras <bigpod AT gmail.com>
#                    Norman Rasmussen <norman AT rasmussen.co.za>
#                    Stéphan Kochen <stephan AT kochen.nl>
# Copyright (C) 2005-2006 Dimitur Kirov <dkirov AT gmail.com>
#                         Alex Mauer <hawke AT hawkesnest.net>
# Copyright (C) 2005-2007 Travis Shirk <travis AT pobox.com>
#                         Nikos Kouremenos <kourem AT gmail.com>
# Copyright (C) 2006 Junglecow J <junglecow AT gmail.com>
#                    Stefan Bethge <stefan AT lanpartei.de>
# Copyright (C) 2006-2008 Jean-Marie Traissard <jim AT lapin.org>
# Copyright (C) 2007 Lukas Petrovicky <lukas AT petrovicky.net>
#                    James Newton <redshodan AT gmail.com>
# Copyright (C) 2007-2008 Brendan Taylor <whateley AT gmail.com>
#                         Julien Pivotto <roidelapluie AT gmail.com>
#                         Stephan Erb <steve-e AT h3c.de>
# Copyright (C) 2008 Jonathan Schleifer <js-gajim AT webkeks.org>
#
# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import time
import json
import logging
from functools import partial
from threading import Thread
from datetime import datetime
from importlib.util import find_spec
from packaging.version import Version as V

from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Soup
from nbxmpp import idlequeue
from nbxmpp import Hashes2

from gajim.common import app
from gajim.common import events
from gajim.common.dbus import location
from gajim.common.dbus import logind
from gajim.common.dbus import music_track

from gajim import gui_menu_builder
from gajim.dialog_messages import get_dialog

from gajim.gui.controls.base import BaseControl
from gajim.gui.controls.groupchat import GroupchatControl

from gajim.common import idle
from gajim.common.zeroconf import connection_zeroconf
from gajim.common import proxy65_manager
from gajim.common import socks5
from gajim.common import helpers
from gajim.common import passwords
from gajim.common.helpers import ask_for_status_message
from gajim.common.helpers import get_muc_context
from gajim.common.helpers import get_group_chat_nick
from gajim.common.structs import MUCData
from gajim.common.structs import OutgoingMessage
from gajim.common.nec import NetworkEvent
from gajim.common.nec import NetworkEventsController
from gajim.common.i18n import _
from gajim.common.client import Client
from gajim.common.preview import PreviewManager
from gajim.common.const import Display
from gajim.common.const import JingleState

from gajim.common.file_props import FilesProp
from gajim.common.connection_handlers_events import InformationEvent

from gajim.common import ged
from gajim.common.exceptions import FileError

from gajim.gui.avatar import AvatarStorage
from gajim.gui.notification import Notification
from gajim.gui.dialogs import DialogButton
from gajim.gui.dialogs import ErrorDialog
from gajim.gui.dialogs import WarningDialog
from gajim.gui.dialogs import InformationDialog
from gajim.gui.dialogs import ConfirmationDialog
from gajim.gui.dialogs import InputDialog
from gajim.gui.dialogs import PassphraseDialog
from gajim.gui.filechoosers import FileChooserDialog
from gajim.gui.filetransfer import FileTransfersWindow
from gajim.gui.roster_item_exchange import RosterItemExchangeWindow
from gajim.gui.main import MainWindow
from gajim.gui.util import get_show_in_roster
from gajim.gui.util import get_show_in_systray
from gajim.gui.util import open_window
from gajim.gui.util import get_app_window
from gajim.gui.util import get_app_windows
from gajim.gui.util import get_color_for_account
from gajim.gui.const import ControlType


log = logging.getLogger('gajim.interface')

class Interface:
    def __init__(self):
        app.interface = self
        app.thread_interface = ThreadInterface

        self.pass_dialog = {}

        self.handlers = {}
        self.roster = None

        self.avatar_storage = AvatarStorage()
        self.preview_manager = PreviewManager()

        # Load CSS files
        app.load_css_config()

        for account in app.settings.get_accounts():
            if app.settings.get_account_setting(account, 'is_zeroconf'):
                app.ZEROCONF_ACC_NAME = account
                break

        app.idlequeue = idlequeue.get_idlequeue()
        # resolve and keep current record of resolved hosts
        app.socks5queue = socks5.SocksQueue(
            app.idlequeue,
            self.handle_event_file_rcv_completed,
            self.handle_event_file_progress,
            self.handle_event_file_error)
        app.proxy65_manager = proxy65_manager.Proxy65Manager(app.idlequeue)

        app.nec = NetworkEventsController()
        app.notification = Notification()

        self.create_core_handlers_list()
        self.register_core_handlers()

        # self.create_zeroconf_default_config()
        # if app.settings.get_account_setting(app.ZEROCONF_ACC_NAME, 'active') \
        # and app.is_installed('ZEROCONF'):
        #     app.connections[app.ZEROCONF_ACC_NAME] = \
        #         connection_zeroconf.ConnectionZeroconf(app.ZEROCONF_ACC_NAME)

        for account in app.settings.get_accounts():
            if (not app.settings.get_account_setting(account, 'is_zeroconf') and
                    app.settings.get_account_setting(account, 'active')):
                client = Client(account)
                app.connections[account] = client
                app.ged.register_event_handler(
                    'muc-added', ged.CORE, self._on_muc_added)

        self.instances = {}

        for a in app.connections:
            self.instances[a] = {'infos': {}, 'disco': {}, 'gc_config': {},
                'search': {}, 'sub_request': {}}
            app.contacts.add_account(a)
            app.groups[a] = {}
            app.gc_connected[a] = {}
            app.automatic_rooms[a] = {}
            app.newly_added[a] = []
            app.to_be_removed[a] = []
            app.nicks[a] = app.settings.get_account_setting(a, 'name')
            app.block_signed_in_notifications[a] = True
            app.last_message_time[a] = {}

        if sys.platform not in ('win32', 'darwin'):
            logind.enable()
            music_track.enable()
        else:
            GLib.timeout_add_seconds(20, self.check_for_updates)

        idle.Monitor.set_interval(app.settings.get('autoawaytime') * 60,
                                  app.settings.get('autoxatime') * 60)

        self.systray_enabled = False

        if not app.is_display(Display.WAYLAND):
            from gajim.gui.status_icon import StatusIcon
            self.systray = StatusIcon()

        if sys.platform in ('win32', 'darwin'):
            from gajim.gui.emoji_chooser import emoji_chooser
            emoji_chooser.load()

        self.last_ftwindow_update = 0

        self._network_monitor = Gio.NetworkMonitor.get_default()
        self._network_monitor.connect('notify::network-available',
                                      self._network_status_changed)
        self.network_state = self._network_monitor.get_network_available()

    @staticmethod
    def handle_event_information(obj):
        if not obj.popup:
            return

        if obj.dialog_name is not None:
            get_dialog(obj.dialog_name, *obj.args, **obj.kwargs)
            return

        if obj.level == 'error':
            cls = ErrorDialog
        elif obj.level == 'warn':
            cls = WarningDialog
        elif obj.level == 'info':
            cls = InformationDialog
        else:
            return

        cls(obj.pri_txt, GLib.markup_escape_text(obj.sec_txt))

    @staticmethod
    def raise_dialog(name, *args, **kwargs):
        get_dialog(name, *args, **kwargs)

    @staticmethod
    def handle_event_http_auth(obj):
        # ('HTTP_AUTH', account, (method, url, transaction_id, iq_obj, msg))
        def _response(account, answer):
            obj.conn.get_module('HTTPAuth').build_http_auth_answer(
                obj.stanza, answer)

        account = obj.conn.name
        message = _('HTTP (%(method)s) Authorization '
                    'for %(url)s (ID: %(id)s)') % {
                        'method': obj.method,
                        'url': obj.url,
                        'id': obj.iq_id}
        sec_msg = _('Do you accept this request?')
        if app.get_number_of_connected_accounts() > 1:
            sec_msg = _('Do you accept this request (account: %s)?') % account
        if obj.msg:
            sec_msg = obj.msg + '\n' + sec_msg
        message = message + '\n' + sec_msg

        ConfirmationDialog(
            _('Authorization Request'),
            _('HTTP Authorization Request'),
            message,
            [DialogButton.make('Cancel',
                               text=_('_No'),
                               callback=_response,
                               args=[obj, 'no']),
             DialogButton.make('Accept',
                               callback=_response,
                               args=[obj, 'yes'])]).show()

    def handle_event_iq_error(self, event):
        ctrl = app.window.get_control(event.account, event.properties.jid.bare)
        if ctrl and ctrl.is_groupchat:
            ctrl.add_info_message('Error: %s' % event.properties.error)

    @staticmethod
    def handle_event_connection_lost(obj):
        # ('CONNECTION_LOST', account, [title, text])
        account = obj.conn.name
        app.notification.popup(
            _('Connection Failed'), account, account,
            'connection-lost', 'gajim-connection_lost', obj.title, obj.msg)

    @staticmethod
    def unblock_signed_in_notifications(account):
        app.block_signed_in_notifications[account] = False

    def handle_event_status(self, event):
        if event.show in ('offline', 'error'):
            # TODO: Close all account windows
            pass

        if event.show == 'offline':
            app.block_signed_in_notifications[event.account] = True
        else:
            # 30 seconds after we change our status to sth else than offline
            # we stop blocking notifications of any kind
            # this prevents from getting the roster items as 'just signed in'
            # contacts. 30 seconds should be enough time
            GLib.timeout_add_seconds(30,
                                     self.unblock_signed_in_notifications,
                                     event.account)

    def handle_event_presence(self, obj):
        # 'NOTIFY' (account, (jid, status, status message, resource,
        # priority, timestamp))
        #
        # Contact changed show
        account = obj.conn.name
        jid = obj.jid

        if app.jid_is_transport(jid):
            # It must be an agent

            # transport just signed in/out, don't show
            # popup notifications for 30s
            account_jid = account + '/' + jid
            app.block_signed_in_notifications[account_jid] = True
            GLib.timeout_add_seconds(30, self.unblock_signed_in_notifications,
                account_jid)

        ctrl = app.window.get_control(account, jid)
        if ctrl and ctrl.session and len(obj.contact_list) > 1:
            ctrl.remove_session(ctrl.session)

    @staticmethod
    def handle_event_read_state_sync(event):
        if event.type.is_groupchat:
            control = app.get_groupchat_control(
                event.account, event.jid.bare)
            if control is None:
                log.warning('Groupchat control not found')
                return

            jid = event.jid.bare
            types = ['printed_gc_msg', 'printed_marked_gc_msg']

        else:
            types = ['chat', 'pm', 'printed_chat', 'printed_pm']
            jid = event.jid

            control = app.window.get_control(event.account, jid)

        # Compare with control.last_msg_id.
        events_ = app.events.get_events(event.account, jid, types)
        if not events_:
            log.warning('No Events')
            return

        if event.type.is_groupchat:
            id_ = events_[-1].stanza_id or events_[-1].message_id
        else:
            id_ = events_[-1].message_id

        if id_ != event.marker_id:
            return

        if not app.events.remove_events(event.account, jid, types=types):
            # There were events to remove
            if control is not None:
                control.redraw_after_event_removed(event.jid)

    @staticmethod
    def handle_event_msgsent(obj):
        if not obj.play_sound:
            return

        enabled = app.settings.get_soundevent_settings('message_sent')['enabled']
        if enabled:
            if isinstance(obj.jid, list) and len(obj.jid) > 1:
                return
            helpers.play_sound('message_sent')

    @staticmethod
    def handle_event_msgnotsent(obj):
        #('MSGNOTSENT', account, (jid, ierror_msg, msg, time, session))
        msg = _('error while sending %(message)s ( %(error)s )') % {
                'message': obj.message, 'error': obj.error}
        if not obj.session:
            # No session. This can happen when sending a message from
            # gajim-remote
            log.warning(msg)
            return
        obj.session.roster_message(obj.jid, msg, obj.time_, obj.conn.name,
            msg_type='error')

    @staticmethod
    def handle_event_gc_invitation(event):
        event = events.GcInvitationEvent(event)

        # TODO: show account page
        # self.add_event(event.account, str(event.from_), event)

        if helpers.allow_showing_notification(event.account):
            client = app.get_client(event.account)
            if get_muc_context(event.muc) == 'public':
                jid = event.from_
            else:
                jid = event.from_.bare
            contact = client.get_module('Contacts').get_contact(jid)
            event_type = _('Group Chat Invitation')
            text = _('%(contact)s invited you to %(chat)s') % {
                'contact': contact.name,
                'chat': event.info.muc_name}
            app.notification.popup(event_type,
                                   str(jid),
                                   event.account,
                                   'gc-invitation',
                                   'gajim-gc_invitation',
                                   event_type,
                                   text,
                                   room_jid=event.muc)

    @staticmethod
    def handle_event_client_cert_passphrase(obj):
        def on_ok(passphrase, checked):
            obj.conn.on_client_cert_passphrase(passphrase, obj.con, obj.port,
                obj.secure_tuple)

        def on_cancel():
            obj.conn.on_client_cert_passphrase('', obj.con, obj.port,
                obj.secure_tuple)

        PassphraseDialog(_('Certificate Passphrase Required'),
                         _('Enter the certificate passphrase for account %s') % \
                         obj.conn.name, ok_handler=on_ok,
                         cancel_handler=on_cancel)

    def handle_event_password_required(self, obj):
        #('PASSWORD_REQUIRED', account, None)
        account = obj.conn.name
        if account in self.pass_dialog:
            return
        text = _('Enter your password for account %s') % account

        def on_ok(passphrase, save):
            app.settings.set_account_setting(account, 'savepass', save)
            passwords.save_password(account, passphrase)
            obj.on_password(passphrase)
            del self.pass_dialog[account]

        def on_cancel():
            del self.pass_dialog[account]

        self.pass_dialog[account] = PassphraseDialog(
            _('Password Required'), text, _('Save password'), ok_handler=on_ok,
            cancel_handler=on_cancel)

    def handle_event_roster_info(self, obj):
        #('ROSTER_INFO', account, (jid, name, sub, ask, groups))
        account = obj.conn.name
        contacts = app.contacts.get_contacts(account, obj.jid)
        if (not obj.sub or obj.sub == 'none') and \
        (not obj.ask or obj.ask == 'none') and not obj.nickname and \
        not obj.groups:
            # contact removed us.
            if contacts:
                self.roster.remove_contact(obj.jid, account, backend=True)
                return
        elif not contacts:
            if obj.sub == 'remove':
                return
            # Add new contact to roster

            contact = app.contacts.create_contact(jid=obj.jid,
                account=account, name=obj.nickname, groups=obj.groups,
                show='offline', sub=obj.sub, ask=obj.ask,
                avatar_sha=obj.avatar_sha)
            app.contacts.add_contact(account, contact)
            self.roster.add_contact(obj.jid, account)
        else:
            # If contact has changed (sub, ask or group) update roster
            # Mind about observer status changes:
            #   According to xep 0162, a contact is not an observer anymore when
            #   we asked for auth, so also remove him if ask changed
            old_groups = contacts[0].groups
            if obj.sub == 'remove':
                # another of our instance removed a contact. Remove it here too
                self.roster.remove_contact(obj.jid, account, backend=True)
                return
            update = False
            if contacts[0].sub != obj.sub or contacts[0].ask != obj.ask\
            or old_groups != obj.groups:
                # c.get_shown_groups() has changed. Reflect that in
                # roster_window
                self.roster.remove_contact(obj.jid, account, force=True)
                update = True
            for contact in contacts:
                contact.name = obj.nickname or ''
                contact.sub = obj.sub
                contact.ask = obj.ask
                contact.groups = obj.groups or []
            if update:
                self.roster.add_contact(obj.jid, account)
                # Refilter and update old groups
                for group in old_groups:
                    self.roster.draw_group(group, account)
                self.roster.draw_contact(obj.jid, account)
        if obj.jid in self.instances[account]['sub_request'] and obj.sub in (
        'from', 'both'):
            self.instances[account]['sub_request'][obj.jid].destroy()

    def handle_event_file_send_error(self, event):
        ft = self.instances['file_transfers']
        ft.set_status(event.file_props, 'stop')

        if helpers.allow_popup_window(event.account):
            ft.show_send_error(event.file_props)
            return

        event = events.FileSendErrorEvent(event.file_props)
        self.add_event(event.account, event.jid, event)

        if helpers.allow_showing_notification(event.account):
            event_type = _('File Transfer Error')
            app.notification.popup(
                event_type, event.jid, event.account,
                'file-send-error', 'dialog-error',
                event_type, event.file_props.name)

    def handle_event_file_request_error(self, obj):
        # ('FILE_REQUEST_ERROR', account, (jid, file_props, error_msg))
        ft = self.instances['file_transfers']
        ft.set_status(obj.file_props, 'stop')
        errno = obj.file_props.error

        if helpers.allow_popup_window(obj.conn.name):
            if errno in (-4, -5):
                ft.show_stopped(obj.jid, obj.file_props, obj.error_msg)
            else:
                ft.show_request_error(obj.file_props)
            return

        if errno in (-4, -5):
            event_class = events.FileErrorEvent
            msg_type = 'file-error'
        else:
            event_class = events.FileRequestErrorEvent
            msg_type = 'file-request-error'

        event = event_class(obj.file_props)
        self.add_event(obj.conn.name, obj.jid, event)

        if helpers.allow_showing_notification(obj.conn.name):
            # Check if we should be notified
            event_type = _('File Transfer Error')
            app.notification.popup(
                event_type,
                obj.jid,
                obj.conn.name,
                msg_type,
                'dialog-error',
                title=event_type,
                text=obj.file_props.name)

    def handle_event_file_request(self, obj):
        account = obj.conn.name
        if obj.jid not in app.contacts.get_jid_list(account):
            contact = app.contacts.create_not_in_roster_contact(
                jid=obj.jid, account=account)
            app.contacts.add_contact(account, contact)
            self.roster.add_contact(obj.jid, account)
        contact = app.contacts.get_first_contact_from_jid(account, obj.jid)
        if obj.file_props.session_type == 'jingle':
            request = \
                obj.stanza.getTag('jingle').getTag('content').getTag(
                    'description').getTag('request')
            if request:
                # If we get a request instead
                ft_win = self.instances['file_transfers']
                ft_win.add_transfer(account, contact, obj.file_props)
                return
        if helpers.allow_popup_window(account):
            self.instances['file_transfers'].show_file_request(
                account, contact, obj.file_props)
            return
        event = events.FileRequestEvent(obj.file_props)
        self.add_event(account, obj.jid, event)
        if helpers.allow_showing_notification(account):
            txt = _('%s wants to send you a file.') % app.get_name_from_jid(
                account, obj.jid)
            event_type = _('File Transfer Request')
            app.notification.popup(
                event_type,
                obj.jid,
                account,
                'file-request',
                icon_name='document-send',
                title=event_type,
                text=txt)

    @staticmethod
    def handle_event_file_error(title, message):
        ErrorDialog(title, message)

    def handle_event_file_progress(self, account, file_props):
        if time.time() - self.last_ftwindow_update > 0.5:
            # Update ft window every 500ms
            self.last_ftwindow_update = time.time()
            self.instances['file_transfers'].set_progress(
                file_props.type_, file_props.sid, file_props.received_len)

    def __compare_hashes(self, account, file_props):
        session = app.connections[account].get_module(
            'Jingle').get_jingle_session(jid=None, sid=file_props.sid)
        ft_win = self.instances['file_transfers']
        h = Hashes2()
        try:
            file_ = open(file_props.file_name, 'rb')
        except Exception:
            return
        hash_ = h.calculateHash(file_props.algo, file_)
        file_.close()
        # If the hash we received and the hash of the file are the same,
        # then the file is not corrupt
        jid = file_props.sender
        if file_props.hash_ == hash_:
            GLib.idle_add(self.popup_ft_result, account, jid, file_props)
            GLib.idle_add(ft_win.set_status, file_props, 'ok')
        else:
            # Wrong hash, we need to get the file again!
            file_props.error = -10
            GLib.idle_add(self.popup_ft_result, account, jid, file_props)
            GLib.idle_add(ft_win.set_status, file_props, 'hash_error')
        # End jingle session
        if session:
            session.end_session()

    def handle_event_file_rcv_completed(self, account, file_props):
        ft = self.instances['file_transfers']
        if file_props.error == 0:
            ft.set_progress(
                file_props.type_, file_props.sid, file_props.received_len)
            jid = app.get_jid_without_resource(str(file_props.receiver))
            app.nec.push_incoming_event(
                NetworkEvent('file-transfer-completed',
                             file_props=file_props,
                             jid=jid))

        else:
            ft.set_status(file_props, 'stop')
        if not file_props.completed and (file_props.stalled or
                file_props.paused):
            return

        if file_props.type_ == 'r':  # We receive a file
            app.socks5queue.remove_receiver(file_props.sid, True, True)
            if file_props.session_type == 'jingle':
                if file_props.hash_ and file_props.error == 0:
                    # We compare hashes in a new thread
                    self.hashThread = Thread(target=self.__compare_hashes,
                                             args=(account, file_props))
                    self.hashThread.start()
                else:
                    # We didn't get the hash, sender probably doesn't
                    # support that
                    jid = file_props.sender
                    self.popup_ft_result(account, jid, file_props)
                    if file_props.error == 0:
                        ft.set_status(file_props, 'ok')
                    session = \
                        app.connections[account].get_module(
                            'Jingle').get_jingle_session(jid=None,
                                                         sid=file_props.sid)
                    # End jingle session
                    # TODO: Only if there are no other parallel downloads in
                    # this session
                    if session:
                        session.end_session()
        else:  # We send a file
            jid = file_props.receiver
            app.socks5queue.remove_sender(file_props.sid, True, True)
            self.popup_ft_result(account, jid, file_props)

    def popup_ft_result(self, account, jid, file_props):
        ft = self.instances['file_transfers']
        if helpers.allow_popup_window(account):
            if file_props.error == 0:
                if app.settings.get('notify_on_file_complete'):
                    ft.show_completed(jid, file_props)
            elif file_props.error == -1:
                ft.show_stopped(
                    jid,
                    file_props,
                    error_msg=_('Remote Contact Stopped Transfer'))
            elif file_props.error == -6:
                ft.show_stopped(
                    jid,
                    file_props,
                    error_msg=_('Error Opening File'))
            elif file_props.error == -10:
                ft.show_hash_error(
                    jid,
                    file_props,
                    account)
            elif file_props.error == -12:
                ft.show_stopped(
                    jid,
                    file_props,
                    error_msg=_('SSL Certificate Error'))
            return

        msg_type = ''
        event_type = ''
        if (file_props.error == 0 and
                app.settings.get('notify_on_file_complete')):
            event_class = events.FileCompletedEvent
            msg_type = 'file-completed'
            event_type = _('File Transfer Completed')
        elif file_props.error in (-1, -6):
            event_class = events.FileStoppedEvent
            msg_type = 'file-stopped'
            event_type = _('File Transfer Stopped')
        elif file_props.error == -10:
            event_class = events.FileHashErrorEvent
            msg_type = 'file-hash-error'
            event_type = _('File Transfer Failed')

        if event_type == '':
            # FIXME: ugly workaround (this can happen Gajim sent, Gaim recvs)
            # this should never happen but it does. see process_result() in
            # socks5.py
            # who calls this func (sth is really wrong unless this func is also
            # registered as progress_cb
            return

        if msg_type:
            event = event_class(file_props)
            self.add_event(account, jid, event)

        if file_props is not None:
            if file_props.type_ == 'r':
                # Get the name of the sender, as it is in the roster
                sender = file_props.sender.split('/')[0]
                name = app.contacts.get_first_contact_from_jid(
                    account, sender).get_shown_name()
                filename = os.path.basename(file_props.file_name)

                if event_type == _('File Transfer Completed'):
                    txt = _('%(filename)s received from %(name)s.') % {
                        'filename': filename,
                        'name': name}
                    icon_name = 'emblem-default'
                elif event_type == _('File Transfer Stopped'):
                    txt = _('File transfer of %(filename)s from %(name)s '
                            'stopped.') % {
                                'filename': filename,
                                'name': name}
                    icon_name = 'process-stop'
                else: # File transfer hash error
                    txt = _('File transfer of %(filename)s from %(name)s '
                            'failed.') % {
                                'filename': filename,
                                'name': name}
                    icon_name = 'process-stop'
            else:
                receiver = file_props.receiver
                if hasattr(receiver, 'jid'):
                    receiver = receiver.jid
                receiver = receiver.split('/')[0]
                # Get the name of the contact, as it is in the roster
                name = app.contacts.get_first_contact_from_jid(
                    account, receiver).get_shown_name()
                filename = os.path.basename(file_props.file_name)
                if event_type == _('File Transfer Completed'):
                    txt = _('You successfully sent %(filename)s to '
                            '%(name)s.') % {
                                'filename': filename,
                                'name': name}
                    icon_name = 'emblem-default'
                elif event_type == _('File Transfer Stopped'):
                    txt = _('File transfer of %(filename)s to %(name)s '
                            'stopped.') % {
                                'filename': filename,
                                'name': name}
                    icon_name = 'process-stop'
                else: # File transfer hash error
                    txt = _('File transfer of %(filename)s to %(name)s '
                            'failed.') % {
                                'filename': filename,
                                'name': name}
                    icon_name = 'process-stop'
        else:
            txt = ''
            icon_name = None

        if (app.settings.get('notify_on_file_complete') and
                (app.settings.get('autopopupaway') or
                app.connections[account].status in ('online', 'chat'))):
            # We want to be notified and we are online/chat or we don't mind
            # to be bugged when away/na/busy
            app.notification.popup(
                event_type,
                jid,
                account,
                msg_type,
                icon_name=icon_name,
                title=event_type,
                text=txt)

    @staticmethod
    def handle_event_signed_in(obj):
        """
        SIGNED_IN event is emitted when we sign in, so handle it
        """
        # ('SIGNED_IN', account, ())
        # block signed in notifications for 30 seconds

        # Add our own JID into the DB
        app.storage.archive.insert_jid(obj.conn.get_own_jid().bare)
        account = obj.conn.name
        app.block_signed_in_notifications[account] = True

        pep_supported = obj.conn.get_module('PEP').supported

        if obj.conn.get_module('MAM').available:
            obj.conn.get_module('MAM').request_archive_on_signin()

        # enable location listener
        if (pep_supported and app.is_installed('GEOCLUE') and
                app.settings.get_account_setting(account, 'publish_location')):
            location.enable()

        if ask_for_status_message(obj.conn.status, signin=True):
            app.window.show_app_page()

    def send_httpupload(self, chat_control, path=None):
        if path is not None:
            self._send_httpupload(chat_control, path)
            return

        accept_cb = partial(self.on_file_dialog_ok, chat_control)
        FileChooserDialog(accept_cb,
                          select_multiple=True,
                          transient_for=app.window)

    def on_file_dialog_ok(self, chat_control, paths):
        for path in paths:
            self._send_httpupload(chat_control, path)

    def _send_httpupload(self, chat_control, path):
        client = app.get_client(chat_control.account)
        try:
            transfer = client.get_module('HTTPUpload').make_transfer(
                path,
                chat_control.encryption,
                chat_control.contact,
                chat_control.is_groupchat)
        except FileError as error:
            app.nec.push_incoming_event(InformationEvent(
                None, dialog_name='open-file-error2', args=error))
            return

        transfer.connect('cancel', self._on_cancel_upload)
        transfer.connect('state-changed',
                         self._on_http_upload_state_changed)
        chat_control.add_file_transfer(transfer)
        client.get_module('HTTPUpload').start_transfer(transfer)

    def _on_http_upload_state_changed(self, transfer, _signal_name, state):
        # Note: This has to be a bound method in order to connect the signal
        if state.is_finished:
            uri = transfer.get_transformed_uri()

            type_ = 'chat'
            if transfer.is_groupchat:
                type_ = 'groupchat'

            message = OutgoingMessage(account=transfer.account,
                                      contact=transfer.contact,
                                      message=uri,
                                      type_=type_,
                                      oob_url=uri)

            client = app.get_client(transfer.account)
            client.send_message(message)

    def _on_cancel_upload(self, transfer, _signal_name):
        # Note: This has to be a bound method in order to connect the signal
        client = app.get_client(transfer.account)
        client.get_module('HTTPUpload').cancel_transfer(transfer)

    @staticmethod
    def handle_event_metacontacts(obj):
        app.contacts.define_metacontacts(obj.conn.name, obj.meta_list)

    def handle_event_zc_name_conflict(self, obj):
        def _on_ok(new_name):
            app.settings.set_account_setting(obj.conn.name, 'name', new_name)
            obj.conn.username = new_name
            obj.conn.change_status(obj.conn.status, obj.conn.status_message)

        def _on_cancel(*args):
            obj.conn.change_status('offline', '')

        InputDialog(
            _('Username Conflict'),
            _('Username Conflict'),
            _('Please enter a new username for your local account'),
            [DialogButton.make('Cancel',
                               callback=_on_cancel),
             DialogButton.make('Accept',
                               text=_('_OK'),
                               callback=_on_ok)],
            input_str=obj.alt_name,
            transient_for=self.roster.window).show()

    def handle_event_jingleft_cancel(self, obj):
        ft = self.instances['file_transfers']
        file_props = None
        # get the file_props of our session
        file_props = FilesProp.getFileProp(obj.conn.name, obj.sid)
        if not file_props:
            return
        ft.set_status(file_props, 'stop')
        file_props.error = -4 # is it the right error code?
        ft.show_stopped(obj.jid, file_props, 'Peer cancelled ' +
                            'the transfer')

    # Jingle AV handling
    def handle_event_jingle_incoming(self, event):
        # ('JINGLE_INCOMING', account, peer jid, sid, tuple-of-contents==(type,
        # data...))
        # TODO: conditional blocking if peer is not in roster

        account = event.conn.name
        content_types = []
        for item in event.contents:
            content_types.append(item.media)
        # check type of jingle session
        if 'audio' in content_types or 'video' in content_types:
            # a voip session...
            # we now handle only voip, so the only thing we will do here is
            # not to return from function
            pass
        else:
            # unknown session type... it should be declined in common/jingle.py
            return

        notification_event = events.JingleIncomingEvent(
            event.fjid, event.sid, content_types)

        ctrl = (app.window.get_control(account, event.fjid) or
                app.window.get_control(account, event.jid))
        if ctrl:
            if 'audio' in content_types:
                ctrl.set_jingle_state(
                    'audio',
                    JingleState.CONNECTION_RECEIVED,
                    event.sid)
            if 'video' in content_types:
                ctrl.set_jingle_state(
                    'video',
                    JingleState.CONNECTION_RECEIVED,
                    event.sid)
            ctrl.add_call_received_message(notification_event)

        if helpers.allow_popup_window(account):
            def _prepare_control():
                ctrl = app.window.get_control(account, event.jid)
                ctrl.add_call_received_message(notification_event)

            if not ctrl:
                app.window.add_chat(
                    account, event.jid, 'contact', select=True)
            GLib.idle_add(_prepare_control)
            return

        self.add_event(account, event.fjid, notification_event)

        if helpers.allow_showing_notification(account):
            heading = _('Incoming Call')
            contact = app.get_name_from_jid(account, event.jid)
            text = _('%s is calling') % contact
            app.notification.popup(
                heading,
                event.fjid,
                account,
                'jingle-incoming',
                icon_name='call-start-symbolic',
                title=heading,
                text=text)

    @staticmethod
    def handle_event_jingle_connected(event):
        # ('JINGLE_CONNECTED', account, (peerjid, sid, media))
        if event.media in ('audio', 'video'):
            account = event.conn.name
            ctrl = (app.window.get_control(account, event.fjid) or
                    app.window.get_control(account, event.jid))
            if ctrl:
                con = app.connections[account]
                session = con.get_module('Jingle').get_jingle_session(
                    event.fjid, event.sid)

                if event.media == 'audio':
                    content = session.get_content('audio')
                    ctrl.set_jingle_state(
                        'audio',
                        JingleState.CONNECTED,
                        event.sid)
                if event.media == 'video':
                    content = session.get_content('video')
                    ctrl.set_jingle_state(
                        'video',
                        JingleState.CONNECTED,
                        event.sid)

                # Now, accept the content/sessions.
                # This should be done after the chat control is running
                if not session.accepted:
                    session.approve_session()
                for content in event.media:
                    session.approve_content(content)

    @staticmethod
    def handle_event_jingle_disconnected(event):
        # ('JINGLE_DISCONNECTED', account, (peerjid, sid, reason))
        account = event.conn.name
        ctrl = (app.window.get_control(account, event.fjid) or
                app.window.get_control(account, event.jid))
        if ctrl:
            if event.media is None:
                ctrl.stop_jingle(sid=event.sid, reason=event.reason)
            if event.media == 'audio':
                ctrl.set_jingle_state(
                    'audio',
                    JingleState.NULL,
                    sid=event.sid,
                    reason=event.reason)
            if event.media == 'video':
                ctrl.set_jingle_state(
                    'video',
                    JingleState.NULL,
                    sid=event.sid,
                    reason=event.reason)

    @staticmethod
    def handle_event_jingle_error(event):
        # ('JINGLE_ERROR', account, (peerjid, sid, reason))
        account = event.conn.name
        ctrl = (app.window.get_control(account, event.fjid) or
                app.window.get_control(account, event.jid))
        if ctrl and event.sid == ctrl.jingle['audio'].sid:
            ctrl.set_jingle_state(
                'audio',
                JingleState.ERROR,
                reason=event.reason)

    @staticmethod
    def handle_event_roster_item_exchange(obj):
        # data = (action in [add, delete, modify], exchange_list, jid_from)
        RosterItemExchangeWindow(obj.conn.name, obj.action,
                                 obj.exchange_items_list, obj.fjid)

    @staticmethod
    def handle_event_plain_connection(event):
        ConfirmationDialog(
            _('Insecure Connection'),
            _('Insecure Connection'),
            _('You are about to connect to the account %(account)s '
              '(%(server)s) using an insecure connection method. This means '
              'conversations will not be encrypted. Connecting PLAIN is '
              'strongly discouraged.') % {
                  'account': event.account,
                  'server': app.get_hostname_from_account(event.account)},
            [DialogButton.make('Cancel',
                               text=_('_Abort'),
                               callback=event.abort),
             DialogButton.make('Remove',
                               text=_('_Connect Anyway'),
                               callback=event.connect)]).show()

    def create_core_handlers_list(self):
        self.handlers = {
            'file-send-error': [self.handle_event_file_send_error],
            'client-cert-passphrase': [
                self.handle_event_client_cert_passphrase],
            'connection-lost': [self.handle_event_connection_lost],
            'file-request-error': [self.handle_event_file_request_error],
            'file-request-received': [self.handle_event_file_request],
            'muc-invitation': [self.handle_event_gc_invitation],
            'http-auth-received': [self.handle_event_http_auth],
            'information': [self.handle_event_information],
            'iq-error-received': [self.handle_event_iq_error],
            'jingle-connected-received': [self.handle_event_jingle_connected],
            'jingle-disconnected-received': [
                self.handle_event_jingle_disconnected],
            'jingle-error-received': [self.handle_event_jingle_error],
            'jingle-request-received': [self.handle_event_jingle_incoming],
            'jingle-ft-cancelled-received': [self.handle_event_jingleft_cancel],
            'message-not-sent': [self.handle_event_msgnotsent],
            'message-sent': [self.handle_event_msgsent],
            'metacontacts-received': [self.handle_event_metacontacts],
            'our-show': [self.handle_event_status],
            'password-required': [self.handle_event_password_required],
            'plain-connection': [self.handle_event_plain_connection],
            'presence-received': [self.handle_event_presence],
            # 'roster-info': [self.handle_event_roster_info],
            'roster-item-exchange-received': \
                [self.handle_event_roster_item_exchange],
            'signed-in': [self.handle_event_signed_in],
            'zeroconf-name-conflict': [self.handle_event_zc_name_conflict],
            'read-state-sync': [self.handle_event_read_state_sync],
        }

    def register_core_handlers(self):
        """
        Register core handlers in Global Events Dispatcher (GED).

        This is part of rewriting whole events handling system to use GED.
        """
        for event_name, event_handlers in self.handlers.items():
            for event_handler in event_handlers:
                prio = ged.GUI1
                if isinstance(event_handler, tuple):
                    prio = event_handler[1]
                    event_handler = event_handler[0]
                app.ged.register_event_handler(event_name, prio,
                    event_handler)

    def add_event(self, account, jid, event):
        """
        Add an event to the app.events var
        """
        # We add it to the app.events queue
        # Do we have a queue?
        jid = app.get_jid_without_resource(jid)
        no_queue = len(app.events.get_events(account, jid)) == 0
        # event can be in common.events.*
        # event_type can be in advancedNotificationWindow.events_list
        event_types = {'file-request': 'ft_request',
            'file-completed': 'ft_finished'}
        event_type = event_types.get(event.type_)
        show_in_roster = get_show_in_roster(event_type, jid)
        show_in_systray = get_show_in_systray(event_type, account, jid)
        event.show_in_roster = show_in_roster
        event.show_in_systray = show_in_systray
        app.events.add_event(account, jid, event)

        self.roster.show_title()
        if no_queue:  # We didn't have a queue: we change icons
            if app.contacts.get_contact_with_highest_priority(account, jid):
                self.roster.draw_contact(jid, account)
            else:
                groupchat = event.type_ == 'gc-invitation'
                self.roster.add_to_not_in_the_roster(
                    account, jid, groupchat=groupchat)

        # Select the big brother contact in roster, it's visible because it has
        # events.
        family = app.contacts.get_metacontacts_family(account, jid)
        if family:
            _nearby_family, bb_jid, bb_account = \
                app.contacts.get_nearby_family_and_big_brother(family,
                account)
        else:
            bb_jid, bb_account = jid, account
        self.roster.select_contact(bb_jid, bb_account)

    def handle_event(self, account, fjid, type_):
        if type_ in ('connection-lost', 'connection-failed'):
            app.interface.roster.window.present()
            return

        w = None
        ctrl = None

        resource = app.get_resource_from_jid(fjid)
        jid = app.get_jid_without_resource(fjid)

        if type_ in ('printed_gc_msg', 'printed_marked_gc_msg', 'gc_msg'):
            w = self.msg_win_mgr.get_window(jid, account)
            if jid in self.minimized_controls[account]:
                self.roster.on_groupchat_maximized(None, jid, account)
                return
            ctrl = self.msg_win_mgr.get_gc_control(jid, account)

        elif type_ in ('printed_chat', 'chat', ''):
            # '' is for log in/out notifications

            ctrl = self.msg_win_mgr.search_control(jid, account, resource)

            if not ctrl:
                highest_contact = app.contacts.\
                    get_contact_with_highest_priority(account, jid)
                # jid can have a window if this resource was lower when he sent
                # message and is now higher because the other one is offline
                if resource and highest_contact.resource == resource and \
                not self.msg_win_mgr.has_window(jid, account):
                    # remove resource of events too
                    app.events.change_jid(account, fjid, jid)
                    resource = None
                    fjid = jid

                contact = None
                if resource:
                    contact = app.contacts.get_contact(account, jid, resource)
                if not contact:
                    contact = highest_contact
                if not contact:
                    # Maybe we deleted the contact from the roster
                    return

                ctrl = self.new_chat(contact, account, resource=resource)

                app.last_message_time[account][jid] = 0 # long time ago

            w = ctrl.parent_win
        elif type_ in ('printed_pm', 'pm'):

            ctrl = self.msg_win_mgr.get_control(fjid, account)

            if not ctrl:
                room_jid = jid
                nick = resource
                gc_contact = app.contacts.get_gc_contact(
                    account, room_jid, nick)
                ctrl = self.new_private_chat(gc_contact, account)

            w = ctrl.parent_win
        elif type_ in ('file-request', 'file-request-error',
        'file-send-error', 'file-error', 'file-stopped', 'file-completed',
        'file-hash-error', 'jingle-incoming'):
            # Get the first single message event
            event = app.events.get_first_event(account, fjid, type_)
            if not event:
                # default to jid without resource
                event = app.events.get_first_event(account, jid, type_)
                if not event:
                    return
                # Open the window
                self.roster.open_event(account, jid, event)
            else:
                # Open the window
                self.roster.open_event(account, fjid, event)
        elif type_ == 'gc-invitation':
            event = app.events.get_first_event(account, jid, type_)
            if event is None:
                return
            # TODO: Show account page
            # open_window('GroupChatInvitation',
            #             account=account,
            #             event=event)
            app.events.remove_events(account, jid, event)
            # self.roster.draw_contact(jid, account)
        elif type_ == 'subscription_request':
            event = app.events.get_first_event(account, jid, type_)
            if event is None:
                return
            # TODO: Show account page
            app.events.remove_events(account, jid, event)
            # self.roster.draw_contact(jid, account)
        elif type_ == 'unsubscribed':
            event = app.events.get_first_event(account, jid, type_)
            if event is None:
                return
            # TODO: Show account page
            app.events.remove_events(account, jid, event)
            # self.roster.draw_contact(jid, account)
        if w:
            w.set_active_tab(ctrl)
            w.window.present()
            # Using isinstance here because we want to catch all derived types
            if isinstance(ctrl, BaseControl):
                ctrl.scroll_to_end()

    def create_groupchat(self, account, room_jid, config):
        if app.window.chat_exists(account, room_jid):
            log.error('Trying to create groupchat '
                      'which is already added as chat')
            return

        client = app.get_client(account)
        client.get_module('MUC').create(room_jid, config)

    def show_add_join_groupchat(self, account, jid, nickname=None):
        if not app.window.chat_exists(account, jid):
            client = app.get_client(account)
            client.get_module('MUC').join(jid, nick=nickname)

        app.window.add_group_chat(account, str(jid), select=True)

    @staticmethod
    def _on_muc_added(event):
        if app.window.chat_exists(event.account, event.jid):
            return

        app.window.add_group_chat(event.account, str(event.jid))

    @staticmethod
    def create_account(account,
                       username,
                       domain,
                       password,
                       proxy_name,
                       custom_host,
                       anonymous=False):

        account_label = f'{username}@{domain}'
        if anonymous:
            username = 'anon'
            account_label = f'anon@{domain}'

        config = {}
        config['active'] = False
        config['name'] = username
        config['resource'] = 'gajim.%s' % helpers.get_random_string(8)
        config['account_label'] = account_label
        config['account_color'] = get_color_for_account(
            '%s@%s' % (username, domain))
        config['hostname'] = domain
        config['savepass'] = True
        config['anonymous_auth'] = anonymous
        config['autoconnect'] = True
        config['sync_with_global_status'] = True

        if proxy_name is not None:
            config['proxy'] = proxy_name

        use_custom_host = custom_host is not None
        config['use_custom_host'] = use_custom_host
        if custom_host:
            host, _protocol, type_ = custom_host
            host, port = host.rsplit(':', maxsplit=1)
            config['custom_port'] = int(port)
            config['custom_host'] = host
            config['custom_type'] = type_.value

        app.settings.add_account(account)
        for opt in config:
            app.settings.set_account_setting(account, opt, config[opt])

        # Password module depends on existing config
        passwords.save_password(account, password)

        app.css_config.refresh()

        # Action must be added before account window is updated
        app.app.add_account_actions(account)

        window = get_app_window('AccountsWindow')
        if window is not None:
            window.add_account(account)

    def enable_account(self, account):
        if account == app.ZEROCONF_ACC_NAME:
            app.connections[account] = connection_zeroconf.ConnectionZeroconf(
                account)
        else:
            app.connections[account] = Client(account)

        app.plugin_manager.register_modules_for_account(
            app.connections[account])

        app.ged.register_event_handler(
            'muc-added', ged.CORE, self._on_muc_added)

        # update variables
        self.instances[account] = {
            'infos': {}, 'disco': {}, 'gc_config': {}, 'search': {},
            'sub_request': {}}

        app.groups[account] = {}
        app.contacts.add_account(account)
        app.gc_connected[account] = {}
        app.automatic_rooms[account] = {}
        app.newly_added[account] = []
        app.to_be_removed[account] = []
        if account == app.ZEROCONF_ACC_NAME:
            app.nicks[account] = app.ZEROCONF_ACC_NAME
        else:
            app.nicks[account] = app.settings.get_account_setting(account,
                                                                  'name')
        app.block_signed_in_notifications[account] = True
        app.last_message_time[account] = {}

        app.settings.set_account_setting(account, 'active', True)
        gui_menu_builder.build_accounts_menu()
        app.app.update_app_actions_state()

        app.nec.push_incoming_event(NetworkEvent(
            'account-enabled',
            account=account))

        app.connections[account].change_status('online', '')
        window = get_app_window('AccountsWindow')
        if window is not None:
            GLib.idle_add(window.enable_account, account, True)

    def disable_account(self, account):
        for win in get_app_windows(account):
            # Close all account specific windows, except the RemoveAccount
            # dialog. It shows if the removal was successful.
            if type(win).__name__ == 'RemoveAccount':
                continue
            win.destroy()

        app.settings.set_account_setting(account, 'roster_version', '')
        app.settings.set_account_setting(account, 'active', False)
        gui_menu_builder.build_accounts_menu()
        app.app.update_app_actions_state()

        app.nec.push_incoming_event(NetworkEvent(
            'account-disabled',
            account=account))

        if account == app.ZEROCONF_ACC_NAME:
            app.connections[account].disable_account()
        app.connections[account].cleanup()
        del app.connections[account]
        del self.instances[account]
        del app.nicks[account]
        del app.block_signed_in_notifications[account]
        del app.groups[account]
        app.contacts.remove_account(account)
        del app.gc_connected[account]
        del app.automatic_rooms[account]
        del app.to_be_removed[account]
        del app.newly_added[account]
        del app.last_message_time[account]

    def remove_account(self, account):
        if app.settings.get_account_setting(account, 'active'):
            self.disable_account(account)

        app.storage.cache.remove_roster(account)
        # Delete password must be before del_per() because it calls set_per()
        # which would recreate the account with defaults values if not found
        passwords.delete_password(account)
        app.settings.remove_account(account)
        app.app.remove_account_actions(account)

        window = get_app_window('AccountsWindow')
        if window is not None:
            window.remove_account(account)

    def autoconnect(self):
        """
        Auto connect at startup
        """

        for account in app.connections:
            if not app.settings.get_account_setting(account, 'autoconnect'):
                continue

            status = 'online'
            status_message = ''

            if app.settings.get_account_setting(account, 'restore_last_status'):
                status = app.settings.get_account_setting(account, 'last_status')
                status_message = app.settings.get_account_setting(
                    account, 'last_status_msg')
                status_message = helpers.from_one_line(status_message)

            app.connections[account].change_status(status, status_message)

    def change_status(self, status, account=None):
        ask = ask_for_status_message(status)

        if status is None:
            status = helpers.get_global_show()

        if ask:
            if account is None:
                app.window.show_app_page()
            else:
                app.window.show_account_page(account)
            return

        if account is not None:
            self._change_status(account, status)
            return

        for account in app.connections:
            if not app.settings.get_account_setting(account,
                                                    'sync_with_global_status'):
                continue

            self._change_status(account, status)

    def change_account_status(self, account, status):
        ask = ask_for_status_message(status)

        client = app.get_client(account)
        if status is None:
            status = client.status

        if ask:
            app.window.show_account_page(account)
            return

        self._change_status(account, status)

    @staticmethod
    def _change_status(account, status):
        client = app.get_client(account)
        message = client.status_message
        if status != 'offline':
            app.settings.set_account_setting(account, 'last_status', status)
            app.settings.set_account_setting(
                account,
                'last_status_msg',
                helpers.to_one_line(message))

        if status == 'offline':
            # TODO delete pep
            # self.delete_pep(app.get_jid_from_account(account), account)
            pass

        client.change_status(status, message)

    def show_systray(self):
        if not app.is_display(Display.WAYLAND):
            self.systray_enabled = True
            self.systray.show_icon()

    def hide_systray(self):
        if not app.is_display(Display.WAYLAND):
            self.systray_enabled = False
            self.systray.hide_icon()

    def process_connections(self):
        """
        Called each foo (200) milliseconds. Check for idlequeue timeouts
        """
        try:
            app.idlequeue.process()
        except Exception:
            # Otherwise, an exception will stop our loop

            if sys.platform == 'win32':
                # On Windows process() calls select.select(), so we need this
                # executed as often as possible.
                # Adding it directly with GLib.idle_add() causes Gajim to use
                # too much CPU time. That's why its added with 1ms timeout.
                # On Linux only alarms are checked in process(), so we use
                # a bigger timeout
                timeout, in_seconds = 1, None
            else:
                timeout, in_seconds = app.idlequeue.PROCESS_TIMEOUT

            if in_seconds:
                GLib.timeout_add_seconds(timeout, self.process_connections)
            else:
                GLib.timeout_add(timeout, self.process_connections)
            raise
        return True # renew timeout (loop for ever)

    @staticmethod
    def save_config():
        app.settings.save()

    def save_avatar(self, data):
        return self.avatar_storage.save_avatar(data)

    def get_avatar(self,
                   contact,
                   size,
                   scale,
                   show=None,
                   pixbuf=False,
                   style='circle'):
        if pixbuf:
            return self.avatar_storage.get_pixbuf(
                contact, size, scale, show, style=style)
        return self.avatar_storage.get_surface(
            contact, size, scale, show, style=style)

    def avatar_exists(self, filename):
        return self.avatar_storage.get_avatar_path(filename) is not None

    # does JID exist only within a groupchat?
    def is_pm_contact(self, fjid, account):
        bare_jid = app.get_jid_without_resource(fjid)

        gc_ctrl = self.msg_win_mgr.get_gc_control(bare_jid, account)

        if not gc_ctrl and \
        bare_jid in self.minimized_controls[account]:
            gc_ctrl = self.minimized_controls[account][bare_jid]

        return gc_ctrl and gc_ctrl.is_groupchat

    @staticmethod
    def create_ipython_window():
        # Check if IPython is installed
        ipython = find_spec('IPython')
        is_installed = ipython is not None
        if not is_installed:
            # Abort early to avoid tracebacks
            print('IPython is not installed')
            return
        try:
            from gajim.dev.ipython_view import IPythonView
        except ImportError:
            print('ipython_view not found')
            return
        from gi.repository import Pango

        if os.name == 'nt':
            font = 'Lucida Console 9'
        else:
            font = 'Luxi Mono 10'

        window = Gtk.Window()
        window.set_title(_('Gajim: IPython Console'))
        window.set_size_request(750, 550)
        window.set_resizable(True)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        view = IPythonView()
        view.override_font(Pango.FontDescription(font))
        view.set_wrap_mode(Gtk.WrapMode.CHAR)
        sw.add(view)
        window.add(sw)
        window.show_all()
        def on_delete(win, event):
            win.hide()
            return True
        window.connect('delete_event', on_delete)
        view.updateNamespace({'gajim': app})
        app.ipython_window = window

    def _network_status_changed(self, monitor, _param):
        connected = monitor.get_network_available()
        if connected == self.network_state:
            return

        self.network_state = connected
        if connected:
            log.info('Network connection available')
        else:
            log.info('Network connection lost')
            for connection in app.connections.values():
                if (connection.state.is_connected or
                        connection.state.is_available):
                    connection.disconnect(gracefully=False, reconnect=True)

    def create_zeroconf_default_config(self):
        if app.settings.get_account_setting(app.ZEROCONF_ACC_NAME, 'name'):
            return
        log.info('Creating zeroconf account')
        app.settings.add_account(app.ZEROCONF_ACC_NAME)
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'autoconnect',
                                         True)
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'no_log_for',
                                         '')
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'password',
                                         'zeroconf')
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'sync_with_global_status',
                                         True)
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'custom_port',
                                         5298)
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'is_zeroconf',
                                         True)
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'use_ft_proxies',
                                         False)
        app.settings.set_account_setting(app.ZEROCONF_ACC_NAME,
                                         'active',
                                         False)

    def check_for_updates(self):
        if not app.settings.get('check_for_update'):
            return

        now = datetime.now()
        last_check = app.settings.get('last_update_check')
        if not last_check:
            app.window.add_app_message('gajim-update-check')
            return

        last_check_time = datetime.strptime(last_check, '%Y-%m-%d %H:%M')
        if (now - last_check_time).days < 7:
            return

        self.get_latest_release()

    def get_latest_release(self):
        log.info('Checking for Gajim updates')
        session = Soup.Session()
        session.props.user_agent = 'Gajim %s' % app.version
        message = Soup.Message.new(
            'GET', 'https://gajim.org/current-version.json')
        session.queue_message(message, self._on_update_checked)

    def _on_update_checked(self, _session, message):
        now = datetime.now()
        app.settings.set('last_update_check', now.strftime('%Y-%m-%d %H:%M'))

        body = message.props.response_body.data
        if not body:
            log.warning('Could not reach gajim.org for update check')
            return

        data = json.loads(body)
        latest_version = data['current_version']

        if V(latest_version) > V(app.version):
            app.window.add_app_message('gajim-update', latest_version)
        else:
            log.info('Gajim is up to date')

    def run(self, application):
        if app.settings.get('trayicon') != 'never':
            self.show_systray()

        # self.roster = roster_window.RosterWindow(application)
        # if self.msg_win_mgr.mode == \
        # MessageWindowMgr.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER:
        #     self.msg_win_mgr.create_window(None, None, None)

        # Creating plugin manager
        from gajim import plugins
        app.plugin_manager = plugins.PluginManager()
        app.plugin_manager.init_plugins()

        # self.roster._before_fill()
        for account in app.connections:
            app.connections[account].get_module('Roster').load_roster()
        # self.roster._after_fill()

        # get instances for windows/dialogs that will show_all()/hide()
        self.instances['file_transfers'] = FileTransfersWindow()

        GLib.timeout_add(100, self.autoconnect)
        if sys.platform == 'win32':
            timeout, in_seconds = 20, None
        else:
            timeout, in_seconds = app.idlequeue.PROCESS_TIMEOUT

        if in_seconds:
            GLib.timeout_add_seconds(timeout, self.process_connections)
        else:
            GLib.timeout_add(timeout, self.process_connections)

        def remote_init():
            if app.settings.get('remote_control'):
                try:
                    from gajim import remote_control
                    remote_control.GajimRemote()
                except Exception:
                    pass
        GLib.timeout_add_seconds(5, remote_init)
        MainWindow()


class ThreadInterface:
    def __init__(self, func, func_args=(), callback=None, callback_args=()):
        """
        Call a function in a thread
        """
        def thread_function(func, func_args, callback, callback_args):
            output = func(*func_args)
            if callback:
                GLib.idle_add(callback, output, *callback_args)

        Thread(target=thread_function, args=(func, func_args, callback,
                callback_args)).start()
