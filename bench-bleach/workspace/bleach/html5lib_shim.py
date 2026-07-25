"""html5lib shim providing filter base class and entity conversion."""

import html5lib
from html5lib.filters.base import Filter
from html5lib.serializer import HTMLSerializer
from html5lib.constants import DataLossWarning
from html5lib.treebuilders import getTreeBuilder


class BleachHTMLSerializer(HTMLSerializer):
    """A serializer that handles entity conversion."""
    pass


def convert_entities(text):
    """Convert HTML entities to their unicode characters.

    Uses html5lib to parse the text as an HTML fragment, which resolves
    all HTML entities (named and numeric) into their unicode equivalents.
    Then walks the resulting tree and concatenates the text content.

    Args:
        text: A string potentially containing HTML entities.

    Returns:
        A string with all HTML entities converted to unicode.
    """
    parser = html5lib.HTMLParser(tree=getTreeBuilder('dom'))
    doc = parser.parseFragment(text)

    walker = html5lib.getTreeWalker('dom')
    result = []
    for token in walker(doc):
        if token['type'] in ('Characters', 'SpaceCharacters'):
            result.append(token['data'])
    return ''.join(result)
