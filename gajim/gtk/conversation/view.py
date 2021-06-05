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

import logging
import time

from datetime import timedelta

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from gajim.common import app
from gajim.common.const import AvatarSize
from gajim.common.helpers import to_user_string
from gajim.common.helpers import get_start_of_day

from .rows.read_marker import ReadMarkerRow
from .rows.scroll_hint import ScrollHintRow
from .rows.message import MessageRow
from .rows.info import InfoMessage
from .rows.date import DateRow
from .rows.file_transfer import FileTransferRow
from .rows.muc_subject import MUCSubject
from .rows.muc_join_left import MUCJoinLeft
from .rows.muc_user_status import MUCUserStatus
from ..util import scroll_to_end

log = logging.getLogger('gajim.gui.conversation_view')


class ConversationView(Gtk.ListBox):

    __gsignals__ = {
        'quote': (
            GObject.SignalFlags.RUN_LAST | GObject.SignalFlags.ACTION,
            None,
            (str, )
        ),
    }

    def __init__(self, account, contact):
        Gtk.ListBox.__init__(self)
        self.set_selection_mode(Gtk.SelectionMode.NONE)
        self.set_sort_func(self._sort_func)
        self.set_filter_func(self._filter_func)
        self._account = account
        self._client = None
        if account is not None:
            self._client = app.get_client(account)
        self._contact = contact

        self.encryption_enabled = False
        self.autoscroll = True
        self.locked = False

        # Keeps track of the number of rows shown in ConversationView
        self._row_count = 0
        self._max_row_count = 100

        # Keeps track of date rows we have added to the list
        self._active_date_rows = set()

        # message_id -> row mapping
        self._message_id_row_map = {}

        app.settings.connect_signal('print_join_left',
                                    self._on_contact_setting_changed,
                                    account=self._account,
                                    jid=self._contact.jid)

        app.settings.connect_signal('print_status',
                                    self._on_contact_setting_changed,
                                    account=self._account,
                                    jid=self._contact.jid)

        if self._contact is not None:
            self._read_marker_row = ReadMarkerRow(self._account, self._contact)
            self.add(self._read_marker_row)

        self._scroll_hint_row = ScrollHintRow(self._account)
        self.add(self._scroll_hint_row)

    def lock(self):
        self.locked = True

    def unlock(self):
        self.locked = False

    def clear(self):
        for row in self.get_children()[2:]:
            self.remove(row)
        self._reset_conversation_view()

    def _reset_conversation_view(self):
        self._row_count = 0
        self._active_date_rows = set()
        self._message_id_row_map = {}

    def get_first_message_row(self):
        for row in self.get_children():
            if isinstance(row, MessageRow):
                return row
        return None

    def get_last_message_row(self):
        children = self.get_children()
        children.reverse()
        for row in children:
            if isinstance(row, MessageRow):
                return row
        return None

    def set_history_complete(self, complete):
        self._scroll_hint_row.set_history_complete(complete)

    @staticmethod
    def _sort_func(row1, row2):
        if row1.timestamp == row2.timestamp:
            return 0
        return -1 if row1.timestamp < row2.timestamp else 1

    def _filter_func(self, row):
        if row.type in ('muc-user-joined', 'muc-user-left'):
            return self._contact.settings.get('print_join_left')
        if row.type == 'muc-user-status':
            return self._contact.settings.get('print_status')

        return True

    def add_muc_subject(self, text, nick, date):
        subject = MUCSubject(self._account, text, nick, date)
        self._insert_message(subject)

    def add_muc_user_left(self, nick, reason, error=False):
        join_left = MUCJoinLeft('muc-user-left',
                                self._account,
                                nick,
                                reason=reason,
                                error=error)
        self._insert_message(join_left)

    def add_muc_user_joined(self, nick):
        join_left = MUCJoinLeft('muc-user-joined',
                                self._account,
                                nick)
        self._insert_message(join_left)

    def add_muc_user_status(self, user_contact, is_self):
        user_status = MUCUserStatus(self._account, user_contact, is_self)
        self._insert_message(user_status)

    def add_info_message(self, text):
        message = InfoMessage(self._account, text)
        self._insert_message(message)

    def add_file_transfer(self, transfer):
        transfer_row = FileTransferRow(self._account, transfer)
        self._insert_message(transfer_row)

    def add_message(self,
                    text,
                    kind,
                    name,
                    timestamp,
                    log_line_id=None,
                    message_id=None,
                    correct_id=None,
                    display_marking=None,
                    additional_data=None,
                    subject=None,
                    marker=None,
                    error=None):

        if not timestamp:
            timestamp = time.time()

        if correct_id:
            self.correct_message(correct_id, message_id, text)
            return

        avatar = self._get_avatar(kind, name)

        is_groupchat = False
        if self._contact is not None:
            is_groupchat = self._contact.is_groupchat

        message = MessageRow(
            self._account,
            message_id,
            timestamp,
            kind,
            name,
            text,
            avatar,
            is_groupchat,
            additional_data=additional_data,
            display_marking=display_marking,
            marker=marker,
            error=error,
            encryption_enabled=self.encryption_enabled,
            log_line_id=log_line_id)

        if message.type == 'chat':
            self._message_id_row_map[message.message_id] = message

        self._insert_message(message)

    def _get_avatar(self, kind, name):
        if self._contact is None:
            return None

        scale = self.get_scale_factor()
        if self._contact.is_groupchat:
            contact = self._contact.get_resource(name)
            return contact.get_avatar(AvatarSize.ROSTER, scale, add_show=False)

        if kind == 'outgoing':
            contact = self._client.get_module('Contacts').get_contact(
                str(self._client.get_own_jid().bare))
        else:
            contact = self._contact

        return contact.get_avatar(AvatarSize.ROSTER, scale, add_show=False)

    def _insert_message(self, message):
        self.add(message)
        self._add_date_row(message.timestamp)
        self._check_for_merge(message)
        GLib.idle_add(message.queue_resize)

    def _add_date_row(self, timestamp):
        start_of_day = get_start_of_day(timestamp)
        if start_of_day in self._active_date_rows:
            return

        date_row = DateRow(self._account, start_of_day)
        self._active_date_rows.add(start_of_day)
        self.add(date_row)

        row = self.get_row_at_index(date_row.get_index() + 1)
        if row is None:
            return

        if row.type != 'chat':
            return

        row.set_merged(False)

    def _check_for_merge(self, message):
        if message.type != 'chat':
            return

        ancestor = self._find_ancestor(message)
        if ancestor is None:
            self._update_descendants(message)
        else:
            if message.is_mergeable(ancestor):
                message.set_merged(True)

    def _find_ancestor(self, message):
        index = message.get_index()
        while index != 0:
            index -= 1
            row = self.get_row_at_index(index)
            if row is None:
                return None

            if row.type == 'read_marker':
                continue

            if row.type != 'chat':
                return None

            if not message.is_same_sender(row):
                return None

            if not row.is_merged:
                return row
        return None

    def _update_descendants(self, message):
        index = message.get_index()
        while True:
            index += 1
            row = self.get_row_at_index(index)
            if row is None:
                return

            if row.type == 'read_marker':
                continue

            if row.type != 'chat':
                return

            if message.is_mergeable(row):
                row.set_merged(True)
                continue

            if message.is_same_sender(row):
                row.set_merged(False)
                self._update_descendants(row)
            return

    def reduce_message_count(self, before):
        success = False
        row_count = len(self.get_children())
        while row_count > self._max_row_count:
            if before:
                if self._reduce_messages_before():
                    row_count -= 1
                    success = True
            else:
                self._reduce_messages_after()
                row_count -= 1
                success = True

        return success

    def _reduce_messages_before(self):
        success = False

        # We want to keep relevant DateRows when removing rows
        row1 = self.get_row_at_index(2)
        row2 = self.get_row_at_index(3)

        if row1.type == row2.type == 'date':
            # First two rows are date rows,
            # it’s safe to remove the fist row
            self.remove(row1)
            success = True

        if row1.type == 'date' and row2.type != 'date':
            # First one is a date row, keep it and
            # remove the second row instead
            self.remove(row2)
            success = True

        if row1.type != 'date':
            # Not a date row, safe to remove
            self.remove(row1)
            success = True

        return success

    def _reduce_messages_after(self):
        row = self.get_row_at_index(len(self.get_children()) - 1)
        self.remove(row)

    def scroll_to_message_and_highlight(self, log_line_id):
        highlight_row = None
        for row in self.get_children():
            row.get_style_context().remove_class(
                'conversation-search-highlight')
            if row.log_line_id == log_line_id:
                highlight_row = row

        if highlight_row is not None:
            highlight_row.get_style_context().add_class(
                'conversation-search-highlight')
            # This scrolls the ListBox to the highlighted row
            highlight_row.grab_focus()

    def _get_row_by_message_id(self, id_):
        return self._message_id_row_map.get(id_)

    def get_row_by_log_line_id(self, log_line_id):
        for row in self.get_children():
            if row.log_line_id == log_line_id:
                return row
        return None

    def iter_rows(self):
        for row in self.get_children():
            yield row

    def set_read_marker(self, id_):
        if id_ is None:
            self._read_marker_row.hide()
            return

        row = self._get_row_by_message_id(id_)
        if row is None:
            return

        row.set_displayed()

        timestamp = row.timestamp + timedelta(microseconds=1)
        self._read_marker_row.set_timestamp(timestamp)

    def update_avatars(self):
        for row in self.get_children():
            if row.type == 'chat':
                avatar = self._get_avatar(row.kind, row.name)
                row.update_avatar(avatar)

    def update_text_tags(self):
        for row in self.get_children():
            row.update_text_tags()

    def scroll_to_end(self, force=False):
        if self.autoscroll or force:
            GLib.idle_add(scroll_to_end, self.get_parent().get_parent())

    def correct_message(self, correct_id, message_id, text):
        message_row = self._get_row_by_message_id(correct_id)
        if message_row is not None:
            message_row.set_correction(text, message_id)
            message_row.set_merged(False)

    def show_receipt(self, id_):
        message_row = self._get_row_by_message_id(id_)
        if message_row is not None:
            message_row.set_receipt()

    def show_error(self, id_, error):
        message_row = self._get_row_by_message_id(id_)
        if message_row is not None:
            message_row.set_error(to_user_string(error))
            message_row.set_merged(False)

    def on_quote(self, text):
        self.emit('quote', text)

    def _on_contact_setting_changed(self, *args):
        self.invalidate_filter()
