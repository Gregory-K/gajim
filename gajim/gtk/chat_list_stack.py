
from gi.repository import Gtk
from gi.repository import GObject

from gajim.common import app

from gajim.gui.chat_list import ChatList


HANDLED_EVENTS = [
    'message-received',
    'mam-message-received',
    'gc-message-received',
    'presence-received',
    'message-sent',
    'chatstate-received',
]


class ChatListStack(Gtk.Stack):

    __gsignals__ = {
        'unread-count-changed': (GObject.SignalFlags.RUN_LAST,
                                 None,
                                 (str, int)),
        'chat-selected': (GObject.SignalFlags.RUN_LAST,
                          None,
                          (str, str, str)),
    }

    def __init__(self, main_window, ui, chat_stack):
        Gtk.Stack.__init__(self)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_vhomogeneous(False)

        self._ui = ui
        self._chat_stack = chat_stack
        self._chat_lists = {}

        self.add_named(Gtk.Box(), 'default')

        self.show_all()
        self._ui.search_entry.connect(
            'search-changed', self._on_search_changed)

        main_window.connect('notify::is-active', self._on_window_active)

    def _on_window_active(self, window, _param):
        is_active = window.get_property('is-active')
        if is_active:
            chat = self.get_selected_chat()
            if chat is not None:
                chat.reset_unread()

    def get_chatlist(self, workspace_id):
        return self._chat_lists[workspace_id]

    def get_selected_chat(self):
        workspace_id = self.get_visible_child_name()
        if workspace_id == 'empty':
            return None

        chat_list = self._chat_lists[workspace_id]
        return chat_list.get_selected_chat()

    def is_chat_active(self, account, jid):
        chat = self.get_selected_chat()
        if chat is None:
            return False
        if chat.account != account or chat.jid != jid:
            return False
        return chat.is_active

    def _on_search_changed(self, search_entry):
        chat_list = self.get_visible_child()
        chat_list.set_filter_text(search_entry.get_text())

    def add_chat_list(self, workspace_id):
        chat_list = ChatList(workspace_id)
        chat_list.connect('row-selected', self._on_row_selected)

        self._chat_lists[workspace_id] = chat_list
        self.add_named(chat_list, workspace_id)
        return chat_list

    def remove_chat_list(self, workspace_id):
        chat_list = self._chat_lists[workspace_id]
        self.remove(chat_list)
        for account, jid, _ in chat_list.get_open_chats():
            self.remove_chat(workspace_id, account, jid)

        self._chat_lists.pop(workspace_id)
        chat_list.destroy()

    def _on_row_selected(self, _chat_list, row):
        if row is None:
            self._chat_stack.clear()
            return

        self._chat_stack.show_chat(row.account, row.jid)
        if row.is_active:
            row.reset_unread()
        self.emit('chat-selected', row.workspace_id, row.account, row.jid)

    def show_chat_list(self, workspace_id):
        current_workspace_id = self.get_visible_child_name()
        if current_workspace_id == workspace_id:
            return

        if current_workspace_id != 'default':
            self._chat_lists[current_workspace_id].unselect_all()

        self._ui.workspace_label.set_text(
            app.settings.get_workspace_setting(workspace_id, 'name'))
        self.set_visible_child_name(workspace_id)

    def add_chat(self, workspace_id, account, jid, type_, pinned=False):
        chat_list = self._chat_lists.get(workspace_id)
        if chat_list is None:
            chat_list = self.add_chat_list(workspace_id)
        chat_list.add_chat(account, jid, type_, pinned)

    def select_chat(self, account, jid):
        chat_list = self._find_chat(account, jid)
        if chat_list is None:
            return

        self.show_chat_list(chat_list.workspace_id)
        chat_list.select_chat(account, jid)

    def store_open_chats(self, workspace_id):
        chat_list = self._chat_lists[workspace_id]
        open_chats = chat_list.get_open_chats()
        app.settings.set_workspace_setting(
            workspace_id, 'open_chats', open_chats)

    def toggle_chat_pinned(self, workspace_id, account, jid):
        chat_list = self._chat_lists[workspace_id]
        chat_list.toggle_chat_pinned(account, jid)
        self.store_open_chats(workspace_id)

    def remove_chat(self, workspace_id, account, jid):
        chat_list = self._chat_lists[workspace_id]
        type_ = chat_list.get_chat_type(account, jid)
        chat_list.remove_chat(account, jid)
        self.store_open_chats(workspace_id)

        if not self.contains_chat(account, jid):
            self._chat_stack.remove_chat(account, jid)
            if type_ == 'groupchat':
                client = app.get_client(account)
                client.get_module('MUC').leave(jid)

    def _find_chat(self, account, jid):
        for chat_list in self._chat_lists.values():
            if chat_list.contains_chat(account, jid):
                return chat_list
        return None

    def contains_chat(self, account, jid, workspace_id=None):
        if workspace_id is None:
            for chat_list in self._chat_lists.values():
                if chat_list.contains_chat(account, jid):
                    return True
            return False

        chat_list = self._chat_lists[workspace_id]
        return chat_list.contains_chat(account, jid)

    def process_event(self, event):
        if event.name not in HANDLED_EVENTS:
            return

        chat_list = self._find_chat(event.account, event.jid)
        if chat_list is None:
            return
        chat_list.process_event(event)