class Constants:
    def __getattr__(self, name):
        return getattr(self.__class__, name)
    def __setattr__(self, name, value):
        raise AttributeError("cannot set constant <%s>" % name)
