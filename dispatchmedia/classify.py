# Copyright 2010 Quantique. Licence: GPL3+

from dispatchmedia.common import unix_basename, ensure_dir
from dispatchmedia.torrents import TorrentData
import dispatchmedia.media_types as MT

from collections import defaultdict
import logging
import os.path
import subprocess
import re

LOGGER = logging.getLogger(__name__)

# Nonnegative decimal SP filename NL
LINE_RE = re.compile(r'^(\d+) (.+)\n$')
# r00 style multipart
RAR_EXT_RE = re.compile(r'^\.r(\d\d)$')
TERM_SEP_RE = re.compile(r'[_\W]+', re.UNICODE)
SEVEN_BORDER_RE = re.compile(r'^-+ -+ (-+) -+  (-+)\n$')

def defset(line):
    return set(line.split())

# ogg could conceivably be video (oga is unambiguous)
MUSIC_EXTS = defset('mp3 oga ogg flac m4a mpc ape wma')
# mp4 could conceivably be audio (m4v is unambiguous)
VID_EXTS = defset('avi mkv mpg mov ogv ogm m4v mp4 m2ts vob rmvb wmv')

FONT_EXTS = defset('otf ttf ttc pfb')
ISO_EXTS = defset('iso nrg ccd b5i cdi')
COMICBOOK_EXTS = defset('cbt cbr cbz')
EBOOK_EXTS = defset('epub html htm chm rtf txt djvu pdf doc docx lrf mobi lit eps')
SUBTITLES_EXTS = defset('ass ssa srt sub sup')

# Common tar archives
TAR_EXTS = defset('gz bz2 xz')
ARCHIVE_EXTS = defset('rar zip tar 7z')
for ext in TAR_EXTS:
    ARCHIVE_EXTS.add('tar.' + ext)
    ARCHIVE_EXTS.add('t' + ext)

# jar and ace are archives, I don't plan to deal with them.
# bin can be bin/cue (iso-like), or a binary executable.
# there's some magic below to handle bin/cue.
AMBIGUOUS_EXTS = defset('png jpg jpeg gif py xml exe bin jar ace sh')
# Not dealing with subs-only releases right now
AMBIGUOUS_EXTS.update(SUBTITLES_EXTS)

# TV or Anime, these are hard to differentiate.
SERIES_HINTS = defset('HDTV TV season seasons series')
MOVIE_HINTS = defset('Cam TS TeleSync TC TeleCine R5 DVDSCR')
GAME_PLATFORMS = defset('Xbox Wii PS2 PS3 PC')

def intersect_keepcase(s1, s2):
    r = set()
    for i in s1:
        if i.lower() in s2:
            r.add(i)
    return r

def istream_iter(istream):
    for line in istream:
        size, fname = LINE_RE.match(line).groups()
        yield fname, size

class UnknownReleaseKindError(ValueError):
    pass

class Release(object):
    def __init__(self, fname, name=None):
        self.fname = fname
        if name is None:
            self.name = unix_basename(fname)
        else:
            self.name = name

    @classmethod
    def from_fname(cls, fname):
        if os.path.isdir(fname):
            return Directory(fname)
        prefix, ext = os.path.splitext(fname)
        ext = ext.lower()
        if ext == '.torrent':
            return Torrent(fname)
        if ext[0] == '.' and ext[1:] in ARCHIVE_EXTS:
            return Archive(fname)
        raise UnknownReleaseKindError('Unknown release type for %s' % fname)

class Torrent(Release):
    def __init__(self, *args, **kargs):
        super(Torrent, self).__init__(*args, **kargs)
        self._data = TorrentData.from_file(self.fname)

    def __del__(self):
        del self._data

    def iter_names_and_sizes(self):
        return self._data.torrent_files()

    def walk_lockstep(self, down_loc, dest_parent):
        if not os.path.exists(down_loc):
            LOGGER.warn('Skipping inexistent %s', down_loc)
            return

        dest_loc = os.path.join(dest_parent, self._data.name)
        if not self._data.is_multi:
            yield down_loc, dest_loc
            return

        dirs_done = set()
        ensure_dir(dest_loc)

        for path_bytes in self._data.multi_finfo:
            path_chars = self._data.multi_finfo_path(path_bytes)
            src = os.path.join(down_loc, *path_chars)
            if not os.path.exists(src):
                LOGGER.debug('Skipping inexistent %s', src)
                continue
            dest = os.path.join(dest_loc, *path_chars)
            dir_path = path_chars[:-1]
            if tuple(dir_path) not in dirs_done:
                pfx = dest_loc
                pfx2 = []
                for fragment in dir_path:
                    pfx += '/' + fragment
                    pfx2.append(fragment)
                    pfx3 = tuple(pfx2)
                    if pfx3 not in dirs_done:
                        ensure_dir(pfx)
                        dirs_done.add(pfx3)
            yield src, dest

    def down_loc(self, default_down_base):
        return self._data.down_loc(default_down_base)


class TransmissionTorrent(Torrent):
    def __init__(self, fname, config_dir):
        super(TransmissionTorrent, self).__init__(fname)
        self.config_dir = config_dir

    @property
    def transmission_basename(self):
        # Are slashes even allowed? name should probably require no slashes.
        name = self._data.name.replace('/', '_')
        short_ih = self._data.info_hash[:16]
        return name + '.' + short_ih

    @property
    def transmission_resume_fname(self):
        return os.path.join(self.config_dir, 'resume',
                self.transmission_basename + '.resume')

    @property
    def transmission_down_dir(self):
        resume_data = TorrentData.from_file(self.transmission_resume_fname)
        # XXX Not sure about encoding
        ddir = resume_data._tdata['destination'].decode('utf-8')
        del resume_data
        return ddir

    def down_loc(self, default_down_base):
        return os.path.join(self.transmission_down_dir, self._data.name)

class Directory(Release):
    def iter_names_and_sizes(self):
        cmd = [ 'find', '-type', 'f', '-printf', '%s %p\n', ]
        proc = subprocess.Popen(cmd, cwd=self.fname, stdout=subprocess.PIPE)

        for item in istream_iter(proc.stdout):
            yield item

        proc.wait()
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, cmd)

    def walk_lockstep(self, down_loc, dest_parent):
        if down_loc != self.fname:
            raise ValueError(down_loc, self.fname)
        dest_loc = os.path.join(dest_parent, unix_basename(down_loc))
        for (dirpath, dirnames, filenames) in os.walk(down_loc):
            if dirpath == down_loc:
                d2 = dest_loc
            else:
                d2 = os.path.join(dest_loc, os.path.relpath(dirpath, down_loc))
            # Happens when transitioning from shallow symlinks,
            # maybe we should error out anyway.
            if os.path.lexists(d2):
                if not os.path.isdir(d2):
                    LOGGER.warn('%s already exists and isn\'t a directory', d2)
                    # Prevent recursion
                    dirnames[:] = []
                    continue
            else:
                os.mkdir(d2)
            for fname in filenames:
                src = os.path.join(dirpath, fname)
                dest = os.path.join(d2, fname)
                yield src, dest


class Archive(Release):
    def iter_names_and_sizes(self):
        # unrar l -v could also work, but it's nonsensical to parse
        # some begin/end sections, some uniq
        # pypi:rarfile isn't packaged
        cmd = [ '7z', 'l', '--', self.fname, ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        inside = False

        for line in proc.stdout:
            match = SEVEN_BORDER_RE.match(line)
            if match:
                if inside:
                    break
                else:
                    s0, s1 = match.span(1)
                    n0, n1 = match.span(2)
                    inside = True
            elif inside:
                yield line[n0:-1], line[s0:s1]

        proc.wait()
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, cmd)


def classify(release):
    size_max = -1
    ext_size_max = -1
    total_size = 0
    # Keys are either empty or start with a dot.
    size_by_ext = defaultdict(int)
    item_count_by_ext = defaultdict(int)
    size_of_dir = defaultdict(int)
    common_prefix = None
    for (fname, size) in release.iter_names_and_sizes():
        if common_prefix is not None:
            common_prefix = os.path.commonprefix((common_prefix, fname))
        else:
            common_prefix = fname
        size = int(size)
        total_size += size
        if size > size_max:
            size_max = size
            size_max_item = fname

        dirname, basename = os.path.split(fname)
        if not basename:
            # fname is empty or ends with a slash.
            raise ValueError(fname)

        noext, ext = os.path.splitext(basename)
        if ext[1:] in TAR_EXTS and noext.endswith('.tar'):
            noext, _ = os.path.splitext(noext)
            ext = '.tar' + ext
        elif RAR_EXT_RE.match(ext):
            ext = '.rar'
        item_count_by_ext[ext] += 1
        ext_size = size_by_ext[ext] + size
        size_by_ext[ext] = ext_size
        if ext_size > ext_size_max:
            ext_size_max = ext_size
            ext_size_max_item = ext

        size_of_dir[dirname] += size

    item_count_by_ext = dict(item_count_by_ext)
    size_by_ext = dict(size_by_ext)

    if size_max == -1: # No lines
        return MT.Empty

    largest_dir = max(size_of_dir, key=lambda d: size_of_dir[d])
    largest_dir_rel_weight = float(size_of_dir[largest_dir]) / total_size

    del (basename,
        dirname, ext, noext, size, ext_size, fname )
    # ugly output
    #LOGGER.debug(yaml.dump(locals()))

    if not ext_size_max_item:
        LOGGER.warn('The bulk of the release has no file extension.')
        # The empty ext dominates
        return MT.Unknown

    ext_of_bulk = ext_size_max_item[1:].lower()
    count_of_bulk_by_ext = item_count_by_ext[ext_size_max_item]

    LOGGER.info(
            'Extension %s, with %d file(s), accounts for %.1f%% of total size',
            ext_of_bulk, count_of_bulk_by_ext,
            100. * ext_size_max / total_size)

    release_tokens = set()
    release_tokens.update(TERM_SEP_RE.split(common_prefix.lower()))
    if release.name:
        release_tokens.update(TERM_SEP_RE.split(release.name.lower()))
    LOGGER.debug('Tokens searched for hints: %s', ' '.join(release_tokens))

    if ext_of_bulk in MUSIC_EXTS:
        if largest_dir_rel_weight > .7:
            return MT.Album
        else:
            return MT.Discography
    elif ext_of_bulk in COMICBOOK_EXTS:
        return MT.Comics
    elif ext_of_bulk in EBOOK_EXTS:
        return MT.EBook
    elif ext_of_bulk in FONT_EXTS:
        return MT.Font
    elif ext_of_bulk in ISO_EXTS \
            or (ext_of_bulk == 'bin' \
                    and item_count_by_ext['.cue'] == item_count_by_ext['.bin']):
        platform_hints = intersect_keepcase(GAME_PLATFORMS, release_tokens)
        if len(platform_hints) == 1:
            return MT.Media.registry[platform_hints.pop()]
        return MT.Iso
    elif ext_of_bulk in VID_EXTS:
        series_hints = SERIES_HINTS.intersection(release_tokens)
        movie_hints = MOVIE_HINTS.intersection(release_tokens)
        if len([hint for hint in (series_hints, movie_hints) if hint]) != 1:
            if count_of_bulk_by_ext > 3:
                return MT.Series
            else:
                return MT.Movie
        elif movie_hints:
            return MT.Movie
        elif series_hints:
            return MT.Series
        else:
            assert False
    elif ext_of_bulk in ARCHIVE_EXTS:
        # We don't know what the archive contains.
        # This design works on file names.
        return MT.Archive
    elif ext_of_bulk in AMBIGUOUS_EXTS:
        # No way to guess
        return MT.Unknown
    else:
        # Invite to submit a bug report?
        LOGGER.warn(
            'Extension %s wasn\'t recognized',
            ext_of_bulk)
        LOGGER.info(
            'Report a bug if you think it should be')
        return MT.Unknown

