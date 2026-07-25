"""Bleach is an HTML sanitizing library that escapes or strips markup and
performs linkification.

Basic usage::

    >>> import bleach
    >>> bleach.clean('an <script>evil()</script> example')
    'an &lt;script&gt;evil()&lt;/script&gt; example'
    >>> bleach.linkify('a http://example.com link')
    'a <a href="http://example.com" rel="nofollow">http://example.com</a> link'

"""

from bleach.sanitizer import (
    ALLOWED_ATTRIBUTES,
    ALLOWED_PROTOCOLS,
    ALLOWED_TAGS,
    Cleaner,
    clean,
)
from bleach.linkifier import Linker, linkify
from bleach.css_sanitizer import CSSSanitizer
from bleach.callbacks import DEFAULT_CALLBACKS, nofollow, target_blank

#: Library version
__version__ = '3.3.0'

__all__ = [
    'clean',
    'linkify',
    'Cleaner',
    'Linker',
    'CSSSanitizer',
    'ALLOWED_TAGS',
    'ALLOWED_ATTRIBUTES',
    'ALLOWED_PROTOCOLS',
    'nofollow',
    'target_blank',
    'DEFAULT_CALLBACKS',
    '__version__',
]
