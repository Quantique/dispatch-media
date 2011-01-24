
# Tools for organizing downloaded media

Two utilities are provided: dispatch-media and classify-releases.

`classify-releases` tells what kind of files an archive, a torrent, or a
directory refers to.

    Usage:
        classify-releases [--auto]    (directory|torrent|archive)…
        classify-releases  --dirs     directory…
        classify-releases  --torrents release.torrent…
        classify-releases  --archives archive.rar…


`dispatch-media` runs configurable actions on downloaded archives
and torrents. It extracts archives and links torrented files to
a content-appropriate location. It uses the same algorithm as
classify-releases to decide where files should be dispatched.

The source and target layout are described in a YAML configuration file.
An example configuration is provided; edit it and put it in `~/.config`.

    Usage:
        dispatch-media [options]
    Options:
        -v, --verbose    Increase verbosity
        --config=CONFIG  Load configuration from CONFIG instead of
                         ~/.config/dispatch-media.conf


## Dependencies

On Debian/Ubuntu, requirements can be installed with:

    sudo aptitude install python-libtorrent python-yaml rsync dtrx p7zip-rar unrar

## Installation

No installation is required.
Both programs can be symlinked to `~∕bin` for convenience.

