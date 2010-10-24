# Copyright 2010 Quantique. Licence: GPL3+


class AutoName(object):
    @classmethod
    def name(cls, plural=False, lower=False):
        r = cls.__name__
        if lower:
            r = r.lower()
        if plural:
            if r[-1] == 'y':
                return r[:-1] + 'ies'
            elif r[-1] == 's':
                return r
            else:
                return r + 's'
        else:
            return r

class AlwaysSingular(AutoName):
    @classmethod
    def name(cls, plural=False, *args, **kargs):
        return super(AlwaysSingular, cls).name(*args, **kargs)

class Media(AutoName):
    registry = None
    class __metaclass__(type):
        def __init__(cls, name, bases, attrs):
            type.__init__(cls, name, bases, attrs)
            if cls.registry is None:
                cls.registry = {}
            else:
                cls.registry[name] = cls
                cls.registry[cls.name(lower=True)] = cls
                cls.registry[cls.name(plural=True)] = cls
                cls.registry[cls.name(plural=True, lower=True)] = cls


class Album(Media): pass
class Comics(Media): pass
class Discography(Media): pass
class EBook(Media):
    @classmethod
    def name(cls, lower=False, plural=False):
        # CamelCase magic
        if lower:
            if plural:
                return 'e-books'
            else:
                return 'e-book'
        else:
            if plural:
                return cls.__name__ + 's'
            else:
                return cls.__name__
class Font(Media): pass
class Iso(AlwaysSingular, Media): pass
class Movie(Media): pass
class PC(AlwaysSingular, Media): pass
class PS2(AlwaysSingular, Media): pass
class PS3(AlwaysSingular, Media): pass
class Series(Media): pass
class Wii(AlwaysSingular, Media): pass
class Xbox(AlwaysSingular, Media): pass


