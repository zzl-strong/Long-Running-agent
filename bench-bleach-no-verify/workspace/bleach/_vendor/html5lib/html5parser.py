"""HTML5 tokenizer and parser for the vendored html5lib.

Produces a stream of tokens (dictionaries) compatible with html5lib's token format.
"""

import re
from html.parser import HTMLParser as _HTMLParser

from bleach._vendor.html5lib.constants import tokenTypes, voidElements, spaceCharacters


__all__ = ['HTMLParser', 'HTMLTokenizer']


class HTMLTokenizer:
    """A tokenizer that produces html5lib-compatible tokens from HTML source.

    Uses Python's built-in HTMLParser for robust parsing, converting its
    SAX-style events into html5lib token dictionaries.
    """

    def __init__(self, strict=False):
        self._parser = _HTMLToTokens()
        self._tokens = []
        self._pos = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._pos >= len(self._tokens):
            raise StopIteration
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def tokenize(self, source):
        """Tokenize an HTML source string.

        Returns self for iteration.
        """
        self._tokens = self._parser.parse(source)
        self._pos = 0
        return self

    def normalizeToken(self, token):
        """Normalize a token (no-op for this implementation)."""
        return token


class _HTMLToTokens(_HTMLParser):
    """Internal: converts HTMLParser events to html5lib token dicts."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._tokens = []
        self._current_attrs = {}

    def parse(self, source):
        """Parse HTML source and return a list of token dicts."""
        self._tokens = []
        self.feed(source)
        self.close()
        return self._tokens

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        is_void = tag.lower() in voidElements

        if is_void:
            token_type = 'EmptyTag'
        else:
            token_type = 'StartTag'

        self._tokens.append({
            'type': token_type,
            'name': tag,
            'data': attrs_dict,
        })

    def handle_endtag(self, tag):
        self._tokens.append({
            'type': 'EndTag',
            'name': tag,
            'data': {},
        })

    def handle_data(self, data):
        if not data:
            return

        # Check if it's all whitespace
        if all(c in spaceCharacters for c in data):
            self._tokens.append({
                'type': 'SpaceCharacters',
                'data': data,
            })
        else:
            self._tokens.append({
                'type': 'Characters',
                'data': data,
            })

    def handle_entityref(self, name):
        from bleach._vendor.html5lib.constants import namedCharacters
        char = namedCharacters.get(name + ';', '&' + name + ';')
        self._tokens.append({
            'type': 'Characters',
            'data': char,
        })

    def handle_charref(self, name):
        try:
            if name.startswith('x') or name.startswith('X'):
                codepoint = int(name[1:], 16)
            else:
                codepoint = int(name)
            char = chr(codepoint)
        except (ValueError, OverflowError):
            char = '\ufffd'
        self._tokens.append({
            'type': 'Characters',
            'data': char,
        })

    def handle_comment(self, data):
        self._tokens.append({
            'type': 'Comment',
            'data': data,
        })

    def handle_decl(self, decl):
        # DOCTYPE or other declarations
        pass

    def unknown_decl(self, data):
        pass


class HTMLParser:
    """Main entry point for html5lib HTML parsing.

    Parses HTML source and returns a document tree.
    """

    def __init__(self, tree=None, namespaceHTMLElements=True, strict=False):
        self.tree = tree
        self.namespaceHTMLElements = namespaceHTMLElements
        self.strict = strict

    def parse(self, source, namespaceHTMLElements=None):
        """Parse HTML source, return a list of tokens."""
        tokenizer = HTMLTokenizer(strict=self.strict)
        tokenizer.tokenize(source)
        return list(tokenizer)

    def parseFragment(self, source, container='div', namespaceHTMLElements=None):
        """Parse an HTML fragment, return a list of tokens."""
        return self.parse(source, namespaceHTMLElements=namespaceHTMLElements)
