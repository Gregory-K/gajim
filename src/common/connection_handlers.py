# -*- coding:utf-8 -*-
## src/common/connection_handlers.py
##
## Copyright (C) 2006 Dimitur Kirov <dkirov AT gmail.com>
##                    Junglecow J <junglecow AT gmail.com>
## Copyright (C) 2006-2007 Tomasz Melcer <liori AT exroot.org>
##                         Travis Shirk <travis AT pobox.com>
##                         Nikos Kouremenos <kourem AT gmail.com>
## Copyright (C) 2006-2010 Yann Leboulanger <asterix AT lagaule.org>
## Copyright (C) 2007 Julien Pivotto <roidelapluie AT gmail.com>
## Copyright (C) 2007-2008 Brendan Taylor <whateley AT gmail.com>
##                         Jean-Marie Traissard <jim AT lapin.org>
##                         Stephan Erb <steve-e AT h3c.de>
## Copyright (C) 2008 Jonathan Schleifer <js-gajim AT webkeks.org>
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim. If not, see <http://www.gnu.org/licenses/>.
##

import os
import base64
import sys
import operator
import hashlib
import hmac

from time import (altzone, daylight, gmtime, localtime, mktime, strftime,
        time as time_time, timezone, tzname)
from calendar import timegm

import common.xmpp
import common.caps_cache as capscache

from common import helpers
from common import gajim
from common import exceptions
from common import dataforms
from common.commands import ConnectionCommands
from common.pubsub import ConnectionPubSub
from common.pep import ConnectionPEP
from common.protocol.caps import ConnectionCaps
from common.protocol.bytestream import ConnectionSocks5Bytestream
from common.protocol.bytestream import ConnectionIBBytestream
from common.message_archiving import ConnectionArchive
from common.message_archiving import ARCHIVING_COLLECTIONS_ARRIVED
from common.message_archiving import ARCHIVING_COLLECTION_ARRIVED
from common.message_archiving import ARCHIVING_MODIFICATIONS_ARRIVED
from common.connection_handlers_events import *

from common import ged
from common import nec
from common.nec import NetworkEvent

if gajim.HAVE_FARSIGHT:
    from common.jingle import ConnectionJingle
else:
    class ConnectionJingle():
        def __init__(self):
            pass
        def _JingleCB(self, con, stanza):
            pass

from common import dbus_support
if dbus_support.supported:
    import dbus
    from music_track_listener import MusicTrackListener

import logging
log = logging.getLogger('gajim.c.connection_handlers')

# kind of events we can wait for an answer
VCARD_PUBLISHED = 'vcard_published'
VCARD_ARRIVED = 'vcard_arrived'
AGENT_REMOVED = 'agent_removed'
METACONTACTS_ARRIVED = 'metacontacts_arrived'
ROSTER_ARRIVED = 'roster_arrived'
PRIVACY_ARRIVED = 'privacy_arrived'
PEP_CONFIG = 'pep_config'
HAS_IDLE = True
try:
#       import idle
    import common.sleepy
except Exception:
    log.debug(_('Unable to load idle module'))
    HAS_IDLE = False


class ConnectionDisco:
    """
    Holds xmpppy handlers and public methods for discover services
    """

    def discoverItems(self, jid, node = None, id_prefix = None):
        """
        According to XEP-0030:
                jid is mandatory;
                name, node, action is optional.
        """
        self._discover(common.xmpp.NS_DISCO_ITEMS, jid, node, id_prefix)

    def discoverInfo(self, jid, node = None, id_prefix = None):
        """
        According to XEP-0030:
                For identity: category, type is mandatory, name is optional.
                For feature: var is mandatory.
        """
        self._discover(common.xmpp.NS_DISCO_INFO, jid, node, id_prefix)

    def request_register_agent_info(self, agent):
        if not self.connection or self.connected < 2:
            return None
        iq = common.xmpp.Iq('get', common.xmpp.NS_REGISTER, to=agent)
        id_ = self.connection.getAnID()
        iq.setID(id_)
        # Wait the answer during 30 secondes
        self.awaiting_timeouts[gajim.idlequeue.current_time() + 30] = (id_,
                _('Registration information for transport %s has not arrived in time')\
                % agent)
        self.connection.SendAndCallForResponse(iq, self._ReceivedRegInfo,
                {'agent': agent})

    def _agent_registered_cb(self, con, resp, agent):
        if resp.getType() == 'result':
            self.dispatch('INFORMATION', (_('Registration succeeded'),
                    _('Registration with agent %s succeeded') % agent))
            self.request_subscription(agent, auto_auth=True)
            self.agent_registrations[agent]['roster_push'] = True
            if self.agent_registrations[agent]['sub_received']:
                p = common.xmpp.Presence(agent, 'subscribed')
                p = self.add_sha(p)
                self.connection.send(p)
        if resp.getType() == 'error':
            self.dispatch('ERROR', (_('Registration failed'), _('Registration with'
                    ' agent %(agent)s failed with error %(error)s: %(error_msg)s') % {
                    'agent': agent, 'error': resp.getError(),
                    'error_msg': resp.getErrorMsg()}))

    def register_agent(self, agent, info, is_form = False):
        if not self.connection or self.connected < 2:
            return
        if is_form:
            iq = common.xmpp.Iq('set', common.xmpp.NS_REGISTER, to=agent)
            query = iq.getTag('query')
            info.setAttr('type', 'submit')
            query.addChild(node=info)
            self.connection.SendAndCallForResponse(iq, self._agent_registered_cb,
                    {'agent': agent})
        else:
            # fixed: blocking
            common.xmpp.features_nb.register(self.connection, agent, info,
                    self._agent_registered_cb, {'agent': agent})
        self.agent_registrations[agent] = {'roster_push': False,
                'sub_received': False}

    def _discover(self, ns, jid, node=None, id_prefix=None):
        if not self.connection or self.connected < 2:
            return
        iq = common.xmpp.Iq(typ='get', to=jid, queryNS=ns)
        if id_prefix:
            id_ = self.connection.getAnID()
            iq.setID('%s%s' % (id_prefix, id_))
        if node:
            iq.setQuerynode(node)
        self.connection.send(iq)

    def _ReceivedRegInfo(self, con, resp, agent):
        common.xmpp.features_nb._ReceivedRegInfo(con, resp, agent)
        self._IqCB(con, resp)

    def _discoGetCB(self, con, iq_obj):
        """
        Get disco info
        """
        if not self.connection or self.connected < 2:
            return
        frm = helpers.get_full_jid_from_iq(iq_obj)
        to = unicode(iq_obj.getAttr('to'))
        id_ = unicode(iq_obj.getAttr('id'))
        iq = common.xmpp.Iq(to=frm, typ='result', queryNS=common.xmpp.NS_DISCO,
                frm=to)
        iq.setAttr('id', id_)
        query = iq.setTag('query')
        query.setAttr('node', 'http://gajim.org#' + gajim.version.split('-', 1)[0])
        for f in (common.xmpp.NS_BYTESTREAM, common.xmpp.NS_SI,
        common.xmpp.NS_FILE, common.xmpp.NS_COMMANDS):
            feature = common.xmpp.Node('feature')
            feature.setAttr('var', f)
            query.addChild(node=feature)

        self.connection.send(iq)
        raise common.xmpp.NodeProcessed

    def _DiscoverItemsErrorCB(self, con, iq_obj):
        log.debug('DiscoverItemsErrorCB')
        jid = helpers.get_full_jid_from_iq(iq_obj)
        self.dispatch('AGENT_ERROR_ITEMS', (jid))

    def _DiscoverItemsCB(self, con, iq_obj):
        log.debug('DiscoverItemsCB')
        q = iq_obj.getTag('query')
        node = q.getAttr('node')
        if not node:
            node = ''
        qp = iq_obj.getQueryPayload()
        items = []
        if not qp:
            qp = []
        for i in qp:
            # CDATA payload is not processed, only nodes
            if not isinstance(i, common.xmpp.simplexml.Node):
                continue
            attr = {}
            for key in i.getAttrs():
                attr[key] = i.getAttrs()[key]
            if 'jid' not in attr:
                continue
            try:
                attr['jid'] = helpers.parse_jid(attr['jid'])
            except common.helpers.InvalidFormat:
                # jid is not conform
                continue
            items.append(attr)
        jid = helpers.get_full_jid_from_iq(iq_obj)
        hostname = gajim.config.get_per('accounts', self.name, 'hostname')
        id_ = iq_obj.getID()
        if jid == hostname and id_[:6] == 'Gajim_':
            for item in items:
                self.discoverInfo(item['jid'], id_prefix='Gajim_')
        else:
            self.dispatch('AGENT_INFO_ITEMS', (jid, node, items))

    def _DiscoverItemsGetCB(self, con, iq_obj):
        log.debug('DiscoverItemsGetCB')

        if not self.connection or self.connected < 2:
            return

        if self.commandItemsQuery(con, iq_obj):
            raise common.xmpp.NodeProcessed
        node = iq_obj.getTagAttr('query', 'node')
        if node is None:
            result = iq_obj.buildReply('result')
            self.connection.send(result)
            raise common.xmpp.NodeProcessed
        if node==common.xmpp.NS_COMMANDS:
            self.commandListQuery(con, iq_obj)
            raise common.xmpp.NodeProcessed

    def _DiscoverInfoGetCB(self, con, iq_obj):
        log.debug('DiscoverInfoGetCB')
        if not self.connection or self.connected < 2:
            return
        q = iq_obj.getTag('query')
        node = q.getAttr('node')

        if self.commandInfoQuery(con, iq_obj):
            raise common.xmpp.NodeProcessed

        id_ = unicode(iq_obj.getAttr('id'))
        if id_[:6] == 'Gajim_':
            # We get this request from echo.server
            raise common.xmpp.NodeProcessed

        iq = iq_obj.buildReply('result')
        q = iq.getTag('query')
        if node:
            q.setAttr('node', node)
        q.addChild('identity', attrs = gajim.gajim_identity)
        client_version = 'http://gajim.org#' + gajim.caps_hash[self.name]

        if node in (None, client_version):
            for f in gajim.gajim_common_features:
                q.addChild('feature', attrs = {'var': f})
            for f in gajim.gajim_optional_features[self.name]:
                q.addChild('feature', attrs = {'var': f})

        if q.getChildren():
            self.connection.send(iq)
            raise common.xmpp.NodeProcessed

    def _DiscoverInfoErrorCB(self, con, iq_obj):
        log.debug('DiscoverInfoErrorCB')
        jid = helpers.get_full_jid_from_iq(iq_obj)
        id_ = iq_obj.getID()
        if id_[:6] == 'Gajim_':
            if not self.privacy_rules_requested:
                self.privacy_rules_requested = True
                self._request_privacy()
        self.dispatch('AGENT_ERROR_INFO', (jid))

    def _DiscoverInfoCB(self, con, iq_obj):
        log.debug('DiscoverInfoCB')
        if not self.connection or self.connected < 2:
            return
        # According to XEP-0030:
        # For identity: category, type is mandatory, name is optional.
        # For feature: var is mandatory
        identities, features, data = [], [], []
        q = iq_obj.getTag('query')
        node = q.getAttr('node')
        if not node:
            node = ''
        qc = iq_obj.getQueryChildren()
        if not qc:
            qc = []
        is_muc = False
        transport_type = ''
        for i in qc:
            if i.getName() == 'identity':
                attr = {}
                for key in i.getAttrs().keys():
                    attr[key] = i.getAttr(key)
                if 'category' in attr and \
                        attr['category'] in ('gateway', 'headline') and \
                        'type' in attr:
                    transport_type = attr['type']
                if 'category' in attr and \
                        attr['category'] == 'conference' and \
                        'type' in attr and attr['type'] == 'text':
                    is_muc = True
                identities.append(attr)
            elif i.getName() == 'feature':
                var = i.getAttr('var')
                if var:
                    features.append(var)
            elif i.getName() == 'x' and i.getNamespace() == common.xmpp.NS_DATA:
                data.append(common.xmpp.DataForm(node=i))
        jid = helpers.get_full_jid_from_iq(iq_obj)
        if transport_type and jid not in gajim.transport_type:
            gajim.transport_type[jid] = transport_type
            gajim.logger.save_transport_type(jid, transport_type)
        id_ = iq_obj.getID()
        if id_ is None:
            log.warn('Invalid IQ received without an ID. Ignoring it: %s' % iq_obj)
            return
        if not identities: # ejabberd doesn't send identities when we browse online users
        #FIXME: see http://www.jabber.ru/bugzilla/show_bug.cgi?id=225
            identities = [{'category': 'server', 'type': 'im', 'name': node}]
        if id_[:6] == 'Gajim_':
            if jid == gajim.config.get_per('accounts', self.name, 'hostname'):
                if features.__contains__(common.xmpp.NS_GMAILNOTIFY):
                    gajim.gmail_domains.append(jid)
                    self.request_gmail_notifications()
                if features.__contains__(common.xmpp.NS_SECLABEL):
                    self.seclabel_supported = True
                for identity in identities:
                    if identity['category'] == 'pubsub' and identity.get('type') == \
                    'pep':
                        self.pep_supported = True
                        break
                if features.__contains__(common.xmpp.NS_VCARD):
                    self.vcard_supported = True
                if features.__contains__(common.xmpp.NS_PUBSUB):
                    self.pubsub_supported = True
                    if features.__contains__(
                    common.xmpp.NS_PUBSUB_PUBLISH_OPTIONS):
                        self.pubsub_publish_options_supported = True
                    else:
                        # Remove stored bookmarks accessible to everyone.
                        our_jid = gajim.get_jid_from_account(self.name)
                        self.send_pb_purge(our_jid, 'storage:bookmarks')
                        self.send_pb_delete(our_jid, 'storage:bookmarks')
                if features.__contains__(common.xmpp.NS_ARCHIVE):
                    self.archiving_supported = True
                if features.__contains__(common.xmpp.NS_ARCHIVE_AUTO):
                    self.archive_auto_supported = True
                if features.__contains__(common.xmpp.NS_ARCHIVE_MANAGE):
                    self.archive_manage_supported = True
                if features.__contains__(common.xmpp.NS_ARCHIVE_MANUAL):
                    self.archive_manual_supported = True
                if features.__contains__(common.xmpp.NS_ARCHIVE_PREF):
                    self.archive_pref_supported = True
            if features.__contains__(common.xmpp.NS_BYTESTREAM):
                our_jid = helpers.parse_jid(gajim.get_jid_from_account(
                    self.name) + '/' + self.server_resource)
                gajim.proxy65_manager.resolve(jid, self.connection, our_jid,
                    self.name)
            if features.__contains__(common.xmpp.NS_MUC) and is_muc:
                type_ = transport_type or 'jabber'
                self.muc_jid[type_] = jid
            if transport_type:
                if transport_type in self.available_transports:
                    self.available_transports[transport_type].append(jid)
                else:
                    self.available_transports[transport_type] = [jid]
            if not self.privacy_rules_requested:
                self.privacy_rules_requested = True
                self._request_privacy()

        self.dispatch('AGENT_INFO_INFO', (jid, node, identities,
                features, data))
        self._capsDiscoCB(jid, node, identities, features, data)

class ConnectionVcard:
    def __init__(self):
        self.vcard_sha = None
        self.vcard_shas = {} # sha of contacts
        self.room_jids = [] # list of gc jids so that vcard are saved in a folder

    def add_sha(self, p, send_caps = True):
        c = p.setTag('x', namespace = common.xmpp.NS_VCARD_UPDATE)
        if self.vcard_sha is not None:
            c.setTagData('photo', self.vcard_sha)
        if send_caps:
            return self._add_caps(p)
        return p

    def _add_caps(self, p):
        ''' advertise our capabilities in presence stanza (xep-0115)'''
        c = p.setTag('c', namespace = common.xmpp.NS_CAPS)
        c.setAttr('hash', 'sha-1')
        c.setAttr('node', 'http://gajim.org')
        c.setAttr('ver', gajim.caps_hash[self.name])
        return p

    def _node_to_dict(self, node):
        dict_ = {}
        for info in node.getChildren():
            name = info.getName()
            if name in ('ADR', 'TEL', 'EMAIL'): # we can have several
                dict_.setdefault(name, [])
                entry = {}
                for c in info.getChildren():
                    entry[c.getName()] = c.getData()
                dict_[name].append(entry)
            elif info.getChildren() == []:
                dict_[name] = info.getData()
            else:
                dict_[name] = {}
                for c in info.getChildren():
                    dict_[name][c.getName()] = c.getData()
        return dict_

    def _save_vcard_to_hd(self, full_jid, card):
        jid, nick = gajim.get_room_and_nick_from_fjid(full_jid)
        puny_jid = helpers.sanitize_filename(jid)
        path = os.path.join(gajim.VCARD_PATH, puny_jid)
        if jid in self.room_jids or os.path.isdir(path):
            if not nick:
                return
            # remove room_jid file if needed
            if os.path.isfile(path):
                os.remove(path)
            # create folder if needed
            if not os.path.isdir(path):
                os.mkdir(path, 0700)
            puny_nick = helpers.sanitize_filename(nick)
            path_to_file = os.path.join(gajim.VCARD_PATH, puny_jid, puny_nick)
        else:
            path_to_file = path
        try:
            fil = open(path_to_file, 'w')
            fil.write(str(card))
            fil.close()
        except IOError, e:
            self.dispatch('ERROR', (_('Disk Write Error'), str(e)))

    def get_cached_vcard(self, fjid, is_fake_jid=False):
        """
        Return the vcard as a dict.
        Return {} if vcard was too old.
        Return None if we don't have cached vcard.
        """
        jid, nick = gajim.get_room_and_nick_from_fjid(fjid)
        puny_jid = helpers.sanitize_filename(jid)
        if is_fake_jid:
            puny_nick = helpers.sanitize_filename(nick)
            path_to_file = os.path.join(gajim.VCARD_PATH, puny_jid, puny_nick)
        else:
            path_to_file = os.path.join(gajim.VCARD_PATH, puny_jid)
        if not os.path.isfile(path_to_file):
            return None
        # We have the vcard cached
        f = open(path_to_file)
        c = f.read()
        f.close()
        try:
            card = common.xmpp.Node(node=c)
        except Exception:
            # We are unable to parse it. Remove it
            os.remove(path_to_file)
            return None
        vcard = self._node_to_dict(card)
        if 'PHOTO' in vcard:
            if not isinstance(vcard['PHOTO'], dict):
                del vcard['PHOTO']
            elif 'SHA' in vcard['PHOTO']:
                cached_sha = vcard['PHOTO']['SHA']
                if jid in self.vcard_shas and self.vcard_shas[jid] != \
                cached_sha:
                    # user change his vcard so don't use the cached one
                    return {}
        vcard['jid'] = jid
        vcard['resource'] = gajim.get_resource_from_jid(fjid)
        return vcard

    def request_vcard(self, jid=None, groupchat_jid=None):
        """
        Request the VCARD

        If groupchat_jid is not null, it means we request a vcard to a fake jid,
        like in private messages in groupchat. jid can be the real jid of the
        contact, but we want to consider it comes from a fake jid
        """
        if not self.connection or self.connected < 2:
            return
        iq = common.xmpp.Iq(typ = 'get')
        if jid:
            iq.setTo(jid)
        iq.setTag(common.xmpp.NS_VCARD + ' vCard')

        id_ = self.connection.getAnID()
        iq.setID(id_)
        j = jid
        if not j:
            j = gajim.get_jid_from_account(self.name)
        self.awaiting_answers[id_] = (VCARD_ARRIVED, j, groupchat_jid)
        if groupchat_jid:
            room_jid = gajim.get_room_and_nick_from_fjid(groupchat_jid)[0]
            if not room_jid in self.room_jids:
                self.room_jids.append(room_jid)
            self.groupchat_jids[id_] = groupchat_jid
        self.connection.send(iq)

    def send_vcard(self, vcard):
        if not self.connection or self.connected < 2:
            return
        iq = common.xmpp.Iq(typ = 'set')
        iq2 = iq.setTag(common.xmpp.NS_VCARD + ' vCard')
        for i in vcard:
            if i == 'jid':
                continue
            if isinstance(vcard[i], dict):
                iq3 = iq2.addChild(i)
                for j in vcard[i]:
                    iq3.addChild(j).setData(vcard[i][j])
            elif isinstance(vcard[i], list):
                for j in vcard[i]:
                    iq3 = iq2.addChild(i)
                    for k in j:
                        iq3.addChild(k).setData(j[k])
            else:
                iq2.addChild(i).setData(vcard[i])

        id_ = self.connection.getAnID()
        iq.setID(id_)
        self.connection.send(iq)

        our_jid = gajim.get_jid_from_account(self.name)
        # Add the sha of the avatar
        if 'PHOTO' in vcard and isinstance(vcard['PHOTO'], dict) and \
        'BINVAL' in vcard['PHOTO']:
            photo = vcard['PHOTO']['BINVAL']
            photo_decoded = base64.decodestring(photo)
            gajim.interface.save_avatar_files(our_jid, photo_decoded)
            avatar_sha = hashlib.sha1(photo_decoded).hexdigest()
            iq2.getTag('PHOTO').setTagData('SHA', avatar_sha)
        else:
            gajim.interface.remove_avatar_files(our_jid)

        self.awaiting_answers[id_] = (VCARD_PUBLISHED, iq2)

    def _IqCB(self, con, iq_obj):
        id_ = iq_obj.getID()

        gajim.nec.push_incoming_event(NetworkEvent('raw-iq-received',
            conn=con, xmpp_iq=iq_obj))

        # Check if we were waiting a timeout for this id
        found_tim = None
        for tim in self.awaiting_timeouts:
            if id_ == self.awaiting_timeouts[tim][0]:
                found_tim = tim
                break
        if found_tim:
            del self.awaiting_timeouts[found_tim]

        if id_ not in self.awaiting_answers:
            return
        if self.awaiting_answers[id_][0] == VCARD_PUBLISHED:
            if iq_obj.getType() == 'result':
                vcard_iq = self.awaiting_answers[id_][1]
                # Save vcard to HD
                if vcard_iq.getTag('PHOTO') and vcard_iq.getTag('PHOTO').getTag('SHA'):
                    new_sha = vcard_iq.getTag('PHOTO').getTagData('SHA')
                else:
                    new_sha = ''

                # Save it to file
                our_jid = gajim.get_jid_from_account(self.name)
                self._save_vcard_to_hd(our_jid, vcard_iq)

                # Send new presence if sha changed and we are not invisible
                if self.vcard_sha != new_sha and gajim.SHOW_LIST[self.connected] !=\
                'invisible':
                    if not self.connection or self.connected < 2:
                        return
                    self.vcard_sha = new_sha
                    sshow = helpers.get_xmpp_show(gajim.SHOW_LIST[self.connected])
                    p = common.xmpp.Presence(typ = None, priority = self.priority,
                            show = sshow, status = self.status)
                    p = self.add_sha(p)
                    self.connection.send(p)
                self.dispatch('VCARD_PUBLISHED', ())
            elif iq_obj.getType() == 'error':
                self.dispatch('VCARD_NOT_PUBLISHED', ())
        elif self.awaiting_answers[id_][0] == VCARD_ARRIVED:
            # If vcard is empty, we send to the interface an empty vcard so that
            # it knows it arrived
            jid = self.awaiting_answers[id_][1]
            groupchat_jid = self.awaiting_answers[id_][2]
            frm = jid
            if groupchat_jid:
                # We do as if it comes from the fake_jid
                frm = groupchat_jid
            our_jid = gajim.get_jid_from_account(self.name)
            if not iq_obj.getTag('vCard') or iq_obj.getType() == 'error':
                if frm and frm != our_jid:
                    # Write an empty file
                    self._save_vcard_to_hd(frm, '')
                    jid, resource = gajim.get_room_and_nick_from_fjid(frm)
                    self.dispatch('VCARD', {'jid': jid, 'resource': resource})
                elif frm == our_jid:
                    self.dispatch('MYVCARD', {'jid': frm})
        elif self.awaiting_answers[id_][0] == AGENT_REMOVED:
            jid = self.awaiting_answers[id_][1]
            self.dispatch('AGENT_REMOVED', jid)
        elif self.awaiting_answers[id_][0] == METACONTACTS_ARRIVED:
            if not self.connection:
                return
            if iq_obj.getType() == 'result':
                # Metacontact tags
                # http://www.xmpp.org/extensions/xep-0209.html
                meta_list = {}
                query = iq_obj.getTag('query')
                storage = query.getTag('storage')
                metas = storage.getTags('meta')
                for meta in metas:
                    try:
                        jid = helpers.parse_jid(meta.getAttr('jid'))
                    except common.helpers.InvalidFormat:
                        continue
                    tag = meta.getAttr('tag')
                    data = {'jid': jid}
                    order = meta.getAttr('order')
                    try:
                        order = int(order)
                    except Exception:
                        order = 0
                    if order is not None:
                        data['order'] = order
                    if tag in meta_list:
                        meta_list[tag].append(data)
                    else:
                        meta_list[tag] = [data]
                self.dispatch('METACONTACTS', meta_list)
            else:
                if iq_obj.getErrorCode() not in ('403', '406', '404'):
                    self.private_storage_supported = False

            # We can now continue connection by requesting the roster
            version = None
            if con.Stream.features and con.Stream.features.getTag('ver',
            namespace=common.xmpp.NS_ROSTER_VER):
                version = gajim.config.get_per('accounts', self.name,
                    'roster_version')
                if version and not gajim.contacts.get_contacts_jid_list(
                self.name):
                    gajim.config.set_per('accounts', self.name,
                        'roster_version', '')
                    version = None

            iq_id = self.connection.initRoster(version=version)
            self.awaiting_answers[iq_id] = (ROSTER_ARRIVED, )
        elif self.awaiting_answers[id_][0] == ROSTER_ARRIVED:
            if iq_obj.getType() == 'result':
                if not iq_obj.getTag('query'):
                    account_jid = gajim.get_jid_from_account(self.name)
                    roster_data = gajim.logger.get_roster(account_jid)
                    roster = self.connection.getRoster(force=True)
                    roster.setRaw(roster_data)
                self._getRoster()
        elif self.awaiting_answers[id_][0] == PRIVACY_ARRIVED:
            if iq_obj.getType() != 'error':
                self.privacy_rules_supported = True
                self.get_privacy_list('block')
            elif self.continue_connect_info:
                if self.continue_connect_info[0] == 'invisible':
                    # Trying to login as invisible but privacy list not supported
                    self.disconnect(on_purpose=True)
                    self.dispatch('STATUS', 'offline')
                    self.dispatch('ERROR', (_('Invisibility not supported'),
                            _('Account %s doesn\'t support invisibility.') % self.name))
                    return
            # Ask metacontacts before roster
            self.get_metacontacts()
        elif self.awaiting_answers[id_][0] == PEP_CONFIG:
            if iq_obj.getType() == 'error':
                return
            if not iq_obj.getTag('pubsub'):
                return
            conf = iq_obj.getTag('pubsub').getTag('configure')
            if not conf:
                return
            node = conf.getAttr('node')
            form_tag = conf.getTag('x', namespace=common.xmpp.NS_DATA)
            if form_tag:
                form = common.dataforms.ExtendForm(node=form_tag)
                self.dispatch('PEP_CONFIG', (node, form))

        elif self.awaiting_answers[id_][0] == ARCHIVING_COLLECTIONS_ARRIVED:
            # TODO
            print 'ARCHIVING_COLLECTIONS_ARRIVED'
            pass

        elif self.awaiting_answers[id_][0] == ARCHIVING_COLLECTION_ARRIVED:
            def save_if_not_exists(with_, nick, direction, tim, payload):
                assert len(payload) == 1, 'got several archiving messages in' +\
                    ' the same time %s' % ''.join(payload)
                if payload[0].getName() == 'body':
                    gajim.logger.save_if_not_exists(with_, direction, tim,
                        msg=payload[0].getData(), nick=nick)
                elif payload[0].getName() == 'message':
                    print 'Not implemented'
            chat = iq_obj.getTag('chat')
            if chat:
                with_ = chat.getAttr('with')
                start_ = chat.getAttr('start')
                tim = helpers.datetime_tuple(start_)
                tim = timegm(tim)
                nb = 0
                for element in chat.getChildren():
                    try:
                        secs = int(element.getAttr('secs'))
                    except TypeError:
                        secs = 0
                    if secs:
                        tim += secs
                    nick = element.getAttr('name')
                    if element.getName() == 'from':
                        save_if_not_exists(with_, nick, 'from', localtime(tim),
                            element.getPayload())
                        nb += 1
                    if element.getName() == 'to':
                        save_if_not_exists(with_, nick, 'to', localtime(tim),
                            element.getPayload())
                        nb += 1
                set_ = chat.getTag('set')
                first = set_.getTag('first')
                if first:
                    try:
                        index = int(first.getAttr('index'))
                    except TypeError:
                        index = 0
                try:
                    count = int(set_.getTagData('count'))
                except TypeError:
                    count = 0
                if count > index + nb:
                    # Request the next page
                    after = element.getTagData('last')
                    self.request_collection_page(with_, start_, after=after)

        elif self.awaiting_answers[id_][0] == ARCHIVING_MODIFICATIONS_ARRIVED:
            modified = iq_obj.getTag('modified')
            if modified:
                for element in modified.getChildren():
                    if element.getName() == 'changed':
                        with_ = element.getAttr('with')
                        start_ = element.getAttr('start')
                        self.request_collection_page(with_, start_)
                    elif element.getName() == 'removed':
                        # do nothing
                        pass

        del self.awaiting_answers[id_]

    def _vCardCB(self, con, vc):
        """
        Called when we receive a vCard Parse the vCard and send it to plugins
        """
        if not vc.getTag('vCard'):
            return
        if not vc.getTag('vCard').getNamespace() == common.xmpp.NS_VCARD:
            return
        id_ = vc.getID()
        frm_iq = vc.getFrom()
        our_jid = gajim.get_jid_from_account(self.name)
        resource = ''
        if id_ in self.groupchat_jids:
            who = self.groupchat_jids[id_]
            frm, resource = gajim.get_room_and_nick_from_fjid(who)
            del self.groupchat_jids[id_]
        elif frm_iq:
            who = helpers.get_full_jid_from_iq(vc)
            frm, resource = gajim.get_room_and_nick_from_fjid(who)
        else:
            who = frm = our_jid
        card = vc.getChildren()[0]
        vcard = self._node_to_dict(card)
        photo_decoded = None
        if 'PHOTO' in vcard and isinstance(vcard['PHOTO'], dict) and \
        'BINVAL' in vcard['PHOTO']:
            photo = vcard['PHOTO']['BINVAL']
            try:
                photo_decoded = base64.decodestring(photo)
                avatar_sha = hashlib.sha1(photo_decoded).hexdigest()
            except Exception:
                avatar_sha = ''
        else:
            avatar_sha = ''

        if avatar_sha:
            card.getTag('PHOTO').setTagData('SHA', avatar_sha)

        # Save it to file
        self._save_vcard_to_hd(who, card)
        # Save the decoded avatar to a separate file too, and generate files for dbus notifications
        puny_jid = helpers.sanitize_filename(frm)
        puny_nick = None
        begin_path = os.path.join(gajim.AVATAR_PATH, puny_jid)
        frm_jid = frm
        if frm in self.room_jids:
            puny_nick = helpers.sanitize_filename(resource)
            # create folder if needed
            if not os.path.isdir(begin_path):
                os.mkdir(begin_path, 0700)
            begin_path = os.path.join(begin_path, puny_nick)
            frm_jid += '/' + resource
        if photo_decoded:
            avatar_file = begin_path + '_notif_size_colored.png'
            if frm_jid == our_jid and avatar_sha != self.vcard_sha:
                gajim.interface.save_avatar_files(frm, photo_decoded, puny_nick)
            elif frm_jid != our_jid and (not os.path.exists(avatar_file) or \
            frm_jid not in self.vcard_shas or \
            avatar_sha != self.vcard_shas[frm_jid]):
                gajim.interface.save_avatar_files(frm, photo_decoded, puny_nick)
                if avatar_sha:
                    self.vcard_shas[frm_jid] = avatar_sha
            elif frm in self.vcard_shas:
                del self.vcard_shas[frm]
        else:
            for ext in ('.jpeg', '.png', '_notif_size_bw.png',
                    '_notif_size_colored.png'):
                path = begin_path + ext
                if os.path.isfile(path):
                    os.remove(path)

        vcard['jid'] = frm
        vcard['resource'] = resource
        if frm_jid == our_jid:
            self.dispatch('MYVCARD', vcard)
            # we re-send our presence with sha if has changed and if we are
            # not invisible
            if self.vcard_sha == avatar_sha:
                return
            self.vcard_sha = avatar_sha
            if gajim.SHOW_LIST[self.connected] == 'invisible':
                return
            if not self.connection:
                return
            sshow = helpers.get_xmpp_show(gajim.SHOW_LIST[self.connected])
            p = common.xmpp.Presence(typ = None, priority = self.priority,
                    show = sshow, status = self.status)
            p = self.add_sha(p)
            self.connection.send(p)
        else:
            #('VCARD', {entry1: data, entry2: {entry21: data, ...}, ...})
            self.dispatch('VCARD', vcard)

# basic connection handlers used here and in zeroconf
class ConnectionHandlersBase:
    def __init__(self):
        # List of IDs we are waiting answers for {id: (type_of_request, data), }
        self.awaiting_answers = {}
        # List of IDs that will produce a timeout is answer doesn't arrive
        # {time_of_the_timeout: (id, message to send to gui), }
        self.awaiting_timeouts = {}
        # keep the jids we auto added (transports contacts) to not send the
        # SUBSCRIBED event to gui
        self.automatically_added = []
        # IDs of jabber:iq:last requests
        self.last_ids = []

        # keep track of sessions this connection has with other JIDs
        self.sessions = {}

        gajim.ged.register_event_handler('error-received', ged.CORE,
            self._nec_error_received)

    def _nec_error_received(self, obj):
        if obj.conn.name != self.name:
            return
        if obj.id_ in self.last_ids:
            gajim.nec.push_incoming_event(LastResultReceivedEvent(None,
                conn=self, iq_obj=obj.iq_obj))
            return True

    def _LastResultCB(self, con, iq_obj):
        log.debug('LastResultCB')
        gajim.nec.push_incoming_event(LastResultReceivedEvent(None, conn=self,
            iq_obj=iq_obj))

    def get_sessions(self, jid):
        """
        Get all sessions for the given full jid
        """
        if not gajim.interface.is_pm_contact(jid, self.name):
            jid = gajim.get_jid_without_resource(jid)

        try:
            return self.sessions[jid].values()
        except KeyError:
            return []

    def get_or_create_session(self, fjid, thread_id):
        """
        Return an existing session between this connection and 'jid', returns a
        new one if none exist
        """
        pm = True
        jid = fjid

        if not gajim.interface.is_pm_contact(fjid, self.name):
            pm = False
            jid = gajim.get_jid_without_resource(fjid)

        session = self.find_session(jid, thread_id)

        if session:
            return session

        if pm:
            return self.make_new_session(fjid, thread_id, type_='pm')
        else:
            return self.make_new_session(fjid, thread_id)

    def find_session(self, jid, thread_id):
        try:
            if not thread_id:
                return self.find_null_session(jid)
            else:
                return self.sessions[jid][thread_id]
        except KeyError:
            return None

    def terminate_sessions(self, send_termination=False):
        """
        Send termination messages and delete all active sessions
        """
        for jid in self.sessions:
            for thread_id in self.sessions[jid]:
                self.sessions[jid][thread_id].terminate(send_termination)

        self.sessions = {}

    def delete_session(self, jid, thread_id):
        if not jid in self.sessions:
            jid = gajim.get_jid_without_resource(jid)
        if not jid in self.sessions:
            return

        del self.sessions[jid][thread_id]

        if not self.sessions[jid]:
            del self.sessions[jid]

    def find_null_session(self, jid):
        """
        Find all of the sessions between us and a remote jid in which we haven't
        received a thread_id yet and returns the session that we last sent a
        message to
        """
        sessions = self.sessions[jid].values()

        # sessions that we haven't received a thread ID in
        idless = [s for s in sessions if not s.received_thread_id]

        # filter out everything except the default session type
        chat_sessions = [s for s in idless if isinstance(s,
                gajim.default_session_type)]

        if chat_sessions:
            # return the session that we last sent a message in
            return sorted(chat_sessions, key=operator.attrgetter("last_send"))[-1]
        else:
            return None

    def find_controlless_session(self, jid, resource=None):
        """
        Find an active session that doesn't have a control attached
        """
        try:
            sessions = self.sessions[jid].values()

            # filter out everything except the default session type
            chat_sessions = [s for s in sessions if isinstance(s,
                    gajim.default_session_type)]

            orphaned = [s for s in chat_sessions if not s.control]

            if resource:
                orphaned = [s for s in orphaned if s.resource == resource]

            return orphaned[0]
        except (KeyError, IndexError):
            return None

    def make_new_session(self, jid, thread_id=None, type_='chat', cls=None):
        """
        Create and register a new session

        thread_id=None to generate one.
        type_ should be 'chat' or 'pm'.
        """
        if not cls:
            cls = gajim.default_session_type

        sess = cls(self, common.xmpp.JID(jid), thread_id, type_)

        # determine if this session is a pm session
        # if not, discard the resource so that all sessions are stored bare
        if not type_ == 'pm':
            jid = gajim.get_jid_without_resource(jid)

        if not jid in self.sessions:
            self.sessions[jid] = {}

        self.sessions[jid][sess.thread_id] = sess

        return sess

class ConnectionHandlers(ConnectionArchive, ConnectionVcard,
ConnectionSocks5Bytestream, ConnectionDisco, ConnectionCommands,
ConnectionPubSub, ConnectionPEP, ConnectionCaps, ConnectionHandlersBase,
ConnectionJingle, ConnectionIBBytestream):
    def __init__(self):
        global HAS_IDLE
        ConnectionArchive.__init__(self)
        ConnectionVcard.__init__(self)
        ConnectionSocks5Bytestream.__init__(self)
        ConnectionIBBytestream.__init__(self)
        ConnectionCommands.__init__(self)
        ConnectionPubSub.__init__(self)
        ConnectionPEP.__init__(self, account=self.name, dispatcher=self,
                pubsub_connection=self)
        ConnectionCaps.__init__(self, account=self.name,
                dispatch_event=self.dispatch, capscache=capscache.capscache,
                client_caps_factory=capscache.create_suitable_client_caps)
        ConnectionJingle.__init__(self)
        ConnectionHandlersBase.__init__(self)
        self.gmail_url = None

        # keep the latest subscribed event for each jid to prevent loop when we
        # acknowledge presences
        self.subscribed_events = {}
        # IDs of jabber:iq:version requests
        self.version_ids = []
        # IDs of urn:xmpp:time requests
        self.entity_time_ids = []
        # ID of urn:xmpp:ping requests
        self.awaiting_xmpp_ping_id = None
        self.continue_connect_info = None

        try:
            self.sleeper = common.sleepy.Sleepy()
#                       idle.init()
            HAS_IDLE = True
        except Exception:
            HAS_IDLE = False

        self.gmail_last_tid = None
        self.gmail_last_time = None

        gajim.nec.register_incoming_event(PrivateStorageBookmarksReceivedEvent)
        gajim.nec.register_incoming_event(BookmarksReceivedEvent)
        gajim.nec.register_incoming_event(
            PrivateStorageRosternotesReceivedEvent)
        gajim.nec.register_incoming_event(RosternotesReceivedEvent)
        gajim.nec.register_incoming_event(StreamConflictReceivedEvent)
        gajim.nec.register_incoming_event(PresenceReceivedEvent)

        gajim.ged.register_event_handler('http-auth-received', ged.CORE,
            self._nec_http_auth_received)
        gajim.ged.register_event_handler('version-request-received', ged.CORE,
            self._nec_version_request_received)
        gajim.ged.register_event_handler('last-request-received', ged.CORE,
            self._nec_last_request_received)
        gajim.ged.register_event_handler('time-request-received', ged.CORE,
            self._nec_time_request_received)
        gajim.ged.register_event_handler('time-revised-request-received',
            ged.CORE, self._nec_time_revised_request_received)
        gajim.ged.register_event_handler('roster-set-received',
            ged.CORE, self._nec_roster_set_received)
        gajim.ged.register_event_handler('private-storage-bookmarks-received',
            ged.CORE, self._nec_private_storate_bookmarks_received)
        gajim.ged.register_event_handler('private-storage-rosternotes-received',
            ged.CORE, self._nec_private_storate_rosternotes_received)
        gajim.ged.register_event_handler('roster-received', ged.CORE,
            self._nec_roster_received)
        gajim.ged.register_event_handler('error-received', ged.CORE,
            self._nec_error_received)
        gajim.ged.register_event_handler('gmail-new-mail-received', ged.CORE,
            self._nec_gmail_new_mail_received)
        gajim.ged.register_event_handler('ping-received', ged.CORE,
            self._nec_ping_received)
        gajim.ged.register_event_handler('presence-received', ged.CORE,
            self._nec_presence_received)

    def build_http_auth_answer(self, iq_obj, answer):
        if not self.connection or self.connected < 2:
            return
        if answer == 'yes':
            confirm = iq_obj.getTag('confirm')
            reply = iq_obj.buildReply('result')
            if iq_obj.getName() == 'message':
                reply.addChild(node=confirm)
            self.connection.send(reply)
        elif answer == 'no':
            err = common.xmpp.Error(iq_obj,
                common.xmpp.protocol.ERR_NOT_AUTHORIZED)
            self.connection.send(err)

    def _nec_http_auth_received(self, obj):
        if obj.conn.name != self.name:
            return
        if obj.opt in ('yes', 'no'):
            obj.conn.build_http_auth_answer(obj.iq_obj, obj.opt)
            return True

    def _HttpAuthCB(self, con, iq_obj):
        log.debug('HttpAuthCB')
        gajim.nec.push_incoming_event(HttpAuthReceivedEvent(None, conn=self,
            iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _ErrorCB(self, con, iq_obj):
        log.debug('ErrorCB')
        gajim.nec.push_incoming_event(ErrorReceivedEvent(None, conn=self,
            iq_obj=iq_obj))

    def _nec_error_received(self, obj):
        if obj.conn.name != self.name:
            return
        if obj.id_ in self.version_ids:
            gajim.nec.push_incoming_event(VersionResultReceivedEvent(None,
                conn=self, iq_obj=obj.iq_obj))
            return True
        if obj.id_ in self.entity_time_ids:
            gajim.nec.push_incoming_event(TimeResultReceivedEvent(None,
                conn=self, iq_obj=obj.iq_obj))
            return True

    def _nec_private_storate_bookmarks_received(self, obj):
        if obj.conn.name != self.name:
            return
        resend_to_pubsub = False
        bm_jids = [b['jid'] for b in self.bookmarks]
        for bm in obj.bookmarks:
            if bm['jid'] not in bm_jids:
                self.bookmarks.append(bm)
                # We got a bookmark that was not in pubsub
                resend_to_pubsub = True
        if self.pubsub_supported and resend_to_pubsub:
            self.store_bookmarks('pubsub')

    def _nec_private_storate_rosternotes_received(self, obj):
        if obj.conn.name != self.name:
            return
        for jid in obj.annotations:
            self.annotations[jid] = obj.annotations[jid]

    def _PrivateCB(self, con, iq_obj):
        """
        Private Data (XEP 048 and 049)
        """
        log.debug('PrivateCB')
        gajim.nec.push_incoming_event(PrivateStorageReceivedEvent(None,
            conn=self, iq_obj=iq_obj))

    def _SecLabelCB(self, con, iq_obj):
        """
        Security Label callback, used for catalogues.
        """
        log.debug('SecLabelCB')
        query = iq_obj.getTag('catalog')
        to = query.getAttr('to')
        items = query.getTags('securitylabel')
        labels = {}
        ll = []
        for item in items:
            label = item.getTag('displaymarking').getData()
            labels[label] = item
            ll.append(label)
        if to not in self.seclabel_catalogues:
            self.seclabel_catalogues[to] = [[], None, None]
        self.seclabel_catalogues[to][1] = labels
        self.seclabel_catalogues[to][2] = ll
        for callback in self.seclabel_catalogues[to][0]:
            callback()
        self.seclabel_catalogues[to][0] = []

    def seclabel_catalogue_request(self, to, callback):
        if to not in self.seclabel_catalogues:
            self.seclabel_catalogues[to] = [[], None, None]
        self.seclabel_catalogues[to][0].append(callback)

    def _rosterSetCB(self, con, iq_obj):
        log.debug('rosterSetCB')
        gajim.nec.push_incoming_event(RosterSetReceivedEvent(None, conn=self,
            iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _nec_roster_set_received(self, obj):
        if obj.conn.name != self.name:
            return
        for jid in obj.items:
            item = obj.items[jid]
            gajim.nec.push_incoming_event(RosterInfoEvent(None, conn=self,
                jid=jid, nickname=item['name'], sub=item['sub'], ask=item['ask'],
                groups=item['groups']))
            account_jid = gajim.get_jid_from_account(self.name)
            gajim.logger.add_or_update_contact(account_jid, jid, item['name'],
                item['sub'], item['ask'], item['groups'])
        if obj.version:
            gajim.config.set_per('accounts', self.name, 'roster_version',
                obj.version)

    def _VersionCB(self, con, iq_obj):
        log.debug('VersionCB')
        if not self.connection or self.connected < 2:
            return
        gajim.nec.push_incoming_event(VersionRequestEvent(None,
            conn=self, iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _nec_version_request_received(self, obj):
        if obj.conn.name != self.name:
            return
        iq_obj = obj.iq_obj.buildReply('result')
        qp = iq_obj.getTag('query')
        qp.setTagData('name', 'Gajim')
        qp.setTagData('version', gajim.version)
        send_os = gajim.config.get_per('accounts', self.name, 'send_os_info')
        if send_os:
            qp.setTagData('os', helpers.get_os_info())
        self.connection.send(iq_obj)

    def _LastCB(self, con, iq_obj):
        log.debug('LastCB')
        if not self.connection or self.connected < 2:
            return
        gajim.nec.push_incoming_event(LastRequestEvent(None,
            conn=self, iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _nec_last_request_received(self, obj):
        global HAS_IDLE
        if obj.conn.name != self.name:
            return
        if HAS_IDLE and gajim.config.get_per('accounts', self.name,
        'send_idle_time'):
            iq_obj = obj.iq_obj.buildReply('result')
            qp = iq_obj.getTag('query')
            qp.attrs['seconds'] = int(self.sleeper.getIdleSec())
        else:
            iq_obj = obj.iq_obj.buildReply('error')
            err = common.xmpp.ErrorNode(name=common.xmpp.NS_STANZAS + \
                ' service-unavailable')
            iq_obj.addChild(node=err)
        self.connection.send(iq_obj)

    def _VersionResultCB(self, con, iq_obj):
        log.debug('VersionResultCB')
        gajim.nec.push_incoming_event(VersionResultReceivedEvent(None,
            conn=self, iq_obj=iq_obj))

    def _TimeCB(self, con, iq_obj):
        log.debug('TimeCB')
        if not self.connection or self.connected < 2:
            return
        gajim.nec.push_incoming_event(TimeRequestEvent(None,
            conn=self, iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _nec_time_request_received(self, obj):
        if obj.conn.name != self.name:
            return
        iq_obj = obj.iq_obj.buildReply('result')
        qp = iq_obj.getTag('query')
        qp.setTagData('utc', strftime('%Y%m%dT%H:%M:%S', gmtime()))
        qp.setTagData('tz', helpers.decode_string(tzname[daylight]))
        qp.setTagData('display', helpers.decode_string(strftime('%c',
            localtime())))
        self.connection.send(iq_obj)

    def _TimeRevisedCB(self, con, iq_obj):
        log.debug('TimeRevisedCB')
        if not self.connection or self.connected < 2:
            return
        gajim.nec.push_incoming_event(TimeRevisedRequestEvent(None,
            conn=self, iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _nec_time_revised_request_received(self, obj):
        if obj.conn.name != self.name:
            return
        iq_obj = obj.iq_obj.buildReply('result')
        qp = iq_obj.setTag('time', namespace=common.xmpp.NS_TIME_REVISED)
        qp.setTagData('utc', strftime('%Y-%m-%dT%H:%M:%SZ', gmtime()))
        isdst = localtime().tm_isdst
        zone = -(timezone, altzone)[isdst] / 60
        tzo = (zone / 60, abs(zone % 60))
        qp.setTagData('tzo', '%+03d:%02d' % (tzo))
        self.connection.send(iq_obj)

    def _TimeRevisedResultCB(self, con, iq_obj):
        log.debug('TimeRevisedResultCB')
        gajim.nec.push_incoming_event(TimeResultReceivedEvent(None,
            conn=self, iq_obj=iq_obj))

    def _gMailNewMailCB(self, con, iq_obj):
        """
        Called when we get notified of new mail messages in gmail account
        """
        log.debug('gMailNewMailCB')
        gajim.nec.push_incoming_event(GmailNewMailReceivedEvent(None,
            conn=self, iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _nec_gmail_new_mail_received(self, obj):
        if obj.conn.name != self.name:
            return
        if not self.connection or self.connected < 2:
            return
        # we'll now ask the server for the exact number of new messages
        jid = gajim.get_jid_from_account(self.name)
        log.debug('Got notification of new gmail e-mail on %s. Asking the '
            'server for more info.' % jid)
        iq = common.xmpp.Iq(typ='get')
        query = iq.setTag('query')
        query.setNamespace(common.xmpp.NS_GMAILNOTIFY)
        # we want only be notified about newer mails
        if self.gmail_last_tid:
            query.setAttr('newer-than-tid', self.gmail_last_tid)
        if self.gmail_last_time:
            query.setAttr('newer-than-time', self.gmail_last_time)
        self.connection.send(iq)

    def _gMailQueryCB(self, con, iq_obj):
        """
        Called when we receive results from Querying the server for mail messages
        in gmail account
        """
        log.debug('gMailQueryCB')
        gajim.nec.push_incoming_event(GMailQueryReceivedEvent(None,
            conn=self, iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _rosterItemExchangeCB(self, con, msg):
        """
        XEP-0144 Roster Item Echange
        """
        log.debug('rosterItemExchangeCB')
        gajim.nec.push_incoming_event(RosterItemExchangeEvent(None,
            conn=self, iq_obj=msg))
        raise common.xmpp.NodeProcessed

    def _messageCB(self, con, msg):
        """
        Called when we receive a message
        """
        log.debug('MessageCB')

        gajim.nec.push_incoming_event(NetworkEvent('raw-message-received',
            conn=con, xmpp_msg=msg, account=self.name))

        mtype = msg.getType()

        # check if the message is a roster item exchange (XEP-0144)
        if msg.getTag('x', namespace=common.xmpp.NS_ROSTERX):
            self._rosterItemExchangeCB(con, msg)
            return

        # check if the message is a XEP-0070 confirmation request
        if msg.getTag('confirm', namespace=common.xmpp.NS_HTTP_AUTH):
            self._HttpAuthCB(con, msg)
            return

        try:
            frm = helpers.get_full_jid_from_iq(msg)
            jid = helpers.get_jid_from_iq(msg)
        except helpers.InvalidFormat:
            self.dispatch('ERROR', (_('Invalid Jabber ID'),
                    _('A message from a non-valid JID arrived, it has been ignored.')))
            return

        addressTag = msg.getTag('addresses', namespace = common.xmpp.NS_ADDRESS)

        # Be sure it comes from one of our resource, else ignore address element
        if addressTag and jid == gajim.get_jid_from_account(self.name):
            address = addressTag.getTag('address', attrs={'type': 'ofrom'})
            if address:
                try:
                    frm = helpers.parse_jid(address.getAttr('jid'))
                except common.helpers.InvalidFormat:
                    log.warn('Invalid JID: %s, ignoring it' % address.getAttr('jid'))
                    return
                jid = gajim.get_jid_without_resource(frm)

        # invitations
        invite = None
        encTag = msg.getTag('x', namespace=common.xmpp.NS_ENCRYPTED)

        if not encTag:
            invite = msg.getTag('x', namespace = common.xmpp.NS_MUC_USER)
            if invite and not invite.getTag('invite'):
                invite = None

        # FIXME: Msn transport (CMSN1.2.1 and PyMSN0.10) do NOT RECOMMENDED
        # invitation
        # stanza (MUC XEP) remove in 2007, as we do not do NOT RECOMMENDED
        xtags = msg.getTags('x')
        for xtag in xtags:
            if xtag.getNamespace() == common.xmpp.NS_CONFERENCE and not invite:
                try:
                    room_jid = helpers.parse_jid(xtag.getAttr('jid'))
                except common.helpers.InvalidFormat:
                    log.warn('Invalid JID: %s, ignoring it' % xtag.getAttr('jid'))
                    continue
                is_continued = False
                if xtag.getTag('continue'):
                    is_continued = True
                self.dispatch('GC_INVITATION', (room_jid, frm, '', None,
                        is_continued))
                return

        thread_id = msg.getThread()

        if not mtype or mtype not in ('chat', 'groupchat', 'error'):
            mtype = 'normal'

        msgtxt = msg.getBody()

        encrypted = False
        xep_200_encrypted = msg.getTag('c', namespace=common.xmpp.NS_STANZA_CRYPTO)

        session = None
        gc_control = gajim.interface.msg_win_mgr.get_gc_control(jid, self.name)
        if not gc_control and \
        jid in gajim.interface.minimized_controls[self.name]:
            gc_control = gajim.interface.minimized_controls[self.name][jid]

        if gc_control and jid == frm: # message from a gc without a resource
            mtype = 'groupchat'

        if mtype != 'groupchat':
            session = self.get_or_create_session(frm, thread_id)

            if thread_id and not session.received_thread_id:
                session.received_thread_id = True

            session.last_receive = time_time()

        # check if the message is a XEP-0020 feature negotiation request
        if msg.getTag('feature', namespace=common.xmpp.NS_FEATURE):
            if gajim.HAVE_PYCRYPTO:
                feature = msg.getTag(name='feature', namespace=common.xmpp.NS_FEATURE)
                form = common.xmpp.DataForm(node=feature.getTag('x'))

                if form['FORM_TYPE'] == 'urn:xmpp:ssn':
                    session.handle_negotiation(form)
                else:
                    reply = msg.buildReply()
                    reply.setType('error')

                    reply.addChild(feature)
                    err = common.xmpp.ErrorNode('service-unavailable', typ='cancel')
                    reply.addChild(node=err)

                    con.send(reply)

                raise common.xmpp.NodeProcessed

            return

        if msg.getTag('init', namespace=common.xmpp.NS_ESESSION_INIT):
            init = msg.getTag(name='init', namespace=common.xmpp.NS_ESESSION_INIT)
            form = common.xmpp.DataForm(node=init.getTag('x'))

            session.handle_negotiation(form)

            raise common.xmpp.NodeProcessed

        tim = msg.getTimestamp()
        tim = helpers.datetime_tuple(tim)
        tim = localtime(timegm(tim))

        if xep_200_encrypted:
            encrypted = 'xep200'

            try:
                msg = session.decrypt_stanza(msg)
                msgtxt = msg.getBody()
            except Exception:
                self.dispatch('FAILED_DECRYPT', (frm, tim, session))

        # Receipt requested
        # TODO: We shouldn't answer if we're invisible!
        contact = gajim.contacts.get_contact(self.name, jid)
        nick = gajim.get_room_and_nick_from_fjid(frm)[1]
        gc_contact = gajim.contacts.get_gc_contact(self.name, jid, nick)
        if msg.getTag('request', namespace=common.xmpp.NS_RECEIPTS) \
        and gajim.config.get_per('accounts', self.name,
        'answer_receipts') and ((contact and contact.sub \
        not in (u'to', u'none')) or gc_contact) and mtype != 'error':
            receipt = common.xmpp.Message(to=frm, typ='chat')
            receipt.setID(msg.getID())
            receipt.setTag('received', namespace='urn:xmpp:receipts',
                attrs={'id': msg.getID()})

            if thread_id:
                receipt.setThread(thread_id)
            con.send(receipt)

        # We got our message's receipt
        if msg.getTag('received', namespace=common.xmpp.NS_RECEIPTS) and \
        session.control and gajim.config.get_per('accounts', self.name,
        'request_receipt'):
            session.control.conv_textview.hide_xep0184_warning(msg.getID())

        if encTag and self.USE_GPG:
            encmsg = encTag.getData()

            keyID = gajim.config.get_per('accounts', self.name, 'keyid')
            if keyID:
                def decrypt_thread(encmsg, keyID):
                    decmsg = self.gpg.decrypt(encmsg, keyID)
                    # \x00 chars are not allowed in C (so in GTK)
                    msgtxt = helpers.decode_string(decmsg.replace('\x00', ''))
                    encrypted = 'xep27'
                    return (msgtxt, encrypted)
                gajim.thread_interface(decrypt_thread, [encmsg, keyID],
                        self._on_message_decrypted, [mtype, msg, session, frm, jid,
                        invite, tim])
                return
        self._on_message_decrypted((msgtxt, encrypted), mtype, msg, session, frm,
                jid, invite, tim)

    def _on_message_decrypted(self, output, mtype, msg, session, frm, jid,
    invite, tim):
        msgtxt, encrypted = output
        if mtype == 'error':
            self.dispatch_error_message(msg, msgtxt, session, frm, tim)
        elif mtype == 'groupchat':
            self.dispatch_gc_message(msg, frm, msgtxt, jid, tim)
        elif invite is not None:
            self.dispatch_invite_message(invite, frm)
        else:
            if isinstance(session, gajim.default_session_type):
                session.received(frm, msgtxt, tim, encrypted, msg)
            else:
                session.received(msg)
    # END messageCB

    # process and dispatch an error message
    def dispatch_error_message(self, msg, msgtxt, session, frm, tim):
        error_msg = msg.getErrorMsg()

        if not error_msg:
            error_msg = msgtxt
            msgtxt = None

        subject = msg.getSubject()

        if session.is_loggable():
            try:
                gajim.logger.write('error', frm, error_msg, tim=tim,
                        subject=subject)
            except exceptions.PysqliteOperationalError, e:
                self.dispatch('DB_ERROR', (_('Disk Write Error'), str(e)))
            except exceptions.DatabaseMalformed:
                pritext = _('Database Error')
                sectext = _('The database file (%s) cannot be read. Try to repair '
                        'it (see http://trac.gajim.org/wiki/DatabaseBackup) or remove '
                        'it (all history will be lost).') % common.logger.LOG_DB_PATH
                self.dispatch('DB_ERROR', (pritext, sectext))
        self.dispatch('MSGERROR', (frm, msg.getErrorCode(), error_msg, msgtxt,
                tim, session))

    def _on_bob_received(self, conn, result, cid):
        """
        Called when we receive BoB data
        """
        if cid not in self.awaiting_cids:
            return

        if result.getType() == 'result':
            data = msg.getTags('data', namespace=common.xmpp.NS_BOB)
            if data.getAttr('cid') == cid:
                for func in self.awaiting_cids[cid]:
                    cb = func[0]
                    args = func[1]
                    pos = func[2]
                    bob_data = data.getData()
                    def recurs(node, cid, data):
                        if node.getData() == 'cid:' + cid:
                            node.setData(data)
                        else:
                            for child in node.getChildren():
                                recurs(child, cid, data)
                    recurs(args[pos], cid, bob_data)
                    cb(*args)
                del self.awaiting_cids[cid]
                return

        # An error occured, call callback without modifying data.
        for func in self.awaiting_cids[cid]:
            cb = func[0]
            args = func[1]
            cb(*args)
        del self.awaiting_cids[cid]

    def get_bob_data(self, cid, to, callback, args, position):
        """
        Request for BoB (XEP-0231) and when data will arrive, call callback
        with given args, after having replaced cid by it's data in
        args[position]
        """
        if cid in self.awaiting_cids:
            self.awaiting_cids[cid].appends((callback, args, position))
        else:
            self.awaiting_cids[cid] = [(callback, args, position)]
        iq = common.xmpp.Iq(to=to, typ='get')
        data = iq.addChild(name='data', attrs={'cid': cid},
            namespace=common.xmpp.NS_BOB)
        self.connection.SendAndCallForResponse(iq, self._on_bob_received,
            {'cid': cid})

    # process and dispatch a groupchat message
    def dispatch_gc_message(self, msg, frm, msgtxt, jid, tim):
        has_timestamp = bool(msg.timestamp)

        subject = msg.getSubject()

        if subject is not None:
            self.dispatch('GC_SUBJECT', (frm, subject, msgtxt, has_timestamp))
            return

        statusCode = msg.getStatusCode()

        if not msg.getTag('body'): # no <body>
            # It could be a config change. See
            # http://www.xmpp.org/extensions/xep-0045.html#roomconfig-notify
            if msg.getTag('x'):
                if statusCode != []:
                    self.dispatch('GC_CONFIG_CHANGE', (jid, statusCode))
            return

        displaymarking = None
        seclabel = msg.getTag('securitylabel')
        if seclabel and seclabel.getNamespace() == common.xmpp.NS_SECLABEL:
            displaymarking = seclabel.getTag('displaymarking')        # Ignore message from room in which we are not
        if jid not in self.last_history_time:
            return

        captcha = msg.getTag('captcha', namespace=common.xmpp.NS_CAPTCHA)
        if captcha:
            captcha = captcha.getTag('x', namespace=common.xmpp.NS_DATA)
            for field in captcha.getTags('field'):
                for media in field.getTags('media'):
                    for uri in media.getTags('uri'):
                        uri_data = uri.getData()
                        if uri_data.startswith('cid:'):
                            uri_data = uri_data[4:]
                            found = False
                            for data in msg.getTags('data',
                            namespace=common.xmpp.NS_BOB):
                                if data.getAttr('cid') == uri_data:
                                    uri.setData(data.getData())
                                    found = True
                            if not found:
                                self.get_bob_data(uri_data, frm,
                                    self.dispatch_gc_message, [msg, frm, msgtxt,
                                    jid, tim], 0)
                                return
        self.dispatch('GC_MSG', (frm, msgtxt, tim, has_timestamp,
            msg.getXHTML(), statusCode, displaymarking, captcha))

        tim_int = int(float(mktime(tim)))
        if gajim.config.should_log(self.name, jid) and not \
        tim_int <= self.last_history_time[jid] and msgtxt and frm.find('/') >= 0:
            # if frm.find('/') < 0, it means message comes from room itself
            # usually it hold description and can be send at each connection
            # so don't store it in logs
            try:
                gajim.logger.write('gc_msg', frm, msgtxt, tim=tim)
                # store in memory time of last message logged.
                # this will also be saved in rooms_last_message_time table
                # when we quit this muc
                self.last_history_time[jid] = mktime(tim)

            except exceptions.PysqliteOperationalError, e:
                self.dispatch('DB_ERROR', (_('Disk Write Error'), str(e)))
            except exceptions.DatabaseMalformed:
                pritext = _('Database Error')
                sectext = _('The database file (%s) cannot be read. Try to repair '
                        'it (see http://trac.gajim.org/wiki/DatabaseBackup) or remove '
                        'it (all history will be lost).') % common.logger.LOG_DB_PATH
                self.dispatch('DB_ERROR', (pritext, sectext))

    def dispatch_invite_message(self, invite, frm):
        item = invite.getTag('invite')
        try:
            jid_from = helpers.parse_jid(item.getAttr('from'))
        except common.helpers.InvalidFormat:
            log.warn('Invalid JID: %s, ignoring it' % item.getAttr('from'))
            return
        reason = item.getTagData('reason')
        item = invite.getTag('password')
        password = invite.getTagData('password')

        is_continued = False
        if invite.getTag('invite').getTag('continue'):
            is_continued = True
        self.dispatch('GC_INVITATION', (frm, jid_from, reason, password,
                is_continued))

    def _presenceCB(self, con, prs):
        """
        Called when we receive a presence
        """
        log.debug('PresenceCB')
        gajim.nec.push_incoming_event(NetworkEvent('raw-pres-received',
            conn=self, iq_obj=prs))

    def _nec_presence_received(self, obj):
        account = obj.conn.name
        jid = obj.jid
        resource = obj.resource or ''

        statuss = ['offline', 'error', 'online', 'chat', 'away', 'xa', 'dnd',
            'invisible']
        obj.old_show = 0
        obj.new_show = statuss.index(obj.show)

        obj.contact_list = []

        highest = gajim.contacts.get_contact_with_highest_priority(account, jid)
        obj.was_highest = (highest and highest.resource == resource)

        # Update contact
        obj.contact_list = gajim.contacts.get_contacts(account, jid)
        obj.contact = None
        resources = []
        for c in obj.contact_list:
            resources.append(c.resource)
            if c.resource == resource:
                obj.contact = c
                break

        if obj.contact:
            obj.old_show = statuss.index(obj.contact.show)
            # nick changed
            if obj.contact_nickname is not None and \
            obj.contact.contact_name != obj.contact_nickname:
                obj.contact.contact_name = obj.contact_nickname
                obj.need_redraw = True

            if obj.old_show == obj.new_show and obj.contact.status == \
            obj.status and obj.contact.priority == obj.prio: # no change
                return
        else:
            obj.contact = gajim.contacts.get_first_contact_from_jid(account,
                jid)
            if not obj.contact:
                # Presence of another resource of our jid
                # Create self contact and add to roster
                if resource == obj.conn.server_resource:
                    return
                # Ignore offline presence of unknown self resource
                if obj.new_show < 2:
                    return
                obj.contact = gajim.contacts.create_self_contact(jid=jid,
                    account=account, show=obj.show, status=obj.status,
                    priority=obj.prio, keyID=obj.keyID,
                    resource=obj.resource)
                gajim.contacts.add_contact(account, obj.contact)
                obj.contact_list.append(obj.contact)
            else:
                obj.old_show = statuss.index(obj.contact.show)
            if (resources != [''] and (len(obj.contact_list) != 1 or \
            obj.contact_list[0].show != 'offline')) and \
            not gajim.jid_is_transport(jid):
                # Another resource of an existing contact connected
                obj.old_show = 0
                obj.contact = gajim.contacts.copy_contact(obj.contact)
                obj.contact_list.append(obj.contact)
            obj.contact.resource = resource

            obj.need_add_in_roster = True

        if not gajim.jid_is_transport(jid) and len(obj.contact_list) == 1:
            # It's not an agent
            if obj.old_show == 0 and obj.new_show > 1:
                if not jid in gajim.newly_added[account]:
                    gajim.newly_added[account].append(jid)
                if jid in gajim.to_be_removed[account]:
                    gajim.to_be_removed[account].remove(jid)
            elif obj.old_show > 1 and obj.new_show == 0 and \
            obj.conn.connected > 1:
                if not jid in gajim.to_be_removed[account]:
                    gajim.to_be_removed[account].append(jid)
                if jid in gajim.newly_added[account]:
                    gajim.newly_added[account].remove(jid)
                obj.need_redraw = True

        obj.contact.show = obj.show
        obj.contact.status = obj.status
        obj.contact.priority = obj.prio
        obj.contact.keyID = obj.keyID
        if obj.timestamp:
            obj.contact.last_status_time = obj.timestamp
        elif not gajim.block_signed_in_notifications[account]:
            # We're connected since more that 30 seconds
            obj.contact.last_status_time = localtime()
        obj.contact.contact_nickname = obj.contact_nickname

        if gajim.jid_is_transport(jid):
            return

        # It isn't an agent
        # reset chatstate if needed:
        # (when contact signs out or has errors)
        if obj.show in ('offline', 'error'):
            obj.contact.our_chatstate = obj.contact.chatstate = \
                obj.contact.composing_xep = None

            # TODO: This causes problems when another
            # resource signs off!
            self.stop_all_active_file_transfers(obj.contact)

            # disable encryption, since if any messages are
            # lost they'll be not decryptable (note that
            # this contradicts XEP-0201 - trying to get that
            # in the XEP, though)

            # there won't be any sessions here if the contact terminated
            # their sessions before going offline (which we do)
            for sess in self.get_sessions(jid):
                if obj.fjid != str(sess.jid):
                    continue
                if sess.control:
                    sess.control.no_autonegotiation = False
                if sess.enable_encryption:
                    sess.terminate_e2e()
                    self.delete_session(jid, sess.thread_id)

    def _StanzaArrivedCB(self, con, obj):
        self.last_io = gajim.idlequeue.current_time()

    def _MucOwnerCB(self, con, iq_obj):
        log.debug('MucOwnerCB')
        gajim.nec.push_incoming_event(MucOwnerReceivedEvent(None,
            conn=self, iq_obj=iq_obj))

    def _MucAdminCB(self, con, iq_obj):
        log.debug('MucAdminCB')
        gajim.nec.push_incoming_event(MucAdminReceivedEvent(None,
            conn=self, iq_obj=iq_obj))

    def _IqPingCB(self, con, iq_obj):
        log.debug('IqPingCB')
        gajim.nec.push_incoming_event(PingReceivedEvent(None, conn=self,
            iq_obj=iq_obj))
        raise common.xmpp.NodeProcessed

    def _nec_ping_received(self, obj):
        if obj.conn.name != self.name:
            return
        if not self.connection or self.connected < 2:
            return
        iq_obj = obj.iq_obj.buildReply('result')
        self.connection.send(iq_obj)

    def _PrivacySetCB(self, con, iq_obj):
        """
        Privacy lists (XEP 016)

        A list has been set.
        """
        log.debug('PrivacySetCB')
        if not self.connection or self.connected < 2:
            return
        result = iq_obj.buildReply('result')
        q = result.getTag('query')
        if q:
            result.delChild(q)
        self.connection.send(result)
        raise common.xmpp.NodeProcessed

    def _getRoster(self):
        log.debug('getRosterCB')
        if not self.connection:
            return
        self.connection.getRoster(self._on_roster_set)
        self.discoverItems(gajim.config.get_per('accounts', self.name,
                'hostname'), id_prefix='Gajim_')
        if gajim.config.get_per('accounts', self.name, 'use_ft_proxies'):
            self.discover_ft_proxies()

    def discover_ft_proxies(self):
        cfg_proxies = gajim.config.get_per('accounts', self.name,
                'file_transfer_proxies')
        our_jid = helpers.parse_jid(gajim.get_jid_from_account(self.name) + \
            '/' + self.server_resource)
        if cfg_proxies:
            proxies = [e.strip() for e in cfg_proxies.split(',')]
            for proxy in proxies:
                gajim.proxy65_manager.resolve(proxy, self.connection, our_jid)

    def _on_roster_set(self, roster):
        gajim.nec.push_incoming_event(RosterReceivedEvent(None, conn=self,
            xmpp_roster=roster))

    def _nec_roster_received(self, obj):
        if obj.conn.name != self.name:
            return
        our_jid = gajim.get_jid_from_account(self.name)
        if self.connected > 1 and self.continue_connect_info:
            msg = self.continue_connect_info[1]
            sign_msg = self.continue_connect_info[2]
            signed = ''
            send_first_presence = True
            if sign_msg:
                signed = self.get_signed_presence(msg, self._send_first_presence)
                if signed is None:
                    self.dispatch('GPG_PASSWORD_REQUIRED',
                            (self._send_first_presence,))
                    # _send_first_presence will be called when user enter passphrase
                    send_first_presence = False
            if send_first_presence:
                self._send_first_presence(signed)

        for jid in obj.roster:
            if jid != our_jid and gajim.jid_is_transport(jid) and \
            not gajim.get_transport_name_from_jid(jid):
                # we can't determine which iconset to use
                self.discoverInfo(jid)

        gajim.logger.replace_roster(self.name, obj.version, obj.roster)
        if obj.received_from_server:
            for contact in gajim.contacts.iter_contacts(self.name):
                if not contact.is_groupchat() and contact.jid not in obj.roster\
                and contact.jid != our_jid:
                    gajim.nec.push_incoming_event(RosterInfoEvent(None,
                        conn=self, jid=contact.jid, nickname=None, sub=None,
                        ask=None, groups=()))
            for jid, info in obj.roster.items():
                gajim.nec.push_incoming_event(RosterInfoEvent(None,
                    conn=self, jid=jid, nickname=info['name'],
                    sub=info['subscription'], ask=info['ask'],
                    groups=info['groups']))

    def _send_first_presence(self, signed = ''):
        show = self.continue_connect_info[0]
        msg = self.continue_connect_info[1]
        sign_msg = self.continue_connect_info[2]
        if sign_msg and not signed:
            signed = self.get_signed_presence(msg)
            if signed is None:
                self.dispatch('BAD_PASSPHRASE', ())
                self.USE_GPG = False
                signed = ''
        self.connected = gajim.SHOW_LIST.index(show)
        sshow = helpers.get_xmpp_show(show)
        # send our presence
        if show == 'invisible':
            self.send_invisible_presence(msg, signed, True)
            return
        if show not in ['offline', 'online', 'chat', 'away', 'xa', 'dnd']:
            return
        priority = gajim.get_priority(self.name, sshow)
        our_jid = helpers.parse_jid(gajim.get_jid_from_account(self.name))
        vcard = self.get_cached_vcard(our_jid)
        if vcard and 'PHOTO' in vcard and 'SHA' in vcard['PHOTO']:
            self.vcard_sha = vcard['PHOTO']['SHA']
        p = common.xmpp.Presence(typ = None, priority = priority, show = sshow)
        p = self.add_sha(p)
        if msg:
            p.setStatus(msg)
        if signed:
            p.setTag(common.xmpp.NS_SIGNED + ' x').setData(signed)

        if self.connection:
            self.connection.send(p)
            self.priority = priority
        self.dispatch('STATUS', show)
        if self.vcard_supported:
            # ask our VCard
            self.request_vcard(None)

        # Get bookmarks from private namespace
        self.get_bookmarks()

        # Get annotations from private namespace
        self.get_annotations()

        # Inform GUI we just signed in
        self.dispatch('SIGNED_IN', ())
        self.send_awaiting_pep()
        self.continue_connect_info = None

    def request_gmail_notifications(self):
        if not self.connection or self.connected < 2:
            return
        # It's a gmail account,
        # inform the server that we want e-mail notifications
        our_jid = helpers.parse_jid(gajim.get_jid_from_account(self.name))
        log.debug(('%s is a gmail account. Setting option '
                'to get e-mail notifications on the server.') % (our_jid))
        iq = common.xmpp.Iq(typ = 'set', to = our_jid)
        iq.setAttr('id', 'MailNotify')
        query = iq.setTag('usersetting')
        query.setNamespace(common.xmpp.NS_GTALKSETTING)
        query = query.setTag('mailnotifications')
        query.setAttr('value', 'true')
        self.connection.send(iq)
        # Ask how many messages there are now
        iq = common.xmpp.Iq(typ = 'get')
        iq.setID(self.connection.getAnID())
        query = iq.setTag('query')
        query.setNamespace(common.xmpp.NS_GMAILNOTIFY)
        self.connection.send(iq)


    def _SearchCB(self, con, iq_obj):
        log.debug('SearchCB')
        gajim.nec.push_incoming_event(SearchFormReceivedEvent(None,
            conn=self, iq_obj=iq_obj))

    def _StreamCB(self, con, iq_obj):
        log.debug('StreamCB')
        gajim.nec.push_incoming_event(StreamReceivedEvent(None,
            conn=self, iq_obj=iq_obj))

    def _register_handlers(self, con, con_type):
        # try to find another way to register handlers in each class
        # that defines handlers
        con.RegisterHandler('message', self._messageCB)
        con.RegisterHandler('presence', self._presenceCB)
        con.RegisterHandler('presence', self._capsPresenceCB)
        # We use makefirst so that this handler is called before _messageCB, and
        # can prevent calling it when it's not needed.
        # We also don't check for namespace, else it cannot stop _messageCB to be
        # called
        con.RegisterHandler('message', self._pubsubEventCB, makefirst=True)
        con.RegisterHandler('iq', self._vCardCB, 'result',
                common.xmpp.NS_VCARD)
        con.RegisterHandler('iq', self._rosterSetCB, 'set',
                common.xmpp.NS_ROSTER)
        con.RegisterHandler('iq', self._siSetCB, 'set',
                common.xmpp.NS_SI)
        con.RegisterHandler('iq', self._rosterItemExchangeCB, 'set',
                common.xmpp.NS_ROSTERX)
        con.RegisterHandler('iq', self._siErrorCB, 'error',
                common.xmpp.NS_SI)
        con.RegisterHandler('iq', self._siResultCB, 'result',
                common.xmpp.NS_SI)
        con.RegisterHandler('iq', self._discoGetCB, 'get',
                common.xmpp.NS_DISCO)
        con.RegisterHandler('iq', self._bytestreamSetCB, 'set',
                common.xmpp.NS_BYTESTREAM)
        con.RegisterHandler('iq', self._bytestreamResultCB, 'result',
                common.xmpp.NS_BYTESTREAM)
        con.RegisterHandler('iq', self._bytestreamErrorCB, 'error',
                common.xmpp.NS_BYTESTREAM)
        con.RegisterHandlerOnce('iq', self.IBBAllIqHandler)
        con.RegisterHandler('iq', self.IBBIqHandler, ns=common.xmpp.NS_IBB)
        con.RegisterHandler('message', self.IBBMessageHandler,
            ns=common.xmpp.NS_IBB)
        con.RegisterHandler('iq', self._DiscoverItemsCB, 'result',
                common.xmpp.NS_DISCO_ITEMS)
        con.RegisterHandler('iq', self._DiscoverItemsErrorCB, 'error',
                common.xmpp.NS_DISCO_ITEMS)
        con.RegisterHandler('iq', self._DiscoverInfoCB, 'result',
                common.xmpp.NS_DISCO_INFO)
        con.RegisterHandler('iq', self._DiscoverInfoErrorCB, 'error',
                common.xmpp.NS_DISCO_INFO)
        con.RegisterHandler('iq', self._VersionCB, 'get',
                common.xmpp.NS_VERSION)
        con.RegisterHandler('iq', self._TimeCB, 'get',
                common.xmpp.NS_TIME)
        con.RegisterHandler('iq', self._TimeRevisedCB, 'get',
                common.xmpp.NS_TIME_REVISED)
        con.RegisterHandler('iq', self._LastCB, 'get',
                common.xmpp.NS_LAST)
        con.RegisterHandler('iq', self._LastResultCB, 'result',
                common.xmpp.NS_LAST)
        con.RegisterHandler('iq', self._VersionResultCB, 'result',
                common.xmpp.NS_VERSION)
        con.RegisterHandler('iq', self._TimeRevisedResultCB, 'result',
                common.xmpp.NS_TIME_REVISED)
        con.RegisterHandler('iq', self._MucOwnerCB, 'result',
                common.xmpp.NS_MUC_OWNER)
        con.RegisterHandler('iq', self._MucAdminCB, 'result',
                common.xmpp.NS_MUC_ADMIN)
        con.RegisterHandler('iq', self._PrivateCB, 'result',
                common.xmpp.NS_PRIVATE)
        con.RegisterHandler('iq', self._SecLabelCB, 'result',
                common.xmpp.NS_SECLABEL_CATALOG)
        con.RegisterHandler('iq', self._HttpAuthCB, 'get',
                common.xmpp.NS_HTTP_AUTH)
        con.RegisterHandler('iq', self._CommandExecuteCB, 'set',
                common.xmpp.NS_COMMANDS)
        con.RegisterHandler('iq', self._gMailNewMailCB, 'set',
                common.xmpp.NS_GMAILNOTIFY)
        con.RegisterHandler('iq', self._gMailQueryCB, 'result',
                common.xmpp.NS_GMAILNOTIFY)
        con.RegisterHandler('iq', self._DiscoverInfoGetCB, 'get',
                common.xmpp.NS_DISCO_INFO)
        con.RegisterHandler('iq', self._DiscoverItemsGetCB, 'get',
                common.xmpp.NS_DISCO_ITEMS)
        con.RegisterHandler('iq', self._IqPingCB, 'get',
                common.xmpp.NS_PING)
        con.RegisterHandler('iq', self._SearchCB, 'result',
                common.xmpp.NS_SEARCH)
        con.RegisterHandler('iq', self._PrivacySetCB, 'set',
                common.xmpp.NS_PRIVACY)
        con.RegisterHandler('iq', self._ArchiveCB, ns=common.xmpp.NS_ARCHIVE)
        con.RegisterHandler('iq', self._PubSubCB, 'result')
        con.RegisterHandler('iq', self._PubSubErrorCB, 'error')
        con.RegisterHandler('iq', self._JingleCB, 'result')
        con.RegisterHandler('iq', self._JingleCB, 'error')
        con.RegisterHandler('iq', self._JingleCB, 'set',
                common.xmpp.NS_JINGLE)
        con.RegisterHandler('iq', self._ErrorCB, 'error')
        con.RegisterHandler('iq', self._IqCB)
        con.RegisterHandler('iq', self._StanzaArrivedCB)
        con.RegisterHandler('iq', self._ResultCB, 'result')
        con.RegisterHandler('presence', self._StanzaArrivedCB)
        con.RegisterHandler('message', self._StanzaArrivedCB)
        con.RegisterHandler('unknown', self._StreamCB, 'urn:ietf:params:xml:ns:xmpp-streams', xmlns='http://etherx.jabber.org/streams')
