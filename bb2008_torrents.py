# Copyright 2010 Quantique. Licence: GPL3+


import logging
import os.path

LOGGER = logging.getLogger(__name__)

try:
    # python-libtorrent
    from libtorrent import bdecode, bencode
except ImportError, e:
    try:
        # python-bittorrent
        from BitTorrent.bencode import bdecode, bencode
    except ImportError, e2:
        raise e
    else:
        LOGGER.info('Using the slower python-bittorrent,'
                ' install python-libtorrent to bdecode faster')

class TorrentFileError(ValueError):
    pass

def read_torrent(fname):
    with open(fname) as fhandle:
        fdata = fhandle.read()
    if not fdata: # Coerce to bool -> test for emptiness
        raise TorrentFileError("Torrent file empty: %s" % fname)
    try:
        r = bdecode(fdata)
        if r is None: # libtorrent doesn't report errors properly
            raise ValueError
    except ValueError, exn:
        raise TorrentFileError("Couldn't parse torrent: %s" % fname)
    else:
        return r

def require_sane_encoding(dct):
    """
    Make sure file names are safe to use.

    The spec mandates UTF-8 everywhere. Make sure we have UTF-8 or a subset.
    ANSI_X3.4-1968 is ASCII.
    """

    if 'encoding' not in dct:
        return
    if dct['encoding'].upper() not in ('UTF-8', 'ANSI_X3.4-1968', 'UTF8'):
        raise TorrentFileError(
                'Invalid torrent encoding: %s.' % dct['encoding'])


def torrent_files(dct):
    #require_sane_encoding(dct)
    # The spec mandates UTF-8 everywhere,
    # but there's crap out there that we'll tolerate
    encoding = dct.get('encoding', 'UTF-8')
    meta_inf = dct['info']
    if 'name.utf-8' in meta_inf:
        base = meta_inf['name.utf-8'].decode('utf-8')
    else:
        base = meta_inf['name'].decode(encoding)
    if 'files' in meta_inf: # multi
        for finfo in meta_inf['files']:
            path = base
            if 'path.utf-8' in finfo:
                for elem in finfo['path.utf-8']:
                    path = os.path.join(path, elem.decode('utf-8'))
            else:
                for elem in finfo['path']:
                    path = os.path.join(path, elem.decode(encoding))
            yield path, finfo['length']
    else:
        path = base
        finfo = meta_inf
        yield path, finfo['length']


