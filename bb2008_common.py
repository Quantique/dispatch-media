
import subprocess
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

