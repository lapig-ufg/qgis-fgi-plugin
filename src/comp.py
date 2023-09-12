import os
import sys


PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3

if PY2:
    import urlparse
    from urllib2 import urlopen, URLError
else:
    from urllib import parse
    urlparse = parse
    from urllib.request import urlopen, URLError

if PY3:
    import configparser
else:
    import ConfigParser as configparser


def get_file_dir(filename):
    if PY2:
        return os.path.dirname(filename).decode(sys.getfilesystemencoding())
    else:
        return os.path.dirname(filename)