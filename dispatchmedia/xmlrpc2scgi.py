#!/usr/bin/env python

# Copyright (C) 2005-2007, Glenn Washburn
# Refactoring - Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
# SSH tunneling and refactoring - Copyright (c) 2011 Quantique
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the
# OpenSSL library under certain conditions as described in each
# individual source file, and distribute linked combinations
# including the two.
#
# You must obey the GNU General Public License in all respects for
# all of the code used other than OpenSSL.  If you modify file(s)
# with this exception, you may extend this exception to your version
# of the file(s), but you are not obligated to do so.  If you do not
# wish to do so, delete this exception statement from your version.
# If you delete this exception statement from all source files in the
# program, then also delete it here.
#
# Contact:  Glenn Washburn <crass@berlios.de>
#
# Note that, before you contact the original author, this version of
# the module has undergone extensive refactoring.
#

"""
Run XMLRPC over SCGI.
"""


__all__ = ( 'do_xmlrpc', 'convert_params_to_native', 'RPCError')


import pipes
import posixpath
import re
import subprocess
import sys
try:
    import urlparse
    import xmlrpclib
except ImportError:
    import urllib.parse as urlparse
    import xmlrpc.client as xmlrpclib


class RPCError(Exception):
    pass


DEBUG = False


## SCGI
def make_scgi_headers(headers):
    return ''.join(('%s\x00%s\x00' % t for t in headers))


def encode_netstring(string):
    return '%d:%s,' % (len(string), string)


def write_scgi(stream, data):
    """ Make an scgi request,
        see spec at: http://python.ca/scgi/protocol.txt
    """

    if isinstance(data, str):
        data = data.encode()
    headers = make_scgi_headers((
        ('CONTENT_LENGTH', str(len(data))),
        ('SCGI', '1'),
    ))

    stream.write(encode_netstring(headers).encode())
    stream.write(data)
    stream.flush()


## HTTP
def parse_http_headers(headers):
    """ Get header (key, value) pairs from header string.
    """

    return dict(line.rstrip().split(": ", 1)
        for line in headers.splitlines())


def parse_http(resp):
    # The response is plain HTTP not wrapped by SCGI,
    # which is only a request spec.
    # The headers are the bare xml-rpc requirements, hard-coded by rtorrent.
    # Always 200 OK; xml-rpc has its own error signaling.
    headers_str, content = resp.split(b"\r\n\r\n", 1)
    headers = parse_http_headers(headers_str.decode())
    clen = int(headers['Content-Length'])

    # Just in case the transport is bogus.
    assert clen == len(content)

    return content



## Socket IO
SCHEME_TCP = 'tcp'
SCHEME_UNIX = 'unix'
SCHEME_SSH_UNIX = 'ssh+unix'
urlparse.uses_netloc.append(SCHEME_TCP)
urlparse.uses_netloc.append(SCHEME_SSH_UNIX)

# POSIX.2 portable
NETCAT = '/bin/nc'


def cmd_of_endpoint(url):
    """ Parse urls used to reach the rtorrent SCGI socket.

        Currently allows unix sockets, local or via ssh, and tcp sockets.

        Unix domain sockets
            unix:/var/run/rtorrent.socket
            unix:rtorrent.socket
            /var/run/rtorrent.socket
            rtorrent.socket

        The unix scheme is the default for urls starting with a slash.

        Unix domain sockets, on a remote host accessed over SSH
            ssh+unix://host/var/run/rtorrent.socket
            ssh+unix://user@host/var/run/rtorrent.socket
            ssh+unix://user@host/~/rtorrent/socket
            ssh+unix://host:5022/var/run/rtorrent/socket

        The ssh syntax aims to be compatible with this internet draft:
            http://tools.ietf.org/html/draft-ietf-secsh-scp-sftp-ssh-uri
        A leading tilde can be used to refer to the home directory.

        TCP sockets:
            Needs firewalling, has poor security.
            tcp://host:port/

        TODO normal xmlrpc endpoints (no SCGI):
            Needs auth to be secure.
            https://host:port/
            The http request goes to /RPC2

    """

    # pipes.quote is used because ssh always goes through a login shell.
    # The only exception is for redirecting ports, which can't be used
    # to access a domain socket.

    us = urlparse.urlsplit(url, SCHEME_UNIX, allow_fragments=False)
    path = us.path
    netloc = us.netloc

    if us.scheme == SCHEME_TCP:
        if url != urlparse.urlunsplit((SCHEME_TCP, netloc, '/', '', '')):
            raise ValueError(url)
        if netloc != '%s:%d' % (us.hostname, us.port):
            raise ValueError(url)
        cmd = [ NETCAT, '--', netloc ]
    elif us.scheme == SCHEME_UNIX:
        if (url != urlparse.urlunsplit((SCHEME_UNIX, '', path, '', ''))
           and url != urlparse.urlunsplit(('', '', path, '', ''))):
            raise ValueError(url)
        if path.startswith('~/'):
            path = posixpath.expanduser(path)
        elif path.startswith('/'):
            pass
        else:
            raise ValueError(path, 'Path must start with / or ~/')
        cmd = [ NETCAT, '-U', '--', path ]
    elif us.scheme == SCHEME_SSH_UNIX:
        if url != urlparse.urlunsplit((SCHEME_SSH_UNIX, netloc, path, '', '')):
            raise ValueError(url)
        if not path or not path.startswith('/'):
            raise ValueError(url)

        if path.startswith('/~/'):
            clean_path = '~/' + pipes.quote(path[3:])
        else:
            clean_path = pipes.quote(path)

        if us.username:
            # user@ takes priority on -l user
            ssh_netloc = '%s@%s' % (us.username, us.hostname)
        else:
            ssh_netloc = us.hostname

        if us.port:
            reconstructed_netloc = '%s:%d' % (ssh_netloc, us.port)
            port_flag = [ '-p', str(us.port) ]
        else:
            reconstructed_netloc = ssh_netloc
            port_flag = []

        if reconstructed_netloc != netloc:
            raise ValueError(url)

        cmd = [ 'ssh', '-T' ] + port_flag + [
            '--', netloc, NETCAT, '-U', '--', clean_path, ]
    else:
        raise ValueError(url)

    return cmd


## Protocol
def do_transport(endpoint, data):
    """ Open a transport, send an SCGI request, wait and grab an HTTP reply.

        TODO: accept HTTP endpoints as well, with none of the SCGI wrapping.
    """

    cmd = cmd_of_endpoint(endpoint)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    # Can't use communicate:
    # that would close stdin, send a sighup, netcat would bail.
    write_scgi(proc.stdin, data)
    resp_http = proc.stdout.read()
    proc.stdin.close()
    proc.wait()
    proc.stdout.close()

    if proc.returncode:
        raise RPCError('nc', proc.returncode, cmd)

    if not resp_http:
        raise RPCError('empty', cmd)

    return parse_http(resp_http)


def do_xmlrpc(endpoint, method, *args):
    """ Send an xmlrpc request to endpoint.
        endpoint: transport url (see cmd_of_endpoint for possible values)
        method:   xmlrpc method name
        params:   tuple of simple python objects
        returns:  unmarshalled response
    """

    req_xml = xmlrpclib.dumps(args, method)
    if DEBUG:
        sys.stderr.write('req_xml: %s\n' % req_xml)
    resp_xml = do_transport(endpoint, req_xml)
    if DEBUG:
        sys.stderr.write('resp_xml: %s\n' % resp_xml)

    # Yes, it's ok to unwrap the totally superfluous methodResponse.params.
    # Faults were already turned into exceptions.
    resp_dict = xmlrpclib.loads(resp_xml)
    assert len(resp_dict) == 2 and resp_dict[1] is None \
            and len(resp_dict[0]) == 1, resp_dict
    resp = resp_dict[0][0]

    return resp


POSINT_RE = re.compile(r'^[0-9]+$')


def convert_params_to_native(params):
    """ Parse xmlrpc-c command line arg syntax.

        Arguments are integers if they match [0-9]+, strings otherwise,
        unless prefixed by b/ i/ s/ l/
        In which case, they are bools, integers, strings, or lists.
        Explicit prefixes are recommended when dealing with external input.
    """

    cparams = []
    for param in params:
        if len(param) < 2 or param[1] != '/':
            if POSINT_RE.match(param):
                cparams.append(int(param))
            else:
                cparams.append(str(param))
            continue

        if param[0] == 'i':
            ptype = int
        elif param[0] == 'b':
            ptype = bool
        elif param[0] == 's':
            ptype = str
        elif param[0] == 'l':
            ptype = lambda x: x.split(',')
        else:
            raise ValueError('Invalid parameter', param)

        cparams.append(ptype(param[2:]))

    return tuple(cparams)


