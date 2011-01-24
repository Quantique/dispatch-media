# Copyright 2010 Quantique. Licence: GPL3+


import contextlib
import hashlib
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


class BData(object):
    def __init__(self, tdata):
        if not isinstance(tdata, dict):
            raise TorrentFileError('Not bencoded data')
        self._tdata = tdata

    @classmethod
    def from_file(cls, fname):
        # XXX compat wrapper
        return from_filename(fname, profile=cls)

    @classmethod
    def from_open_file(cls, fhandle):
        # XXX compat wrapper
        return from_filehandle(fhandle, profile=cls)

    def to_open_file(self, fhandle):
        fhandle.write(bencode(self._tdata))


class TorrentData(BData):
    def __init__(self, tdata):
        super(TorrentData, self).__init__(tdata)
        if 'info' not in tdata:
            raise TorrentFileError('No info_dict')

    @property
    def encoding(self):
        return self._tdata.get('encoding', 'UTF-8')

    @property
    def _meta_inf(self):
        return self._tdata['info']

    @property
    def info_hash(self):
        # Wasteful but convenient
        return hashlib.sha1(bencode(self._meta_inf)).hexdigest()

    def is_rtorrent_session_data(self):
        return 'rtorrent' in self._tdata

    def down_loc(self, down_base, use_rtorrent_meta=True):
        if use_rtorrent_meta and self.is_rtorrent_session_data():
            down_loc = os.path.expanduser(self._tdata['rtorrent']['directory'])
            if not self.is_multi:
                down_loc = os.path.join(down_loc, self.name)
        else:
            down_loc = os.path.join(down_base, self.name)
        return down_loc

    def require_sane_encoding(self):
        """
        Make sure file names are safe to use.

        The spec mandates UTF-8 everywhere. Make sure we have UTF-8 or a subset.
        ANSI_X3.4-1968 is ASCII.
        """

        if self.encoding.upper() not in ('UTF-8', 'ANSI_X3.4-1968', 'UTF8'):
            raise TorrentFileError(
                    'Invalid torrent encoding: %s.' % self.encoding)

    @property
    def name(self):
        #self.require_sane_encoding()
        # The spec mandates UTF-8 everywhere,
        # but there's crap out there that we'll tolerate
        if 'name.utf-8' in self._meta_inf:
            return self._meta_inf['name.utf-8'].decode('utf-8')
        else:
            return self._meta_inf['name'].decode(self.encoding)

    @property
    def is_multi(self):
        return 'files' in self._meta_inf

    @property
    def multi_finfo(self):
        return self._meta_inf['files']

    def multi_finfo_path(self, finfo):
        #self.require_sane_encoding()
        if 'path.utf-8' in finfo:
            return [elem.decode('utf-8') for elem in finfo['path.utf-8']]
        else:
            return [elem.decode(self.encoding) for elem in finfo['path']]

    def torrent_files(self):
        if self.is_multi:
            for finfo in self.multi_finfo:
                path = os.path.join(self.name, *self.multi_finfo_path(finfo))
                yield path, finfo['length']
        else:
            path = self.name
            finfo = self._meta_inf
            yield path, finfo['length']

class Profile(object):
    bdata = BData
    torrent = TorrentData
    rtorrent = TorrentData # XXX
    best = object()

def from_filehandle(fhandle, name=None, profile=Profile.torrent):
    if profile is not Profile.best and not issubclass(profile, BData):
        raise TypeError(profile, BData)

    if name is None:
        if hasattr(fhandle, 'name'):
            name = fhandle.name
        else:
            name = fhandle

    with contextlib.closing(fhandle):
        fdata = fhandle.read()

    if not fdata: # Coerce to bool -> test for emptiness
        raise TorrentFileError("Torrent file empty: %s" % name)
    try:
        tdata = bdecode(fdata)
        if tdata is None: # libtorrent doesn't report errors properly
            raise ValueError
    except ValueError, exn:
        raise TorrentFileError("Couldn't parse torrent: %s" % name)

    if profile is Profile.best:
        for pr in (Profile.rtorrent, Profile.torrent):
            try:
                return pr(tdata)
            except TorrentFileError:
                pass
        return BData(tdata)
    else:
        return profile(tdata)

def from_filename(fname, *args, **kargs):
    with open(fname) as fhandle:
        return from_filehandle(fhandle, name=fname, *args, **kargs)


