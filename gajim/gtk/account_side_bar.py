
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

        self._accounts = list(app.connections.keys())
        for account in self._accounts:
            self.add_account(account)

    def add_account(self, account):
        self.add(Account(account))

    def remove_account(self, account):
        pass


class Account(Gtk.ListBoxRow):
    def __init__(self, account):
        Gtk.ListBoxRow.__init__(self)
        self.get_style_context().add_class('account-sidebar-item')
        self.set_selectable(False)
        image = AccountAvatar(account)

        account_color_bar = Gtk.Box()
        account_color_bar.set_size_request(6, -1)
        account_class = app.css_config.get_dynamic_class(account)
        account_color_bar.get_style_context().add_class(account_class)
        account_color_bar.get_style_context().add_class(
            'account-identifier-bar')

        account_box = Gtk.Box(spacing=6)
        account_box.set_tooltip_text(
            _('Account: %s') % app.get_account_label(account))
        account_box.add(account_color_bar)
        account_box.add(image)

        self.add(account_box)
        self.show_all()


class AccountAvatar(Gtk.Image):
    def __init__(self, account):
        Gtk.Image.__init__(self)

        jid = app.get_jid_from_account(account)
        contact = app.contacts.create_contact(jid, account)

        scale = self.get_scale_factor()
        surface = app.interface.get_avatar(contact,
                                           AvatarSize.ACCOUNT_SIDE_BAR,
                                           scale,
                                           style='round-corners')
        self.set_from_surface(surface)
