"""Shim module for URL parsing compatibility.

Provides a urlparse function compatible with the spec's requirements,
wrapping Python's urllib.parse with query string behavior that includes
the leading '?' in the query attribute (matching Python 2 urlparse behavior).
"""

try:
    from urllib.parse import urlparse as _stdlib_urlparse
except ImportError:
    from urlparse import urlparse as _stdlib_urlparse


def urlparse(url):
    """Parse a URL into components.

    Returns an object with urlparse-compatible attributes.
    The query attribute includes the leading '?' character
    (matching legacy urlparse behavior).

    Args:
        url: A URL string to parse.

    Returns:
        A ParseResult-like object with attributes: scheme, netloc,
        path, params, query, fragment.

    Examples:
        >>> p = urlparse('http://example.com/path?q=1')
        >>> p.scheme
        'http'
        >>> p.netloc
        'example.com'
        >>> p.path
        '/path'
        >>> p.query
        '?q=1'
        >>> p.fragment
        ''
    """
    result = _stdlib_urlparse(url)

    # Python 3's urlparse strips the leading '?' from query.
    # Restore it to match legacy (Python 2) behavior expected by bleach.
    if result.query:
        result = result._replace(query='?' + result.query)

    return result
