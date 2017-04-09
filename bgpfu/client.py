# Copyright (C) 2016 Matt Griswold <grizz@20c.com>
#
# This file is part of bgpfu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

from bgpfu.inet import PrefixList
import logging
from pkg_resources import get_distribution
import re
import socket


class IRRClient(object):

    def __init__(self, host='whois.radb.net', port=43):
        self.keepalive = True
        self.host = host
        self.port = port

        self.re_res = re.compile('(?P<state>[ACDEF])(?P<len>\d*)(?P<msg>[\w\s]*)$')

        self.log = logging.getLogger(__name__)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, typ, value, traceback):
        self.sckt.shutdown(socket.SHUT_RDWR)
        self.sckt.close()

    def connect(self):
        self.sckt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sckt.connect((self.host, self.port))

        if self.keepalive:
            self.sckt.send('!!\n')

        self.query('!nBGPFU-%s' % get_distribution('bgpfu').version)

    def parse_response(self, response):
        self.log.debug("response %s", response)
        match = self.re_res.match(response)
        if not match:
            raise RuntimeError("invalid response '%s'" % (response,))

        state = match.group('state')
        if state == 'A':
            return int(match.group('len'))
        elif state == 'C':
            return False
        elif state == 'D':
            self.log.warning("skipping key not found")
            return False
        elif state == 'E':
            raise KeyError("multiple copies of key in database")
        elif state == 'F':
            if match.group('msg'):
                msg = match.group('msg').strip()
            else:
                msg = 'unknown error'
            raise RuntimeError(msg)

        raise RuntimeError("invalid response '%s'" % (response,))

    def query(self, q):
        q = q + '\n'
        ttl = 0
        sz = len(q)
        while ttl < sz:
            sent = self.sckt.send(q[ttl:])
            if not sent:
                raise RuntimeError("socket connection broken")
            ttl = ttl + sent

        self.log.debug("sent %s %d", q.rstrip(), ttl)

        chunks = []
        ttl = 0
        chunk_size = 4096

        chunk = self.sckt.recv(chunk_size)
        response, chunk = chunk.split('\n', 1)

        sz = self.parse_response(response)
        if not sz:
            return

        ttl = len(chunk)
        chunks.append(chunk)

        while ttl <= sz:
            self.log.debug("ttl %d, sz %d", ttl, sz)
            chunk = self.sckt.recv(chunk_size)
            if chunk == '':
                raise RuntimeError("socket connection broken")
            chunks.append(chunk)
            ttl = ttl + len(chunk)
#            self.log.debug("ttl %d, sz %d", ttl, sz)
#            self.log.debug("chunk '%s'", chunk)

        # split data from response code
        self.log.debug("ttl %d, sz %d", ttl, sz)
        suffix = chunks[-1][-(ttl - sz):]
        chunks[-1] = chunks[-1][:-(ttl - sz)]
        self.log.debug("suffix %d '%s'", ttl - sz, suffix)
        return ''.join(chunks)

    def set_sources(self, sources):
        """ set sources to the specified list """
        return self.query('!s%s' % sources)

    def get_set(self, objs, expand=True):
        """
        Return members of an as-set or route-set.
        if expand is true, also recursively expand members of all sets within the named set.
        """
        if isinstance(objs, basestring):
            objs = (objs,)

        sets = []

        for each in objs:
            q = '!i' + each
            if expand:
                q = q + ',1'
            sets += self.query(q).split()

        return set(sets)

    def routes(self, obj, proto=4):
        """ get routes for specified object """
        proto = int(proto)
        if proto == 4:
            q = '!g'
        elif proto == 6:
            q = '!6'
        else:
            raise ValueError("unknown protocol '%s'" % str(proto))

        q += obj
        prefixes = self.query(q)
        if prefixes:
            return prefixes.split()
        return []

    def prefixlist(self, as_set, proto=4):
        """ get prefix list for specified as-set(s) """

        try:
            all_sets = self.get_set(as_set)
        except AttributeError:
            all_sets = (as_set,)

        prefixes = []
        for each in all_sets:
            prefixes += self.routes(each, proto)
        # set for uniq
        return PrefixList(set(prefixes))

