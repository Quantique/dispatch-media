# Copyright 2010 Quantique. Licence: GPL3+


import contextlib
import errno
import hashlib
import logging
import os.path

LOGGER = logging.getLogger(__name__)

try:
    # python-libtorrent
    from libtorrent import bdecode, bencode
except ImportError as e:
    try:
        # python-bittorrent
        from BitTorrent.bencode import bdecode, bencode
    except ImportError:
        raise e
    else:
        LOGGER.info('Using the slower python-bittorrent,'
                ' install python-libtorrent to bdecode faster')


class TorrentFileError(ValueError):
    pass


class BData(object):
    __slots__ = ('_tdata', '_fname')

    def __init__(self, tdata, file_name=None):
        if not isinstance(tdata, dict):
            raise TorrentFileError(
                'bdecoded data should be a dictionary: %s' % self)
        self._tdata = tdata
        self._fname = file_name

    def as_torrent(self):
        return TorrentData(self)

    def to_open_file(self, fhandle):
        # XXX move this out?
        fhandle.write(bencode(self._tdata))

    def __repr__(self):
        if self._fname is not None:
            return '<data bdecoded from %r>' % self._fname
        return '<bdecoded data at %x>' % id(self)


class LibtorrentResume(object):
    # Adapter pattern
    # Using composition rather than inheritance because
    # resume data can be torrent data as well, but only
    # for some rtorrent versions.
    def __init__(self, bdata):
        self._bdata = bdata
        if self.bdata._fname and self.bdata._fname.endswith(
                '.torrent.libtorrent_resume'):
            self._rdata = self._bdata._tdata
        else:
            # The older, nested variant
            self._rdata = self._bdata._tdata['libtorrent_resume']
        if 'bitfield' not in self._rdata:
            raise TorrentFileError('No bitfield')


class TorrentData(object):
    # Adapter pattern
    # BData with an info dict

    def __init__(self, bdata):
        self._bdata = bdata
        if 'info' not in self._tdata:
            raise TorrentFileError('No info_dict')

    @property
    def _tdata(self):
        return self._bdata._tdata

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

    def require_sane_encoding(self):
        """
        Make sure file names are safe to use.

        The spec mandates UTF-8 everywhere.
        Make sure we have UTF-8 or a subset.
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
    def piece_length(self):
        return self._meta_inf['piece length']

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


def from_filehandle(fhandle):
    # Deserialisation

    if hasattr(fhandle, 'name'):
        desc = fhandle.name
        file_name = fhandle.name
    else:
        desc = fhandle
        file_name = None

    # XXX close ASAP doesn't work well for stdin
    # Same problem with files opened r+
    #with contextlib.closing(fhandle):
    if True:
        fdata = fhandle.read()

    if not fdata:  # Coerce to bool -> test for emptiness
        raise TorrentFileError("Torrent file empty: %s" % desc)
    try:
        tdata = bdecode(fdata)
        if tdata is None:  # libtorrent doesn't report errors properly
            raise ValueError
        if not isinstance(tdata, dict):
            raise TorrentFileError(
                "bdecoded data isn't a dictionary: %s" % desc)
    except ValueError as exn:
        raise TorrentFileError("Couldn't bdecode file: %s" % desc)

    return BData(tdata, file_name=file_name)


def from_filename(fname):
    try:
        with open(fname) as fhandle:
            return from_filehandle(fhandle)
    except IOError as e:
        if e.errno == errno.ENOENT:
            raise TorrentFileError(
                'Torrent file doesn\'t exist: %r' % fname)
        else:
            raise

