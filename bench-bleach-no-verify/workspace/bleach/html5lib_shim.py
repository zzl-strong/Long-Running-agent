"""Shim module for Bleach's interaction with vendored html5lib.

Provides the Filter class (subclassing html5lib's Filter) and the
convert_entities function.
"""

from bleach._vendor.html5lib.constants import (
    namedCharacters,
    tokenTypes,
    voidElements,
)
from bleach._vendor.html5lib.filters.base import Filter as BaseFilter
from bleach._vendor.html5lib.html5parser import HTMLParser
from bleach._vendor.html5lib.serializer import HTMLSerializer
from bleach._vendor.html5lib.treewalkers.base import TreeWalker


class Filter(BaseFilter):
    """A Filter subclass compatible with bleach's token processing pipeline.

    This wraps the vendored html5lib Filter base class.
    """

    def __init__(self, source):
        super().__init__(source)


def convert_entities(text):
    """Convert HTML entities in text to their Unicode equivalents.

    Uses the html5lib tokenizer to parse the text as HTML,
    then serializes it back. The serializer re-escapes &, <, >
    so that essential HTML entities round-trip while others
    get converted to Unicode.

    Args:
        text: A string potentially containing HTML entities.

    Returns:
        A string with non-essential HTML entities converted to
        Unicode characters.
    """
    if not text:
        return text

    # Parse text as an HTML fragment - the tokenizer resolves entities
    parser = HTMLParser()
    tokens = parser.parseFragment(text)

    # Serialize back to HTML - this re-escapes &, <, >
    # but leaves other Unicode characters as-is
    serializer = HTMLSerializer()
    walker = TreeWalker(tokens)
    result = serializer.serialize(walker)
    return result
