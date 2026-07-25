"""
Bleach is an HTML sanitizing library that escapes or strips markup and
attributes based on a safelist.
"""

__version__ = '6.2.0'


def clean(text, tags=None, attributes=None, protocols=None,
          strip=False, strip_comments=True, css_sanitizer=None):
    """Clean an HTML fragment and return the cleaned HTML."""
    from bleach.sanitizer import Cleaner
    cleaner = Cleaner(
        tags=tags,
        attributes=attributes,
        protocols=protocols,
        strip=strip,
        strip_comments=strip_comments,
        css_sanitizer=css_sanitizer,
    )
    return cleaner.clean(text)


def linkify(text, callbacks=None, skip_tags=None, parse_email=False):
    """Convert URL-like strings in an HTML fragment to links."""
    from bleach.linkifier import linkify as _linkify
    from bleach.linkifier import DEFAULT_CALLBACKS
    if callbacks is None:
        callbacks = DEFAULT_CALLBACKS
    return _linkify(
        text,
        callbacks=callbacks,
        skip_tags=skip_tags,
        parse_email=parse_email,
    )


# DEFAULT_CALLBACKS is a list of default callback functions
from bleach.linkifier import DEFAULT_CALLBACKS  # noqa: F811

# html5lib_shim module reference
from bleach import html5lib_shim  # noqa
