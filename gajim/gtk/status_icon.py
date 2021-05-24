# Copyright (C) 2006 Nikos Kouremenos <kourem AT gmail.com>
# Copyright (C) 2006-2007 Jean-Marie Traissard <jim AT lapin.org>
# Copyright (C) 2006-2014 Yann Leboulanger <asterix AT lagaule.org>
# Copyright (C) 2007 Lukas Petrovicky <lukas AT petrovicky.net>
#                    Julien Pivotto <roidelapluie AT gmail.com>
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

from gi.repository import Gtk
from gi.repository import GLib

from gajim.common import app
from gajim.common import configpaths
from gajim.common import ged
from gajim.common.i18n import _
from gajim.common.helpers import get_global_show
from gajim.common.helpers import get_uf_show
from gajim.common.nec import EventHelper

from .util import get_builder
from .util import get_icon_name
from .util import save_roster_position
from .util import restore_roster_position
from .util import open_window

HAS_INDICATOR = False
if app.is_installed('APPINDICATOR'):
    from gi.repository import AppIndicator3 as appindicator
    HAS_INDICATOR = True
elif app.is_installed('AYATANA_APPINDICATOR'):
    from gi.repository import AyatanaAppIndicator3 as appindicator
    HAS_INDICATOR = True


class StatusIcon(EventHelper):
    """
    Class for the notification area icon
    """
    def __init__(self):
        EventHelper.__init__(self)

        self._ui = get_builder('systray_context_menu.ui')
        self._ui.connect_signals(self)

        self._popup_menus = []
        self._hide_menuitem_added = False
        self._status_icon = None

        self._ui.sounds_mute_menuitem.set_active(
            not app.settings.get('sounds_on'))
        self._add_status_menu()

        self.register_events([
            ('our-show', ged.GUI1, self._on_our_show),
            ('account-connected', ged.CORE, self._on_account_state),
            ('account-disconnected', ged.CORE, self._on_account_state),
        ])

    def _on_our_show(self, _event):
        self.update_icon()

    def _on_account_state(self, _event):
        account_connected = bool(app.get_number_of_connected_accounts() > 0)
        self._ui.start_chat_menuitem.set_sensitive(account_connected)

    def show_icon(self):
        if not self._status_icon:
            if HAS_INDICATOR:
                self._status_icon = appindicator.Indicator.new(
                    'Gajim',
                    'dcraven-online',
                    appindicator.IndicatorCategory.COMMUNICATIONS)
                self._status_icon.set_icon_theme_path(
                    str(configpaths.get('ICONS')))
                self._status_icon.set_attention_icon_full(
                    'mail-unread', 'New Message')
                self._status_icon.set_status(
                    appindicator.IndicatorStatus.ACTIVE)
                self._status_icon.set_menu(self._ui.systray_context_menu)
                self._status_icon.set_secondary_activate_target(
                    self._ui.toggle_window_menuitem)
            else:
                self._status_icon = Gtk.StatusIcon()
                self._status_icon.connect(
                    'activate', self._on_activate)
                self._status_icon.connect(
                    'popup-menu', self._on_popup_menu)
                self._status_icon.connect(
                    'size-changed', self.update_icon)

        self.update_icon()
        self._subscribe_events()

    def hide_icon(self):
        if HAS_INDICATOR:
            self._status_icon.set_status(appindicator.IndicatorStatus.PASSIVE)
        else:
            self._status_icon.set_visible(False)
        self._unsubscribe_events()

    def update_icon(self, *args):
        if not app.interface.systray_enabled:
            return
        if app.settings.get('trayicon') == 'always':
            if HAS_INDICATOR:
                self._status_icon.set_status(
                    appindicator.IndicatorStatus.ACTIVE)
            else:
                self._status_icon.set_visible(True)
        if app.events.get_nb_systray_events():
            icon_name = get_icon_name('event')
            if HAS_INDICATOR:
                self._status_icon.set_icon_full(icon_name, _('Pending Event'))
                self._status_icon.set_status(
                    appindicator.IndicatorStatus.ATTENTION)
            else:
                self._status_icon.set_visible(True)
                self._status_icon.set_from_icon_name(icon_name)
            return

        if app.settings.get('trayicon') == 'on_event':
            if HAS_INDICATOR:
                self._status_icon.set_status(
                    appindicator.IndicatorStatus.PASSIVE)
            else:
                self._status_icon.set_visible(False)

        show = get_global_show()
        icon_name = get_icon_name(show)
        if HAS_INDICATOR:
            self._status_icon.set_icon_full(icon_name, show)
            self._status_icon.set_status(appindicator.IndicatorStatus.ACTIVE)
        else:
            self._status_icon.set_from_icon_name(icon_name)

    def _subscribe_events(self):
        app.events.event_added_subscribe(self._on_event_added)
        app.events.event_removed_subscribe(self._on_event_removed)

    def _unsubscribe_events(self):
        app.events.event_added_unsubscribe(self._on_event_added)
        app.events.event_removed_unsubscribe(self._on_event_removed)

    def _on_event_added(self, event):
        if event.show_in_systray:
            self.update_icon()

    def _on_event_removed(self, _event_list):
        self.update_icon()

    def _on_popup_menu(self, _status_icon, button, activate_time):
        if button == 1:
            self._on_activate()
        elif button == 2:
            self._on_activate()
        elif button == 3:
            self._build_menu(activate_time)

    def _build_menu(self, event_time):
        for menu in self._popup_menus:
            menu.destroy()

        self._add_status_menu()

        self._ui.sounds_mute_menuitem.set_active(
            not app.settings.get('sounds_on'))

        if os.name == 'nt':
            # Workaround for popup menu on Windows
            if not self._hide_menuitem_added:
                self._ui.systray_context_menu.prepend(
                    Gtk.SeparatorMenuItem.new())
                item = Gtk.MenuItem.new_with_label(
                    _('Hide this menu'))
                self._ui.systray_context_menu.prepend(item)
                self._hide_menuitem_added = True

        self._ui.systray_context_menu.show_all()
        self._ui.systray_context_menu.popup(
            None, None, None, None, 0, event_time)

    def _add_status_menu(self):
        sub_menu = Gtk.Menu()

        for show in ('online', 'away', 'xa', 'dnd'):
            uf_show = get_uf_show(show, use_mnemonic=True)
            item = Gtk.MenuItem.new_with_mnemonic(uf_show)
            sub_menu.append(item)
            item.connect('activate', self._on_show, show)

        sub_menu.append(Gtk.SeparatorMenuItem())

        uf_show = get_uf_show('offline', use_mnemonic=True)
        item = Gtk.MenuItem.new_with_mnemonic(uf_show)
        item.connect('activate', self._on_show, 'offline')
        sub_menu.append(item)
        sub_menu.show_all()

        self._popup_menus.append(sub_menu)
        self._ui.status_menu.set_submenu(sub_menu)

    @staticmethod
    def _on_new_chat(_widget):
        app.app.activate_action('start-chat', GLib.Variant('s', ''))

    @staticmethod
    def _on_show_all_events(_widget):
        events = app.events.get_systray_events()
        for account in events:
            for jid in events[account]:
                for event in events[account][jid]:
                    app.interface.handle_event(account, jid, event.type_)

    @staticmethod
    def _on_sounds_mute(widget):
        app.settings.set('sounds_on', not widget.get_active())

    def _on_toggle_window(self, *args):
        # When using Gtk.StatusIcon, app.window will never return True for
        # 'has-toplevel-focus' while clicking the menu item
        GLib.idle_add(self._on_activate)

    @staticmethod
    def _on_preferences(_widget):
        open_window('Preferences')

    @staticmethod
    def _on_quit(_widget):
        app.window.quit()

    def _on_activate(self, *args):
        if app.events.get_systray_events():
            self._handle_first_event()
            return

        if app.window.get_property('has-toplevel-focus'):
            save_roster_position(app.window)
            app.window.hide()
            return

        app.window.show_all()
        if not app.window.get_property('visible'):
            # Window was minimized
            restore_roster_position(app.window)

        if not app.settings.get('roster_window_skip_taskbar'):
            app.window.set_property('skip-taskbar-hint', False)
        app.window.present_with_time(Gtk.get_current_event_time())

    @staticmethod
    def _handle_first_event():
        account, jid, event = app.events.get_first_systray_event()
        if not event:
            return
        if not app.window.get_property('visible'):
            restore_roster_position(app.window)
        app.interface.handle_event(account, jid, event.type_)

    @staticmethod
    def _on_show(_widget, show):
        app.interface.change_status(status=show)
