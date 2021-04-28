import logging

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gio

from gajim.common import app
from gajim.common import ged
from gajim.common.helpers import ask_for_status_message
from gajim.common.i18n import _
from gajim.common.nec import EventHelper

from gajim.gui.adhoc import AdHocCommand
from gajim.gui.account_side_bar import AccountSideBar
from gajim.gui.workspace_side_bar import WorkspaceSideBar
from gajim.gui.main_stack import MainStack
from gajim.gui.dialogs import DialogButton
from gajim.gui.dialogs import ConfirmationDialog
from gajim.gui.util import get_builder
from gajim.gui.util import load_icon

from .util import open_window

log = logging.getLogger('gajim.gui.main')


class MainWindow(Gtk.ApplicationWindow, EventHelper):
    def __init__(self):
        Gtk.ApplicationWindow.__init__(self)
        EventHelper.__init__(self)
        self.set_application(app.app)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_title('Gajim')
        self.set_default_size(1000, 500)

        app.window = self

        self._startup_finished = False

        self._ui = get_builder('main.ui')

        self.add(self._ui.main_grid)

        surface = load_icon('org.gajim.Gajim', self, 40)
        self._ui.app_image.set_from_surface(surface)

        self._main_stack = MainStack()
        self._ui.main_grid.add(self._main_stack)

        self._chat_page = self._main_stack.get_chat_page()

        self._workspace_side_bar = WorkspaceSideBar(self._chat_page)
        self._ui.workspace_scrolled.add(self._workspace_side_bar)

        self._account_side_bar = AccountSideBar()
        self._ui.account_box.add(self._account_side_bar)

        self._ui.connect_signals(self)

        self.register_events([
            ('presence-received', ged.GUI1, self._on_event),
            ('caps-update', ged.GUI1, self._on_event),
            ('message-sent', ged.OUT_POSTCORE, self._on_event),
            ('message-received', ged.CORE, self._on_event),
            ('mam-message-received', ged.CORE, self._on_event),
            ('gc-message-received', ged.CORE, self._on_event),
            ('receipt-received', ged.GUI1, self._on_event),
            ('displayed-received', ged.GUI1, self._on_event),
            ('message-error', ged.GUI1, self._on_event),
            ('muc-creation-failed', ged.GUI1, self._on_event),
            ('muc-self-presence', ged.GUI1, self._on_event),
            ('muc-voice-request', ged.GUI1, self._on_event),
            ('muc-disco-update', ged.GUI1, self._on_event),
            ('our-show', ged.GUI1, self._on_our_show),
            ('signed-in', ged.GUI1, self._on_signed_in),
        ])

        self._load_chats()
        self._add_actions()
        self._add_actions2()
        self.show_all()

    @staticmethod
    def _on_our_show(event):
        if event.show == 'offline':
            app.app.set_account_actions_state(event.account)
            app.app.update_app_actions_state()

    @staticmethod
    def _on_signed_in(event):
        app.app.set_account_actions_state(event.account, True)
        app.app.update_app_actions_state()

    def _add_actions(self):
        actions = [
            ('add-workspace', 's', self._add_workspace),
            ('edit-workspace', None, self._edit_workspace),
            ('remove-workspace', None, self._remove_workspace),
            ('activate-workspace', 's', self._activate_workspace),
            ('add-chat', 'a{sv}', self._add_chat),
            ('add-group-chat', 'as', self._add_group_chat),
            ('add-to-roster', 'as', self._add_to_roster),
        ]

        for action in actions:
            action_name, variant, func = action
            if variant is not None:
                variant = GLib.VariantType.new(variant)
            act = Gio.SimpleAction.new(action_name, variant)
            act.connect('activate', func)
            self.add_action(act)

    def _add_actions2(self):
        actions = [
            'change-nickname',
            'change-subject',
            'escape',
            'browse-history',
            'send-file',
            'show-contact-info',
            'show-emoji-chooser',
            'clear-chat',
            'delete-line',
            'close-tab',
            'move-tab-up',
            'move-tab-down',
            'switch-next-tab',
            'switch-prev-tab',
            'switch-next-unread-tab-right'
            'switch-next-unread-tab-left',
            'switch-tab-1',
            'switch-tab-2',
            'switch-tab-3',
            'switch-tab-4',
            'switch-tab-5',
            'switch-tab-6',
            'switch-tab-7',
            'switch-tab-8',
            'switch-tab-9',
        ]

        disabled_for_emacs = (
            'browse-history',
            'send-file',
            'close-tab'
        )

        key_theme = Gtk.Settings.get_default().get_property(
            'gtk-key-theme-name')

        for action in actions:
            if key_theme == 'Emacs' and action in disabled_for_emacs:
                continue
            act = Gio.SimpleAction.new(action, None)
            act.connect('activate', self._on_action)
            self.add_action(act)

    def _on_action(self, action, _param):
        control = self.get_active_control()
        if control is None:
            return

        log.info('Activate action: %s, active control: %s',
                 action.get_name(), control.contact.jid)

        action = action.get_name()

        res = control.delegate_action(action)
        if res != Gdk.EVENT_PROPAGATE:
            return res

        if action == 'escape':
            self._chat_page.hide_search()

        # if action == 'escape' and app.settings.get('escape_key_closes'):
        #     self.remove_tab(control, self.CLOSE_ESC)
        #     return

        # if action == 'close-tab':
        #     self.remove_tab(control, self.CLOSE_CTRL_KEY)
        #     return

        # if action == 'move-tab-up':
        #     old_position = self.notebook.get_current_page()
        #     self.notebook.reorder_child(control.widget,
        #                                 old_position - 1)
        #     return

        # if action == 'move-tab-down':
        #     old_position = self.notebook.get_current_page()
        #     total_pages = self.notebook.get_n_pages()
        #     if old_position == total_pages - 1:
        #         self.notebook.reorder_child(control.widget, 0)
        #     else:
        #         self.notebook.reorder_child(control.widget,
        #                                     old_position + 1)
        #     return

        # if action == 'switch-next-tab':
        #     new = self.notebook.get_current_page() + 1
        #     if new >= self.notebook.get_n_pages():
        #         new = 0
        #     self.notebook.set_current_page(new)
        #     return

        # if action == 'switch-prev-tab':
        #     new = self.notebook.get_current_page() - 1
        #     if new < 0:
        #         new = self.notebook.get_n_pages() - 1
        #     self.notebook.set_current_page(new)
        #     return

        # if action == 'switch-next-unread-tab-right':
        #     self.move_to_next_unread_tab(True)
        #     return

        # if action == 'switch-next-unread-tab-left':
        #     self.move_to_next_unread_tab(False)
        #     return

        # if action.startswith('switch-tab-'):
        #     number = int(action[-1])
        #     self.notebook.set_current_page(number - 1)
        #     return

    def _set_startup_finished(self):
        self._startup_finished = True
        self._chat_page.set_startup_finished()

    def show_account_page(self, account):
        self._account_side_bar.activate_account_page(account)
        self._main_stack.show_account(account)

    def get_active_workspace(self):
        return self._workspace_side_bar.get_active_workspace()

    def is_chat_active(self, account, jid):
        if not self.get_property('has-toplevel-focus'):
            return False
        return self._chat_page.is_chat_active(account, jid)

    def _add_workspace(self, _action, param):
        workspace_id = param.get_string()
        self.add_workspace(workspace_id)

    def add_workspace(self, workspace_id):
        self._workspace_side_bar.add_workspace(workspace_id)
        self._chat_page.add_chat_list(workspace_id)

        if self._startup_finished:
            self.activate_workspace(workspace_id)
            self._workspace_side_bar.store_workspace_order()

    def _edit_workspace(self, _action, _param):
        workspace_id = self.get_active_workspace()
        if workspace_id is not None:
            open_window('WorkspaceDialog', workspace_id=workspace_id)

    def _remove_workspace(self, _action, _param):
        workspace_id = self.get_active_workspace()
        if workspace_id is not None:
            self.remove_workspace(workspace_id)

    def remove_workspace(self, workspace_id):
        was_active = self.get_active_workspace() == workspace_id

        success = self._workspace_side_bar.remove_workspace(workspace_id)
        if not success:
            return

        if was_active:
            new_active_id = self._workspace_side_bar.get_first_workspace()
            self.activate_workspace(new_active_id)

        self._chat_page.remove_chat_list(workspace_id)
        app.settings.remove_workspace(workspace_id)

    def _activate_workspace(self, _action, param):
        workspace_id = param.get_string()
        self.activate_workspace(workspace_id)

    def activate_workspace(self, workspace_id):
        self._main_stack.show_chats(workspace_id)
        self._workspace_side_bar.activate_workspace(workspace_id)

    def update_workspace(self, workspace_id):
        self._chat_page.update_workspace(workspace_id)
        self._workspace_side_bar.update_avatar(workspace_id)

    def _add_group_chat(self, _action, param):
        self.add_group_chat(**param.unpack())

    def add_group_chat(self, account, jid, select=False):
        workspace_id = self.get_active_workspace()
        self._chat_page.add_chat_for_workspace(workspace_id,
                                               account,
                                               jid,
                                               'groupchat',
                                               select=select)

    def _add_chat(self, _action, param):
        self.add_chat(**param.unpack())

    def add_chat(self, account, jid, type_, select=False):
        workspace_id = self.get_active_workspace()
        self._chat_page.add_chat_for_workspace(workspace_id,
                                               account,
                                               jid,
                                               type_,
                                               select=select)

    def add_private_chat(self, account, jid, select=False):
        workspace_id = self.get_active_workspace()
        self._chat_page.add_chat_for_workspace(workspace_id,
                                               account,
                                               jid,
                                               'pm',
                                               select=select)

    @staticmethod
    def _add_to_roster(_action, param):
        _workspace, account, jid = param.unpack()
        open_window('AddNewContactWindow', account=account, contact_jid=jid)

    def get_control(self, *args, **kwargs):
        return self._chat_page.get_control(*args, **kwargs)

    def get_controls(self, *args, **kwargs):
        return self._chat_page.get_controls(*args, **kwargs)

    def get_active_control(self, *args, **kwargs):
        return self._chat_page.get_active_control(*args, **kwargs)

    def chat_exists(self, *args, **kwargs):
        return self._chat_page.chat_exists(*args, **kwargs)

    @staticmethod
    def contact_info(account, jid):
        client = app.get_client(account)
        contact = client.get_module('Contacts').get_contact(jid)
        open_window('ContactInfo', account=account, contact=contact)

    @staticmethod
    def execute_command(account, jid):
        # TODO: Resource?
        AdHocCommand(account, jid)

    def block_contact(self, account, jid):
        client = app.get_client(account)

        contact = client.get_module('Contacts').get_contact(jid)
        if contact.is_blocked:
            client.get_module('Blocking').unblock([jid])
            return

        # TODO: Keep "confirm_block" setting?
        def _block_contact(report=None):
            client.get_module('Blocking').block([contact.jid], report)
            self._chat_page.remove_chat(account, contact.jid)

        ConfirmationDialog(
            _('Block Contact'),
            _('Really block this contact?'),
            _('You will appear offline for this contact and you '
              'will not receive further messages.'),
            [DialogButton.make('Cancel'),
             DialogButton.make('OK',
                               text=_('_Report Spam'),
                               callback=_block_contact,
                               kwargs={'report': 'spam'}),
             DialogButton.make('Remove',
                               text=_('_Block'),
                               callback=_block_contact)],
            modal=False).show()

    def remove_contact(self, account, jid):
        client = app.get_client(account)

        def _remove_contact():
            self._chat_page.remove_chat(account, jid)
            client.get_module('Roster').delete_item(jid)

        contact = client.get_module('Contacts').get_contact(jid)
        sec_text = _('You are about to remove %(name)s (%(jid)s) from '
                     'your contact list.\n') % {
                         'name': contact.name,
                         'jid': jid}

        ConfirmationDialog(
            _('Remove Contact'),
            _('Remove contact from contact list'),
            sec_text,
            [DialogButton.make('Cancel'),
             DialogButton.make('Remove',
                               callback=_remove_contact)]).show()

    def _load_chats(self):
        for workspace_id in app.settings.get_workspaces():
            self.add_workspace(workspace_id)
            self._chat_page.load_workspace_chats(workspace_id)

        workspace_id = self._workspace_side_bar.get_first_workspace()
        self.activate_workspace(workspace_id)

        self._set_startup_finished()

    def _on_event(self, event):
        if event.name == 'caps-update':
            #TODO
            return

        if event.name == 'update-roster-avatar':
            return

        if not self.chat_exists(event.account, event.jid):
            if event.name == 'message-received':
                if event.properties.is_muc_pm:
                    self.add_private_chat(event.account,
                                          event.properties.jid,
                                          'pm')
                else:
                    self.add_chat(event.account,
                                  event.properties.jid,
                                  'contact')
            else:
                # No chat is open, dont handle any gui events
                return

        self._main_stack.process_event(event)

    def quit(self):
        accounts = list(app.connections.keys())
        get_msg = False
        for acct in accounts:
            if app.account_is_available(acct):
                get_msg = True
                break

        def on_continue2(message):
            if 'file_transfers' not in app.interface.instances:
                app.app.start_shutdown(message=message)
                return
            # check if there is an active file transfer
            from gajim.common.modules.bytestream import is_transfer_active
            files_props = app.interface.instances['file_transfers'].\
                files_props
            transfer_active = False
            for x in files_props:
                for y in files_props[x]:
                    if is_transfer_active(files_props[x][y]):
                        transfer_active = True
                        break

            if transfer_active:
                ConfirmationDialog(
                    _('Stop File Transfers'),
                    _('You still have running file transfers'),
                    _('If you quit now, the file(s) being transferred will '
                      'be lost.\n'
                      'Do you still want to quit?'),
                    [DialogButton.make('Cancel'),
                     DialogButton.make('Remove',
                                       text=_('_Quit'),
                                       callback=app.app.start_shutdown,
                                       kwargs={'message': message})]).show()
                return
            app.app.start_shutdown(message=message)

        def on_continue(message):
            if message is None:
                # user pressed Cancel to change status message dialog
                return
            # check if we have unread messages
            # unread = app.events.get_nb_events()

            # for event in app.events.get_all_events(['printed_gc_msg']):
            #     contact = app.contacts.get_groupchat_contact(event.jid)
            #     if contact is None or not contact.can_notify():
            #         unread -= 1

            # if unread:
            #     ConfirmationDialog(
            #         _('Unread Messages'),
            #         _('You still have unread messages'),
            #         _('Messages will only be available for reading them later '
            #           'if storing chat history is enabled and if the contact '
            #           'is in your contact list.'),
            #         [DialogButton.make('Cancel'),
            #          DialogButton.make('Remove',
            #                            text=_('_Quit'),
            #                            callback=on_continue2,
            #                            args=[message])]).show()
            #     return
            on_continue2(message)

        if get_msg and ask_for_status_message('offline'):
            open_window('StatusChange',
                        status='offline',
                        callback=on_continue,
                        show_pep=False)
        else:
            on_continue('')
