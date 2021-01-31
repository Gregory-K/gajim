
from gi.repository import GLib
from gi.repository import Gtk

from gajim.common.const import AvatarSize
from gajim.common import app
from gajim.common.i18n import _


class AccountSideBar(Gtk.ListBox):
    def __init__(self):
        Gtk.ListBox.__init__(self)
        self.set_vexpand(True)
        self.set_valign(Gtk.Align.END)
        self.get_style_context().add_class('account-sidebar')
        self.connect('row-activated', self._on_row_activated)

        self._accounts = list(app.connections.keys())
        for account in self._accounts:
            self.add_account(account)

    def add_account(self, account):
        self.add(Account(account))

    def remove_account(self, account):
        pass

    def _on_row_activated(self, _listbox, row):
        main_window = self.get_toplevel()
        main_window.activate_action(
            'activate-account-page', GLib.Variant('s', row.account))

    def activate_account_page(self, account):
        row = self.get_selected_row()
        if row is not None and row.account == account:
            return

        self.select_row(row)


class Account(Gtk.ListBoxRow):
    def __init__(self, account):
        Gtk.ListBoxRow.__init__(self)
        self.get_style_context().add_class('account-sidebar-item')
        self.set_selectable(False)

        self.account = account
        self._account_class = None
        self._image = AccountAvatar(account)

        self._account_color_bar = Gtk.Box()
        self._account_color_bar.set_size_request(6, -1)
        self._account_color_bar.get_style_context().add_class(
            'account-identifier-bar')

        account_box = Gtk.Box(spacing=6)
        account_box.set_tooltip_text(
            _('Account: %s') % app.get_account_label(account))
        account_box.add(self._account_color_bar)
        account_box.add(self._image)
        self._update_account_color()

        self.add(account_box)
        self.show_all()

    def _update_account_color(self):
        context = self._account_color_bar.get_style_context()
        if self._account_class is not None:
            context.remove_class(self._account_class)

        self._account_class = app.css_config.get_dynamic_class(self.account)
        context.add_class(self._account_class)

    def update(self):
        self._update_account_color()
        self._image.update()


class AccountAvatar(Gtk.Image):
    def __init__(self, account):
        Gtk.Image.__init__(self)
        self._account = account
        self.update()

    def update(self):
        jid = app.get_jid_from_account(self._account)
        contact = app.contacts.create_contact(jid, self._account)
        client = app.get_client(self._account)

        surface = app.interface.get_avatar(contact,
                                           AvatarSize.ACCOUNT_SIDE_BAR,
                                           self.get_scale_factor(),
                                           style='round-corners',
                                           show=client.status)
        self.set_from_surface(surface)
