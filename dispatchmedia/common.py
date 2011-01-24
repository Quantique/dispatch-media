
import errno
import os
import os.path
import stat
import time

def iso8601_now():
    # http://www.aczoom.com/blog/ac/2007-02-24/strftime-in-python
    lt = time.localtime()
    if lt.tm_isdst > 0 and time.daylight:
        tz = time.tzname[1]
        utc_offset_minutes = - int(time.altzone/60)
    else:
        tz = time.tzname[0]
        utc_offset_minutes = - int(time.timezone/60)
    utc_offset_str = "%+03d%02d" % (utc_offset_minutes/60.0,
            utc_offset_minutes % 60)
    return time.strftime("%Y-%m-%dT%H:%M:%S", lt) + utc_offset_str

def unix_basename(path):
    # The python version returns an empty basename if the path ends in a slash
    di, ba = os.path.split(path)
    if ba:
        return ba
    else:
        return os.path.basename(di)

def ensure_dir(path, allow_link=True):
    # Make sure a directory exists
    try:
        os.mkdir(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise
        if allow_link: # A symlink to an existing directory is permitted
            try:
                st = os.stat(path)
            except OSError, e2:
                # Broken symlink, most likely
                raise e
        else:
            st = os.lstat(path)
        if not stat.S_ISDIR(st.st_mode):
            raise


