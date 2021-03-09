# Copyright (C) 2005 Alex Mauer <hawke AT hawkesnest.net>
#                    Stéphan Kochen <stephan AT kochen.nl>
# Copyright (C) 2005-2006 Dimitur Kirov <dkirov AT gmail.com>
# Copyright (C) 2005-2007 Nikos Kouremenos <kourem AT gmail.com>
# Copyright (C) 2005-2014 Yann Leboulanger <asterix AT lagaule.org>
# Copyright (C) 2006 Travis Shirk <travis AT pobox.com>
#                    Stefan Bethge <stefan AT lanpartei.de>
# Copyright (C) 2006-2007 Jean-Marie Traissard <jim AT lapin.org>
# Copyright (C) 2007 Julien Pivotto <roidelapluie AT gmail.com>
# Copyright (C) 2007-2008 Stephan Erb <steve-e AT h3c.de>
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
import time
import logging
from datetime import datetime

from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Pango

from gajim.common import app
from gajim.common import helpers
from gajim.common.const import AvatarSize
from gajim.common.const import PEPEventType
from gajim.common.i18n import Q_
from gajim.common.i18n import _
from gajim.gtkgui_helpers import add_css_class

from .avatar import get_show_circle
from .util import get_builder
from .util import format_mood
from .util import format_activity
from .util import format_tune
from .util import format_location
from .util import get_css_show_class

log = logging.getLogger('gajim.gui.tooltips')


class GCTooltip:
    def __init__(self):
        self.contact = None

        self._ui = get_builder('tooltip_gc_contact.ui')

    def clear_tooltip(self):
        self.contact = None

    def get_tooltip(self, contact):
        if self.contact == contact:
            return True, self._ui.tooltip_grid

        self._populate_grid(contact)
        self.contact = contact
        return False, self._ui.tooltip_grid

    def _hide_grid_childs(self):
        """
        Hide all Elements of the Tooltip Grid
        """
        for child in self._ui.tooltip_grid.get_children():
            child.hide()

    def _populate_grid(self, contact):
        """
        Populate the Tooltip Grid with data of from the contact
        """
        self._hide_grid_childs()

        self._ui.nick.set_text(contact.name)
        self._ui.nick.show()

        # Status Message
        if contact.status:
            status = contact.status.strip()
            if status != '':
                self._ui.status.set_text(status)
                self._ui.status.show()

        # Status
        show = helpers.get_uf_show(contact.show.value)
        self._ui.user_show.set_text(show)
        colorize_status(self._ui.user_show, contact.show.value)
        self._ui.user_show.show()

        # JID
        if contact.real_jid is not None:
            self._ui.jid.set_text(str(contact.jid))
            self._ui.jid.show()

        # Affiliation
        if not contact.affiliation.is_none:
            uf_affiliation = helpers.get_uf_affiliation(contact.affiliation)
            uf_affiliation = \
                _('%(owner_or_admin_or_member)s of this group chat') \
                % {'owner_or_admin_or_member': uf_affiliation}
            self._ui.affiliation.set_text(uf_affiliation)
            self._ui.affiliation.show()

        # Avatar
        scale = self._ui.tooltip_grid.get_scale_factor()
        surface = contact.get_avatar(AvatarSize.TOOLTIP, scale)
        self._ui.avatar.set_from_surface(surface)
        self._ui.avatar.show()
        self._ui.fillelement.show()

        app.plugin_manager.gui_extension_point(
            'gc_tooltip_populate', self, contact, self._ui.tooltip_grid)

    def destroy(self):
        self._ui.tooltip_grid.destroy()


class RosterTooltip:
    def __init__(self):
        self._row = None
        self._ui = get_builder('roster_tooltip.ui')

    def clear_tooltip(self):
        self._row = None
        for widget in self._ui.resource_grid.get_children():
            widget.destroy()
        for widget in self._ui.tooltip_grid.get_children():
            widget.hide()

    def get_tooltip(self, row, contact):
        if self._row == row:
            return True, self._ui.tooltip_grid

        self._populate_grid(contact)
        self._row = row
        return False, self._ui.tooltip_grid

    def _populate_grid(self, contact):
        self.clear_tooltip()
        scale = self._ui.tooltip_grid.get_scale_factor()

        # Avatar
        surface = contact.get_avatar(AvatarSize.TOOLTIP, scale)
        self._ui.avatar.set_from_surface(surface)
        self._ui.avatar.show()

        # Name
        self._ui.name.set_markup(GLib.markup_escape_text(contact.name))
        self._ui.name.show()

        # JID
        self._ui.jid.set_text(str(contact.jid))
        self._ui.jid.show()

        # Resources with show, status, priority
        resources = contact.get_resources()
        self._build_resource_grid(resources, scale)

        # Subscription
        if contact.subscription and contact.subscription != 'both':
            # 'both' is the normal subscription value, just omit it
            self._ui.sub.set_text(helpers.get_uf_sub(contact.subscription))
            self._ui.sub.show()
            self._ui.sub_label.show()

        # PEP info
        # TODO
        # self._append_pep_info(contact)

        app.plugin_manager.gui_extension_point(
            'roster_tooltip_populate', self, contact, self._ui.tooltip_grid)

        # This sets the bottom-most widget to expand, in case the avatar
        # takes more space than the labels
        row_count = 1
        while row_count < 8:
            widget = self._ui.tooltip_grid.get_child_at(1, row_count)
            if widget and widget.get_visible():
                last_widget = widget
                row_count += 1
            else:
                break
        last_widget.set_vexpand(True)

    def _build_resource_grid(self, resources, scale):
        row_num = 0
        for contact in resources:
            show_surface = get_show_circle(
                contact.show, AvatarSize.ROSTER, scale)
            show_image = Gtk.Image.new_from_surface(show_surface)
            show_image.set_halign(Gtk.Align.START)
            show_image.set_valign(Gtk.Align.CENTER)
            self._ui.resource_grid.attach(show_image, 0, row_num, 1, 1)

            resource_string = GLib.markup_escape_text(contact.jid.resource)
            resource_label = Gtk.Label()
            resource_label.set_halign(Gtk.Align.START)
            resource_label.set_xalign(0)
            resource_label.set_ellipsize(Pango.EllipsizeMode.END)
            resource_label.set_max_width_chars(30)
            resource_label.set_text(f'{resource_string} ({contact.priority})')
            self._ui.resource_grid.attach(resource_label, 1, row_num, 1, 1)

            if contact.status:
                row_num += 1
                status_text = GLib.markup_escape_text(contact.status)
                status_label = Gtk.Label(label=status_text)
                status_label.set_halign(Gtk.Align.START)
                status_label.set_xalign(0)
                status_label.set_ellipsize(Pango.EllipsizeMode.END)
                status_label.set_max_width_chars(30)
                self._ui.resource_grid.attach(
                    status_label, 1, row_num, 1, 1)

            if contact.idle_time:
                row_num += 1
                idle_time = time.localtime(contact.idle_time)
                idle_time = datetime(*(idle_time[:6]))
                current = datetime.now()
                if idle_time.date() == current.date():
                    formatted = idle_time.strftime('%X')
                else:
                    formatted = idle_time.strftime('%c')
                idle_text = _('Idle since: %s') % formatted
                idle_label = Gtk.Label(label=idle_text)
                idle_label.set_halign(Gtk.Align.START)
                idle_label.set_xalign(0)
                self._ui.resource_grid.attach(
                    idle_label, 1, row_num, 1, 1)

            row_num += 1

        self._ui.resource_grid.show_all()

    def _append_pep_info(self, contact):
        if PEPEventType.MOOD in contact.pep:
            mood = format_mood(*contact.pep[PEPEventType.MOOD])
            self._ui.mood.set_markup(mood)
            self._ui.mood.show()
            self._ui.mood_label.show()

        if PEPEventType.ACTIVITY in contact.pep:
            activity = format_activity(*contact.pep[PEPEventType.ACTIVITY])
            self._ui.activity.set_markup(activity)
            self._ui.activity.show()
            self._ui.activity_label.show()

        if PEPEventType.TUNE in contact.pep:
            tune = format_tune(*contact.pep[PEPEventType.TUNE])
            self._ui.tune.set_markup(tune)
            self._ui.tune.show()
            self._ui.tune_label.show()

        if PEPEventType.LOCATION in contact.pep:
            location = format_location(contact.pep[PEPEventType.LOCATION])
            self._ui.location.set_markup(location)
            self._ui.location.show()
            self._ui.location_label.show()


class FileTransfersTooltip:
    def __init__(self):
        self.sid = None
        self.widget = None
        if app.settings.get('use_kib_mib'):
            self.units = GLib.FormatSizeFlags.IEC_UNITS
        else:
            self.units = GLib.FormatSizeFlags.DEFAULT

    def clear_tooltip(self):
        self.sid = None
        self.widget = None

    def get_tooltip(self, file_props, sid):
        if self.sid == sid:
            return True, self.widget

        self.widget = self._create_tooltip(file_props, sid)
        self.sid = sid
        return False, self.widget

    def _create_tooltip(self, file_props, _sid):
        ft_grid = Gtk.Grid.new()
        ft_grid.insert_column(0)
        ft_grid.set_row_spacing(6)
        ft_grid.set_column_spacing(12)
        current_row = 0
        properties = []
        name = file_props.name
        if file_props.type_ == 'r':
            file_name = os.path.split(file_props.file_name)[1]
        else:
            file_name = file_props.name
        properties.append((_('File Name: '),
                           GLib.markup_escape_text(file_name)))
        if file_props.type_ == 'r':
            type_ = Q_('?Noun:Download')
            actor = _('Sender: ')
            sender = file_props.sender.split('/')[0]
            name = app.contacts.get_first_contact_from_jid(
                file_props.tt_account, sender).get_shown_name()
        else:
            type_ = Q_('?Noun:Upload')
            actor = _('Recipient: ')
            receiver = file_props.receiver
            if hasattr(receiver, 'name'):
                name = receiver.get_shown_name()
            else:
                name = receiver.split('/')[0]
        properties.append((Q_('?transfer type:Type: '), type_))
        properties.append((actor, GLib.markup_escape_text(name)))

        transfered_len = file_props.received_len
        if not transfered_len:
            transfered_len = 0
        properties.append((Q_('?transfer status:Transferred: '),
                           GLib.format_size_full(transfered_len, self.units)))
        status = self._get_current_status(file_props)
        properties.append((Q_('?transfer status:Status: '), status))
        file_desc = file_props.desc or ''
        properties.append((_('Description: '),
                           GLib.markup_escape_text(file_desc)))

        while properties:
            property_ = properties.pop(0)
            label = Gtk.Label()
            label.set_halign(Gtk.Align.END)
            label.set_valign(Gtk.Align.CENTER)
            label.set_markup(property_[0])
            ft_grid.attach(label, 0, current_row, 1, 1)
            label = Gtk.Label()
            label.set_halign(Gtk.Align.START)
            label.set_valign(Gtk.Align.START)
            label.set_line_wrap(True)
            label.set_markup(property_[1])
            ft_grid.attach(label, 1, current_row, 1, 1)
            current_row += 1

        ft_grid.show_all()
        return ft_grid

    @staticmethod
    def _get_current_status(file_props):
        if file_props.stopped:
            return Q_('?transfer status:Aborted')
        if file_props.completed:
            return Q_('?transfer status:Completed')
        if file_props.paused:
            return Q_('?transfer status:Paused')
        if file_props.stalled:
            # stalled is not paused. it is like 'frozen' it stopped alone
            return Q_('?transfer status:Stalled')

        if file_props.connected:
            if file_props.started:
                return Q_('?transfer status:Transferring')
            return Q_('?transfer status:Not started')
        return Q_('?transfer status:Not started')


def colorize_status(widget, show):
    """
    Colorize the status message inside the tooltip by it's semantics.
    """
    css_class = get_css_show_class(show)[14:]
    add_css_class(widget, css_class, prefix='gajim-status-')
