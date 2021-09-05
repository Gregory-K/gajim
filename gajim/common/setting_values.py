
import uuid

from gajim.common.i18n import _

class _DEFAULT:
    pass

class _ACCOUNT_DEFAULT:
    pass

HAS_APP_DEFAULT = _DEFAULT()
HAS_ACCOUNT_DEFAULT = _ACCOUNT_DEFAULT()

# pylint: disable=line-too-long

APP_SETTINGS = {
    'autopopup': False,
    'show_notifications': True,
    'autopopupaway': False,
    'sounddnd': False,
    'showoffline': True,
    'show_only_chat_and_online': False,
    'show_transports_group': True,
    'autoaway': True,
    'autoawaytime': 5,
    'autoaway_message': '',
    'autoxa': True,
    'autoxatime': 15,
    'autoxa_message': '',
    'ask_online_status': False,
    'ask_offline_status': False,
    'trayicon': 'always',
    'allow_hide_roster': False,
    'iconset': 'dcraven',
    'use_transports_iconsets': True,
    'collapsed_rows': '',
    'roster_theme': 'default',
    'sort_by_show_in_roster': True,
    'sort_by_show_in_muc': False,
    'use_speller': False,
    'show_xhtml': True,
    'speller_language': '',
    'emoticons_theme': 'noto-emoticons',
    'ascii_formatting': True,
    'show_ascii_formatting_chars': True,
    'sounds_on': True,
    'gc_refer_to_nick_char': ',',
    'mainwin_x_position': 0,
    'mainwin_y_position': 0,
    'mainwin_width': 1000,
    'mainwin_height': 500,
    'save_main_window_position': True,
    'show_main_window_on_startup': 'always',
    'last_main_window_visible': True,
    'quit_on_main_window_x_button': False,
    'hide_on_main_window_x_button': False,
    'main_window_skip_taskbar': False,
    'roster_on_the_right': False,
    'latest_disco_addresses': '',
    'time_stamp': '%x | %X  ',
    'change_roster_title': True,
    'restore_timeout': -1,
    'send_on_ctrl_enter': False,
    'key_up_lines': 25,
    'search_engine': 'https://duckduckgo.com/?q=%s',
    'dictionary_url': 'WIKTIONARY',
    'always_english_wikipedia': False,
    'always_english_wiktionary': True,
    'remote_control': False,
    'confirm_paste_image': True,
    'confirm_close_muc': True,
    'confirm_close_multiple_tabs': True,
    'notify_on_file_complete': True,
    'file_transfers_port': 28011,
    'ft_add_hosts_to_send': '',
    'use_kib_mib': False,
    'notify_on_all_muc_messages': False,
    'trayicon_notification_on_events': True,
    'last_save_dir': '',
    'last_send_dir': '',
    'last_sounds_dir': '',
    'notification_preview_message': True,
    'notification_position_x': -1,
    'notification_position_y': -1,
    'muc_highlight_words': '',
    'muc_prefer_direct_msg': True,
    'show_status_msgs_in_roster': True,
    'show_avatars_in_roster': True,
    'show_mood_in_roster': True,
    'show_activity_in_roster': True,
    'show_tunes_in_roster': True,
    'show_location_in_roster': True,
    'avatar_position_in_roster': 'right',
    'print_status_in_chats': False,
    'log_contact_status_changes': False,
    'use_urgency_hint': True,
    'notification_timeout': 5,
    'escape_key_closes': False,
    'hide_groupchat_banner': False,
    'hide_chat_banner': False,
    'hide_groupchat_occupants_list': False,
    'chat_merge_consecutive_nickname': False,
    'ctrl_tab_go_to_next_composing': True,
    'metacontacts_enabled': True,
    'confirm_metacontacts': '',
    'confirm_block': '',
    'enable_negative_priority': False,
    'show_contacts_number': True,
    'max_conversation_lines': 500,
    'shell_like_completion': False,
    'audio_input_device': 'autoaudiosrc ! volume name=gajim_vol',
    'audio_output_device': 'autoaudiosink',
    'video_input_device': 'autovideosrc',
    'video_framerate': '',
    'video_size': '',
    'video_see_self': True,
    'audio_input_volume': 50,
    'audio_output_volume': 50,
    'use_stun_server': False,
    'stun_server': '',
    'global_proxy': '',
    'ignore_incoming_attention': False,
    'remember_opened_chat_controls': True,
    'positive_184_ack': False,
    'use_keyring': True,
    'remote_commands': False,
    'dark_theme': 2,
    'gc_sync_threshold_public_default': 1,
    'gc_sync_threshold_private_default': 0,
    'show_subject_on_join': True,
    'show_chatstate_in_tabs': True,
    'show_chatstate_in_banner': True,
    'muclumbus_api_jid': 'api@search.jabber.network',
    'muclumbus_api_http_uri': 'https://search.jabber.network/api/1.0/search',
    'muclumbus_api_pref': 'http',
    'command_system_execute': False,
    'groupchat_roster_width': 210,
    'dev_force_bookmark_2': False,
    'developer_modus': False,
    'show_help_start_chat': True,
    'gc_notify_on_all_messages_private_default': True,
    'gc_notify_on_all_messages_public_default': False,
    'gc_print_status_default': False,
    'gc_print_join_left_default': False,
    'check_for_update': True,
    'last_update_check': '',
    'always_ask_for_status_message': False,
    'show_send_message_button': False,
    'workspace_order': [],
    'chat_handle_position': 350,
    'chat_timestamp_format': '%H:%M',
    'preview_size': 300,
    'preview_max_file_size': 10485760,
    'preview_allow_all_images': False,
    'preview_leftclick_action': 'open',
    'preview_verify_https': True,
    'preview_anonymous_muc': False,
}

ACCOUNT_SETTINGS = {
    'account': {
        'name': '',
        'account_label': '',
        'account_color': 'rgb(85, 85, 85)',
        'hostname': '',
        'anonymous_auth': False,
        'avatar_sha': '',
        'client_cert': '',
        'client_cert_encrypted': False,
        'savepass': False,
        'password': '',
        'resource': 'gajim.$rand',
        'priority': 0,
        'adjust_priority_with_status': False,
        'autopriority_online': 50,
        'autopriority_chat': 50,
        'autopriority_away': 40,
        'autopriority_xa': 30,
        'autopriority_dnd': 20,
        'autoconnect': False,
        'restore_last_status': False,
        'autoauth': False,
        'active': True,
        'proxy': '',
        'keyid': '',
        'keyname': '',
        'use_plain_connection': False,
        'confirm_unencrypted_connection': True,
        'use_custom_host': False,
        'custom_port': 5222,
        'custom_host': '',
        'custom_type': 'START TLS',
        'sync_with_global_status': False,
        'no_log_for': '',
        'attached_gpg_keys': '',
        'http_auth': 'ask',
        'file_transfer_proxies': '',
        'use_ft_proxies': False,
        'test_ft_proxies_on_startup': False,
        'is_zeroconf': False,
        'last_status': 'online',
        'last_status_msg': '',
        'zeroconf_first_name': '',
        'zeroconf_last_name': '',
        'zeroconf_jabber_id': '',
        'zeroconf_email': '',
        'answer_receipts': True,
        'publish_tune': False,
        'publish_location': False,
        'request_user_data': True,
        'ignore_unknown_contacts': False,
        'send_os_info': True,
        'send_time_info': True,
        'send_idle_time': True,
        'roster_version': '',
        'subscription_request_msg': '',
        'ft_send_local_ips': True,
        'opened_chat_controls': '',
        'recent_groupchats': '',
        'filetransfer_preference': 'httpupload',
        'send_chatstate_default': 'composing_only',
        'gc_send_chatstate_default': 'composing_only',
        'send_marker_default': True,
        'gc_send_marker_private_default': True,
        'gc_send_marker_public_default': False,
        'chat_history_max_age': -1,
        'enable_gssapi': False,
    },

    'contact': {
        'speller_language': '',
        'send_chatstate': HAS_ACCOUNT_DEFAULT,
        'send_marker': HAS_ACCOUNT_DEFAULT,
        'encryption': '',
    },

    'group_chat': {
        'speller_language': '',
        'notify_on_all_messages': HAS_APP_DEFAULT,
        'print_status': HAS_APP_DEFAULT,
        'print_join_left': HAS_APP_DEFAULT,
        'send_chatstate': HAS_ACCOUNT_DEFAULT,
        'send_marker': HAS_ACCOUNT_DEFAULT,
        'encryption': '',
        'sync_threshold': HAS_APP_DEFAULT,
    },
}


WORKSPACE_SETTINGS = {
    'name': _('My Workspace'),
    'color': '',
    'avatar_sha': '',
    'open_chats': [],
}


INITAL_WORKSPACE = {str(uuid.uuid4()): {}}


PLUGIN_SETTINGS = {
    'active': False
}


STATUS_PRESET_SETTINGS = {
    'message': '',
    'activity': '',
    'subactivity': '',
    'mood': '',
}


STATUS_PRESET_EXAMPLES = {
    _('Sleeping'): {
        'message': _('ZZZZzzzzzZZZZZ'),
        'activity': 'inactive',
        'subactivity': 'sleeping',
        'mood': 'sleepy'
    },
    _('Back soon'): {
        'message': _('Back in some minutes.')
    },
    _('Eating'): {
        'message': _('I’m eating.'),
        'activity': 'eating',
        'subactivity': 'other'
    },
    _('Movie'): {
        'message': _('I’m watching a movie.'),
        'activity': 'relaxing',
        'subactivity': 'watching_a_movie'
    },
    _('Working'): {
        'message': _('I’m working.'),
        'activity': 'working',
        'subactivity': 'other'
    },
    _('Out'): {
        'message': _('I’m out enjoying life.'),
        'activity': 'relaxing',
        'subactivity': 'going_out'
    }
}


PROXY_SETTINGS = {
    'type': 'socks5',
    'host': '',
    'port': 0,
    'useauth': False,
    'user': '',
    'pass': '',
}


PROXY_EXAMPLES = {
    'Tor': {
        'type': 'socks5',
        'host': 'localhost',
        'port': 9050
    },
}


DEFAULT_SOUNDEVENT_SETTINGS = {
    'attention_received': {
        'enabled': True,
        'path': 'attention.wav'
    },
    'first_message_received': {
        'enabled': True,
        'path': 'message1.wav'
    },
    'contact_connected': {
        'enabled': False,
        'path': 'connected.wav'
    },
    'contact_disconnected': {
        'enabled': False,
        'path': 'disconnected.wav'
    },
    'message_sent': {
        'enabled': False,
        'path': 'sent.wav'
    },
    'muc_message_highlight': {
        'enabled': True,
        'path': 'gc_message1.wav'
    },
    'muc_message_received': {
        'enabled': True,
        'path': 'message2.wav'
    }
}


ADVANCED_SETTINGS = {
    'app': {
        'allow_hide_roster': _('Allow to hide the contact list window even if the notification area icon is not shown.'),
        'ascii_formatting': _('Treat * / _ pairs as possible formatting characters.'),
        'show_ascii_formatting_chars': _('If enabled, do not remove */_ . So *abc* will be bold but with * * not removed.'),
        'gc_refer_to_nick_char': _('Character to add after nickname when using nickname completion (tab) in group chat.'),
        'save_main_window_position': _('If enabled, Gajim will save the main window position when hiding it, and restore it when showing the window again.'),
        'roster_on_the_right': _('Place the contact list on the right in single window mode'),
        'time_stamp': _('This option lets you customize the timestamp that is printed in conversation. For example \'[%H:%M] \' will show \'[hour:minute] \'. See python doc on strftime for full documentation (https://docs.python.org/3/library/time.html#time.strftime).'),
        'chat_timestamp_format': 'https://docs.python.org/3/library/time.html#time.strftime',
        'change_roster_title': _('If enabled, Gajim will add * and [n] in contact list window title.'),
        'restore_timeout': _('How far back in time (minutes) chat history is restored. -1 means no limit.'),
        'send_on_ctrl_enter': _('Send message on Ctrl+Enter and make a new line with Enter.'),
        'key_up_lines': _('How many lines to store for Ctrl+KeyUP (previously sent messages).'),
        'search_engine': '',
        'dictionary_url': _('Either a custom URL with %%s in it (where %%s is the word/phrase) or \'WIKTIONARY\' (which means use Wikitionary).'),
        'always_english_wikipedia': '',
        'always_english_wiktionary': '',
        'remote_control': _('If checked, Gajim can be controlled remotely using gajim-remote.'),
        'confirm_paste_image': _('Ask before pasting an image.'),
        'confirm_close_muc': _('Ask before closing a group chat tab/window.'),
        'confirm_close_multiple_tabs': _('Ask before closing tabbed chat window if there are chats that can lose data (chat, private chat, group chat that will not be minimized).'),
        'file_transfers_port': '',
        'ft_add_hosts_to_send': _('List of send hosts (comma separated) in addition to local interfaces for file transfers (in case of address translation/port forwarding).'),
        'use_kib_mib': _('IEC standard says KiB = 1024 bytes, KB = 1000 bytes.'),
        'notify_on_all_muc_messages': '',
        'trayicon_notification_on_events': _('Notify of events in the notification area.'),
        'notification_preview_message': _('Preview new messages in notification popup?'),
        'muc_highlight_words': _('A list of words (semicolon separated) that will be highlighted in group chats.'),
        'hide_on_main_window_x_button': _('If enabled, Gajim hides the main window when pressing the X button instead of minimizing into the notification area.'),
        'main_window_skip_taskbar': _('Don’t show main window in the system taskbar.'),
        'show_mood_in_roster': '',
        'show_activity_in_roster': '',
        'show_tunes_in_roster': '',
        'show_location_in_roster': '',
        'avatar_position_in_roster': _('Define the position of avatars in the contact list. Can be \'left\' or \'right\'.'),
        'use_urgency_hint': _('If enabled, Gajim makes the window flash (the default behaviour in most Window Managers) when holding pending events.'),
        'notification_timeout': '',
        'escape_key_closes': _('If enabled, pressing Esc closes a tab/window.'),
        'hide_groupchat_banner': _('Hides the banner in a group chat window.'),
        'hide_chat_banner': _('Hides the banner in a 1:1 chat window.'),
        'hide_groupchat_occupants_list': _('Hides the group chat participants list in a group chat window.'),
        'chat_merge_consecutive_nickname': _('In a chat, show the nickname at the beginning of a line only when it\'s not the same person talking as in the previous message.'),
        'ctrl_tab_go_to_next_composing': _('Ctrl+Tab switches to the next composing tab when there are no tabs with messages pending.'),
        'confirm_metacontacts': _('Show a confirmation dialog to create metacontacts? Empty string means never show the dialog.'),
        'confirm_block': _('Show a confirmation dialog to block a contact? Empty string means never show the dialog.'),
        'enable_negative_priority': _('If enabled, you will be able to set a negative priority to your account in the Accounts window. BE CAREFUL, when you are logged in with a negative priority, you will NOT receive any message from your server.'),
        'show_contacts_number': _('If enabled, Gajim will show both the number of online and total contacts in account rows as well as in group rows.'),
        'max_conversation_lines': _('Maximum number of lines that are printed in conversations. Oldest lines are cleared.'),
        'shell_like_completion': _('If enabled, completion in group chats will be like a shell auto-completion.'),
        'use_stun_server': _('If enabled, Gajim will try to use a STUN server when using Jingle. The one in \'stun_server\' option, or the one given by the XMPP server.'),
        'stun_server': _('STUN server to use when using Jingle'),
        'ignore_incoming_attention': _('If enabled, Gajim will ignore incoming attention requests (\'wizz\').'),
        'remember_opened_chat_controls': _('If enabled, Gajim will reopen chat windows that were opened last time Gajim was closed.'),
        'remote_commands': _('If enabled, Gajim will execute XEP-0146 Commands.'),
        'muclumbus_api_jid': '',
        'muclumbus_api_http_uri': '',
        'muclumbus_api_pref': _('API Preferences. Possible values: \'http\', \'iq\''),
        'command_system_execute': _('If enabled, Gajim will execute commands (/show, /sh, /execute, /exec).'),
        'groupchat_roster_width': _('Width of group chat roster in pixel'),
        'dev_force_bookmark_2': _('Force Bookmark 2 usage'),
        'gc_notify_on_all_messages_private_default': '',
        'gc_notify_on_all_messages_public_default': '',
        'metacontacts_enabled': '',
        'developer_modus': '',
    },
}

# pylint: enable=line-too-long
