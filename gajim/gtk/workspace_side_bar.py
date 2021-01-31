
from gi.repository import Gtk
from gi.repository import GLib
from gajim.common.const import AvatarSize
from gajim.common import app

from gajim.common.i18n import _

from .util import open_window


class WorkspaceSideBar(Gtk.ListBox):
    def __init__(self):
        Gtk.ListBox.__init__(self)
        self.set_vexpand(True)
        self.set_valign(Gtk.Align.START)
        self.set_sort_func(self._sort_func)
        self.get_style_context().add_class('workspace-sidebar')
        self.add(AddWorkspace('add'))
        self.connect('button-press-event', self._on_button_press)
        self.connect('row-activated', self._on_row_activated)

        self._workspaces = {}

    @staticmethod
    def _sort_func(child1, child2):
        if child1.sort_index < child2.sort_index:
            return -1

        if child1.sort_index == child2.sort_index:
            return 0
        return 1

    def _on_button_press(self, _listbox, button_event):
        if button_event.button != 3:
            return
        row = self.get_row_at_y(button_event.y)
        WorspaceMenu(row)

    @staticmethod
    def _on_row_activated(_listbox, row):
        if row.workspace_id == 'add':
            open_window('WorkspaceDialog')
        else:
            app.window.activate_workspace(row.workspace_id)

    def add_workspace(self, workspace_id):
        row = Workspace(workspace_id)
        self._workspaces[workspace_id] = row
        self.add(row)

    def remove_workspace(self, workspace_id):
        if len(self._workspaces) == 1:
            return False
        row = self._workspaces.pop(workspace_id)
        self.remove(row)
        return True

    def activate_workspace(self, workspace_id):
        row = self.get_selected_row()
        if row is not None and row.workspace_id == workspace_id:
            return

        row = self._workspaces[workspace_id]
        self.select_row(row)

    def get_active_workspace(self):
        row = self.get_selected_row()
        if row is None:
            return None
        return row.workspace_id

    def get_first_workspace(self):
        for row in self.get_children():
            return row.workspace_id

    def update_avatar(self, workspace_id):
        row = self._workspaces[workspace_id]
        row.update_avatar()


class CommonWorkspace(Gtk.ListBoxRow):
    def __init__(self, workspace_id):
        Gtk.ListBoxRow.__init__(self)
        self.get_style_context().add_class('workspace-sidebar-item')

        self.workspace_id = workspace_id


class Workspace(CommonWorkspace):
    def __init__(self, workspace_id):
        CommonWorkspace.__init__(self, workspace_id)

        self.sort_index = 0

        self._image = WorkspaceAvatar(workspace_id)
        self._image.set_halign(Gtk.Align.CENTER)
        self.add(self._image)
        self.show_all()

    def update_avatar(self):
        self._image.update()


class AddWorkspace(CommonWorkspace):
    def __init__(self, workspace_id):
        CommonWorkspace.__init__(self, workspace_id)

        self.set_selectable(False)

        self.sort_index = 10000

        image = Gtk.Image.new_from_icon_name('list-add-symbolic',
                                             Gtk.IconSize.DND)
        image.set_halign(Gtk.Align.CENTER)
        image.get_style_context().add_class('dim-label')
        self.add(image)
        self.show_all()


class WorspaceMenu(Gtk.Popover):
    def __init__(self, row):
        Gtk.Popover.__init__(self)
        entries = [
            (_('Remove'), 'remove-workspace'),
        ]

        self._workspace_id = row.workspace_id

        box = Gtk.Box()
        for label, action in entries:
            button = Gtk.Button(label=label)
            button.connect('clicked', self._on_click, action)
            box.add(button)
        box.show_all()

        self.add(box)
        self.set_relative_to(row)
        self.popup()

    def _on_click(self, _button, action):
        self.popdown()
        self.set_relative_to(None)
        app.window.activate_action(action,
                                   GLib.Variant('s', self._workspace_id))


class WorkspaceAvatar(Gtk.Image):
    def __init__(self, workspace_id):
        Gtk.Image.__init__(self)
        self._workspace_id = workspace_id
        self.update()

    def update(self):
        scale = self.get_scale_factor()
        surface = app.interface.avatar_storage.get_workspace_surface(
            self._workspace_id, AvatarSize.WORKSPACE, scale)
        self.set_from_surface(surface)
