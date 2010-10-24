# Copyright 2010 Quantique. Licence: GPL3+

# Figure out a better name
from bb2008_torrents import read_torrent

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
VID_EXTS = defset('avi mkv mpg mov ogm m4v mp4 m2ts vob rmvb wmv')

FONT_EXTS = defset('otf ttf')
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

def unix_basename(path):
    # The python version returns an empty basename if the path ends in a slash
    di, ba = os.path.split(path)
    if ba:
        return ba
    else:
        return os.path.basename(di)

def torrent_files_iter(fname):
    dct = read_torrent(fname)
    base = dct['info']['name']
    if 'files' in dct['info']: # multi
        for finfo in dct['info']['files']:
            path = os.path.join(base, *finfo['path'])
            length = finfo['length']
            yield path, length
    else:
        path = base
        length = dct['info']['length']
        yield path, length

def istream_iter(istream):
    for line in istream:
        size, fname = LINE_RE.match(line).groups()
        yield fname, size

def find_iter(directory):
    cmd = [ 'find', '-type', 'f', '-printf', '%s %p\n', ]
    proc = subprocess.Popen(cmd, cwd=directory, stdout=subprocess.PIPE)

    for item in istream_iter(proc.stdout):
        yield item

    proc.wait()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

def seven_iter(fname):
    # unrar l -v could also work, but it's nonsensical to parse
    # some begin/end sections, some uniq
    # pypi:rarfile isn't packaged
    cmd = [ '7z', 'l', '--', fname, ]
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


def classify(it, name):
    size_max = -1
    ext_size_max = -1
    total_size = 0
    # Keys are either empty or start with a dot.
    size_by_ext = defaultdict(int)
    item_count_by_ext = defaultdict(int)
    common_prefix = None
    for (fname, size) in it:
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

    item_count_by_ext = dict(item_count_by_ext)
    size_by_ext = dict(size_by_ext)

    if size_max == -1: # No lines
        return 'Empty'

    del (it, basename,
        dirname, ext, noext, size, ext_size, fname )
    # ugly output
    #LOGGER.debug(yaml.dump(locals()))

    if not ext_size_max_item:
        # The empty ext dominates
        return 'Unknown'

    ext_of_bulk = ext_size_max_item[1:].lower()
    count_of_bulk_by_ext = item_count_by_ext[ext_size_max_item]

    LOGGER.info(
            'Extension %s, with %d file(s), accounts for %.1f%% of total size',
            ext_of_bulk, count_of_bulk_by_ext,
            100. * ext_size_max / total_size)

    release_tokens = set()
    release_tokens.update(TERM_SEP_RE.split(common_prefix.lower()))
    if name:
        release_tokens.update(TERM_SEP_RE.split(name.lower()))
    LOGGER.debug('Tokens searched for hints: %s', ' '.join(release_tokens))

    if ext_of_bulk in MUSIC_EXTS:
        if count_of_bulk_by_ext > 20:
            return 'Discography'
        else:
            return 'Album'
    elif ext_of_bulk in COMICBOOK_EXTS:
        return 'Comics'
    elif ext_of_bulk in EBOOK_EXTS:
        return 'EBook'
    elif ext_of_bulk in FONT_EXTS:
        return 'Font'
    elif ext_of_bulk in ISO_EXTS \
            or (ext_of_bulk == 'bin' \
                    and item_count_by_ext['.cue'] == item_count_by_ext['.bin']):
        platform_hints = intersect_keepcase(GAME_PLATFORMS, release_tokens)
        if len(platform_hints) == 1:
            return platform_hints.pop()
        return 'Iso'
    elif ext_of_bulk in VID_EXTS:
        series_hints = SERIES_HINTS.intersection(release_tokens)
        movie_hints = MOVIE_HINTS.intersection(release_tokens)
        if len([hint for hint in (series_hints, movie_hints) if hint]) != 1:
            if count_of_bulk_by_ext > 3:
                return 'Series'
            else:
                return 'Movie'
        elif movie_hints:
            return 'Movie'
        elif series_hints:
            return 'Series'
        else:
            assert False
    elif ext_of_bulk in ARCHIVE_EXTS:
        # We don't know what the archive contains.
        # This design works on file names.
        return 'Unknown'
    elif ext_of_bulk in AMBIGUOUS_EXTS:
        # No way to guess
        return 'Unknown'
    else:
        # Invite to submit a bug report?
        LOGGER.warn(
            'Extension %s wasn\'t recognized',
            ext_of_bulk)
        LOGGER.info(
            'Report a bug if you think it should be')
        return 'Unknown'


