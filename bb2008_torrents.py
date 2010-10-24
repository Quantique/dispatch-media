# Copyright 2010 Quantique. Licence: GPL3+


import logging

LOGGER = logging.getLogger(__name__)

try
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
        LOGGER.error("Torrent file empty: %s", fname)
        raise TorrentFileError(fname)
    try:
        return bdecode(fdata)
    except ValueError, exn:
        LOGGER.exception("Couldn't parse torrent: %s", fname)
        raise TorrentFileError(fname)

def require_sane_encoding(dct):
    """
    Make sure file names are safe to use.
    """

    assert 'encoding' not in dct \
            or dct['encoding'] in ('UTF-8', 'ANSI_X3.4-1968', 'UTF8'), \
            fname



