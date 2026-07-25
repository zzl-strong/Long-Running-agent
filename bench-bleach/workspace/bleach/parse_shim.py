"""Parse shim - wraps urllib.parse for compatibility."""

from urllib.parse import urlparse as _urlparse


class urlparse:
    """A wrapper around urllib.parse.urlparse returning attributes."""

    def __init__(self, url):
        parsed = _urlparse(url)
        self.scheme = parsed.scheme
        self.netloc = parsed.netloc
        self.path = parsed.path
        self.params = parsed.params
        self.query = parsed.query
        self.fragment = parsed.fragment

    def __repr__(self):
        return (f'urlparse(scheme={self.scheme!r}, netloc={self.netloc!r}, '
                f'path={self.path!r}, params={self.params!r}, '
                f'query={self.query!r}, fragment={self.fragment!r})')
