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

from __future__ import annotations

from typing import Any
from typing import Literal
from typing import TYPE_CHECKING

import logging

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from nbxmpp import JID

from gajim.common import app

from gajim.gtk.builder import get_builder
from gajim.gtk.chat_filter import ChatFilter
from gajim.gtk.chat_list import ChatList
from gajim.gtk.chat_list_stack import ChatListStack
from gajim.gtk.chat_stack import ChatStack
from gajim.gtk.menus import get_start_chat_button_menu
from gajim.gtk.search_view import SearchView

if TYPE_CHECKING:
    from gajim.gtk.control import ChatControl

log = logging.getLogger('gajim.gtk.chat_page')


class ChatPage(Gtk.Box):

    __gsignals__ = {
        'chat-selected': (GObject.SignalFlags.RUN_LAST,
                          None,
                          (str, str, str)),
    }

    def __init__(self):
        Gtk.Box.__init__(self)

        self._ui = get_builder('chat_paned.ui')
        self.add(self._ui.paned)
        self._ui.connect_signals(self)

        self._chat_stack = ChatStack()
        self._ui.right_grid.attach(self._chat_stack, 0, 0, 1, 1)

        self._chat_control = self._chat_stack.get_chat_control()

        self._search_view = SearchView()
        self._search_view.connect('hide-search', self._on_search_hide)

        self._search_revealer = Gtk.Revealer()
        self._search_revealer.set_reveal_child(False)
        self._search_revealer.set_hexpand(False)
        self._search_revealer.set_hexpand_set(True)
        self._search_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_LEFT)
        self._search_revealer.add(self._search_view)
        self._ui.right_grid.attach(self._search_revealer, 1, 0, 1, 1)

        self._restore_occupants_list = False

        self._chat_filter = ChatFilter(icons=True)
        self._ui.filter_bar.add(self._chat_filter)
        self._ui.filter_bar_toggle.connect(
            'toggled', self._on_filter_revealer_toggled)

        self._chat_list_stack = ChatListStack(
            self._chat_filter, self._ui.search_entry)
        self._chat_list_stack.connect('chat-selected', self._on_chat_selected)
        self._chat_list_stack.connect('chat-unselected',
                                      self._on_chat_unselected)
        self._chat_list_stack.connect('chat-removed', self._on_chat_removed)
        self._chat_list_stack.connect('notify::visible-child-name',
                                      self._on_chat_list_changed)
        self._ui.chat_list_scrolled.add(self._chat_list_stack)

        self._ui.start_chat_menu_button.set_menu_model(
            get_start_chat_button_menu())

        self._ui.paned.set_position(app.settings.get('chat_handle_position'))
        self._ui.paned.connect('button-release-event', self._on_button_release)

        self._startup_finished: bool = False
        self._closed_chat_memory: list[tuple[str, JID, str]] = []

        self._add_actions()

        self.show_all()

    def _add_actions(self):
        actions = [
            ('remove-chat', 'as', self._remove_chat),
            ('search-history', None, self._on_search_history),
        ]

        for action in actions:
            action_name, variant, func = action
            if variant is not None:
                variant = GLib.VariantType.new(variant)
            act = Gio.SimpleAction.new(action_name, variant)
            act.connect('activate', func)
            app.window.add_action(act)

    def set_startup_finished(self) -> None:
        self._startup_finished = True

    def get_chat_list_stack(self) -> ChatListStack:
        return self._chat_list_stack

    def get_chat_stack(self) -> ChatStack:
        return self._chat_stack

    @staticmethod
    def _on_button_release(paned: Gtk.Paned, event: Gdk.EventButton) -> None:
        if event.window != paned.get_handle_window():
            return
        position = paned.get_position()
        app.settings.set('chat_handle_position', position)

    def _on_filter_revealer_toggled(self,
                                    toggle_button: Gtk.ToggleButton) -> None:
        active = toggle_button.get_active()
        self._ui.filter_bar_revealer.set_reveal_child(active)
        self._chat_filter.reset()

    @staticmethod
    def _on_edit_workspace_clicked(_button: Gtk.Button) -> None:
        app.window.activate_action('edit-workspace', GLib.Variant('s', ''))

    def _on_chat_selected(self,
                          _chat_list_stack: ChatListStack,
                          workspace_id: str,
                          account: str,
                          jid: JID) -> None:

        self._chat_stack.show_chat(account, jid)

        if (not self._search_revealer.get_reveal_child() and
                self._restore_occupants_list and
                self._chat_control.contact.is_groupchat):
            # GroupchatRoster was hidden by Search initially, but Search was
            # afterwards closed in a 1:1 chat. Only restore GroupchatRoster if
            # a group chat was selected.
            app.settings.set('hide_groupchat_occupants_list', False)
            self._restore_occupants_list = False

        if not app.settings.get('hide_groupchat_occupants_list'):
            self._search_view.set_context(account, jid)

        self.emit('chat-selected', workspace_id, account, jid)

    def _on_chat_unselected(self, _chat_list_stack: ChatListStack) -> None:
        self._chat_stack.clear()
        self._search_view.set_context(None, None)

    def _on_search_history(self,
                           _action: Gio.SimpleAction,
                           _param: Literal[None]) -> None:

        if self._chat_control.has_active_chat():
            self._search_view.set_context(self._chat_control.contact.account,
                                          self._chat_control.contact.jid)

        if not app.settings.get('hide_groupchat_occupants_list'):
            # Hide group chat roster in order to make some space horizontally.
            # Store state to be able to restore it when hiding search.
            self._restore_occupants_list = True
            app.settings.set('hide_groupchat_occupants_list', True)

        self._search_revealer.set_reveal_child(True)
        self._search_view.set_focus()

    def _on_search_hide(self, *args: Any) -> None:
        self.hide_search()

    def _on_chat_list_changed(self,
                              chat_list_stack: ChatListStack,
                              *args: Any) -> None:

        chat_list = chat_list_stack.get_current_chat_list()
        assert chat_list is not None
        name = app.settings.get_workspace_setting(chat_list.workspace_id,
                                                  'name')
        self._ui.workspace_label.set_text(name)
        self._ui.search_entry.set_text('')
        self._ui.chat_list_scrolled.get_vadjustment().set_value(0)

    def add_chat_list(self, workspace_id: str) -> None:
        self._chat_list_stack.add_chat_list(workspace_id)

    def show_workspace_chats(self, workspace_id: str) -> None:
        self._chat_list_stack.show_chat_list(workspace_id)
        self._ui.filter_bar_toggle.set_active(False)
        self._chat_filter.reset()

    def update_workspace(self, workspace_id: str) -> None:
        name = app.settings.get_workspace_setting(workspace_id, 'name')
        self._ui.workspace_label.set_text(name)

    def remove_chat_list(self, workspace_id: str) -> None:
        self._chat_list_stack.remove_chat_list(workspace_id)

    def chat_exists(self, account: str, jid: JID) -> bool:
        return self._chat_list_stack.contains_chat(account, jid)

    def select_chat(self, account: str, jid: JID) -> None:
        self._chat_list_stack.select_chat(account, jid)

    def chat_exists_for_workspace(self,
                                  workspace_id: str,
                                  account: str,
                                  jid: JID) -> bool:

        return self._chat_list_stack.contains_chat(
            account, jid, workspace_id=workspace_id)

    def add_chat_for_workspace(self,
                               workspace_id: str,
                               account: str,
                               jid: JID,
                               type_: str,
                               pinned: bool = False,
                               position: int = -1,
                               select: bool = False,
                               message: str | None = None) -> None:

        client = app.get_client(account)

        if type_ == 'chat':
            client.get_module('Contacts').add_chat_contact(jid)

        elif type_ == 'groupchat':
            client.get_module('Contacts').add_group_chat_contact(jid)

        elif type_ == 'pm':
            client.get_module('Contacts').add_private_contact(jid)

        if self.chat_exists(account, jid):
            if select:
                self._chat_list_stack.select_chat(account, jid)
            return

        self._chat_list_stack.add_chat(workspace_id, account, jid, type_,
                                       pinned, position)

        if self._startup_finished:
            if select:
                self._chat_list_stack.select_chat(account, jid)
            self._chat_list_stack.store_open_chats(workspace_id)
            if message is not None:
                message_input = self._chat_stack.get_message_input()
                message_input.insert_text(message)

    def load_workspace_chats(self, workspace_id: str) -> None:
        open_chats = app.settings.get_workspace_setting(workspace_id,
                                                        'chats')

        active_accounts = app.settings.get_active_accounts()
        for open_chat in open_chats:
            account = open_chat['account']
            if account not in active_accounts:
                continue

            self.add_chat_for_workspace(workspace_id,
                                        account,
                                        open_chat['jid'],
                                        open_chat['type'],
                                        pinned=open_chat['pinned'],
                                        position=open_chat['position'])

    def is_chat_selected(self, account: str, jid: JID) -> bool:
        return self._chat_list_stack.is_chat_selected(account, jid)

    def restore_chat(self) -> None:
        if not self._closed_chat_memory:
            return

        account, jid, workspace_id = self._closed_chat_memory.pop()

        client = app.get_client(account)
        contact = client.get_module('Contacts').get_contact(jid)

        self.add_chat_for_workspace(workspace_id,
                                    account,
                                    jid,
                                    contact.type_string,
                                    select=True)

    def _remove_chat(self,
                     _action: Gio.SimpleAction,
                     param: GLib.Variant) -> None:

        account, jid = param.unpack()
        jid = JID.from_string(jid)

        self.remove_chat(account, jid)

    def remove_chat(self, account: str, jid: JID) -> None:
        for workspace_id in app.settings.get_workspaces():
            if self.chat_exists_for_workspace(workspace_id, account, jid):
                self._closed_chat_memory.append((account, jid, workspace_id))
                self._chat_list_stack.remove_chat(workspace_id, account, jid)
                return

    def _on_chat_removed(self,
                         _chat_list: ChatList,
                         account: str,
                         jid: JID,
                         type_: str
                         ) -> None:

        if self._chat_control.is_loaded(account, jid):
            self._chat_control.clear()

        if type_ == 'groupchat' and app.account_is_connected(account):
            client = app.get_client(account)
            client.get_module('MUC').leave(jid)

    def remove_chats_for_account(self, account: str) -> None:
        chat_list = self._chat_list_stack.get_current_chat_list()
        if chat_list is not None:
            chat_list.unselect_all()

        self._chat_list_stack.remove_chats_for_account(account)
        if self._chat_control.has_active_chat():
            if self._chat_control.contact.account == account:
                self._chat_control.clear()

    def get_control(self) -> ChatControl:
        return self._chat_control

    def hide_search(self) -> bool:
        if self._search_revealer.get_reveal_child():
            self._search_revealer.set_reveal_child(False)

            if (self._restore_occupants_list and
                    self._chat_control.has_active_chat() and
                    self._chat_control.contact.is_groupchat):
                # Restore GroupchatRoster only if a group chat is selected
                # currently. If this condition isn' satisfied, it is checked
                # again as soon as a chat is selected in _on_chat_selected.
                app.settings.set('hide_groupchat_occupants_list', False)
                self._restore_occupants_list = False

            return True
        return False

    def toggle_chat_list(self) -> None:
        chat_list = self._ui.paned.get_child1()
        assert chat_list is not None
        chat_list.set_visible(not chat_list.get_visible())
