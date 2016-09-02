from bgpfu.output import Output
from bgpfu.client import IRRClient


class BGPFu(object):
    def __init__(self, host='whois.radb.net'):
        self._client = IRRClient()
        self._output = Output()

    @property
    def client(self):
        return self._client

    @property
    def output(self):
        return self._output

    def prefixlist(self, obj, proto=4, aggregate=True):
        with self.client as c:
            prefixes = c.prefixlist(obj, proto=proto)
            if aggregate:
                prefixes = prefixes.aggregate()
        return prefixes

    def as_set(self, obj):
        with self.client as c:
            autnums = c.get_set(obj)
        return autnums
