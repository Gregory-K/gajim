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

from gi.repository import Gdk
from gi.repository import Gtk

from gajim.common import app
from gajim.common import helpers
from gajim.common.i18n import _

from gajim.gtk.util import get_builder
from gajim.gtk.util import get_app_window


class ManageSounds:
    def __init__(self):
        self._ui = get_builder('manage_sounds_window.ui')
        self.window = self._ui.manage_sounds_window
        self.window.set_transient_for(app.app.get_active_window())

        filter_ = Gtk.FileFilter()
        filter_.set_name(_('All files'))
        filter_.add_pattern('*')
        self._ui.filechooser.add_filter(filter_)

        filter_ = Gtk.FileFilter()
        filter_.set_name(_('Wav Sounds'))
        filter_.add_pattern('*.wav')
        self._ui.filechooser.add_filter(filter_)
        self._ui.filechooser.set_filter(filter_)

        self._fill_sound_treeview()

        self._ui.connect_signals(self)

        self.window.show_all()

    @staticmethod
    def _on_row_changed(model, path, iter_):
        sound_event = model[iter_][3]
        app.settings.set_soundevent_setting(sound_event,
                                            'enabled',
                                            bool(model[path][0]))
        app.settings.set_soundevent_setting(sound_event,
                                            'path',
                                            model[iter_][2])

    def _on_toggle(self, _cell, path):
        if self._ui.filechooser.get_filename() is None:
            return
        model = self._ui.sounds_treeview.get_model()
        model[path][0] = not model[path][0]

    def _fill_sound_treeview(self):
        model = self._ui.sounds_treeview.get_model()
        model.clear()

        # pylint: disable=line-too-long
        sounds_dict = {
            'attention_received': _('Attention Message Received'),
            'first_message_received': _('First Message Received'),
            'next_message_received_focused': _('Next Message Received Focused'),
            'next_message_received_unfocused': _('Next Message Received Unfocused'),
            'contact_connected': _('Contact Connected'),
            'contact_disconnected': _('Contact Disconnected'),
            'message_sent': _('Message Sent'),
            'muc_message_highlight': _('Group Chat Message Highlight'),
            'muc_message_received': _('Group Chat Message Received'),
        }
        # pylint: enable=line-too-long

        for sound_event, sound_name in sounds_dict.items():
            settings = app.settings.get_soundevent_settings(sound_event)
            model.append((settings['enabled'],
                          sound_name,
                          settings['path'],
                          sound_event))

    def _on_cursor_changed(self, treeview):
        model, iter_ = treeview.get_selection().get_selected()
        path_to_snd_file = helpers.check_soundfile_path(model[iter_][2])
        if path_to_snd_file is None:
            self._ui.filechooser.unselect_all()
        else:
            self._ui.filechooser.set_filename(path_to_snd_file)

    def _on_file_set(self, button):
        model, iter_ = self._ui.sounds_treeview.get_selection().get_selected()

        filename = button.get_filename()
        directory = os.path.dirname(filename)
        app.settings.set('last_sounds_dir', directory)
        path_to_snd_file = helpers.strip_soundfile_path(filename)

        # set new path to sounds_model
        model[iter_][2] = path_to_snd_file
        # set the sound to enabled
        model[iter_][0] = True

    def _on_clear(self, *args):
        self._ui.filechooser.unselect_all()
        model, iter_ = self._ui.sounds_treeview.get_selection().get_selected()
        model[iter_][2] = ''
        model[iter_][0] = False

    def _on_play(self, *args):
        model, iter_ = self._ui.sounds_treeview.get_selection().get_selected()
        snd_event_config_name = model[iter_][3]
        helpers.play_sound(snd_event_config_name)

    def _on_key_press(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.window.destroy()

    @staticmethod
    def _on_destroy(*args):
        window = get_app_window('Preferences')
        if window is not None:
            window.sounds_preferences = None
