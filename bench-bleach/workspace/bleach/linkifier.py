"""Linkifier module - converts URLs to links."""

import re

from html5lib import parseFragment
from html5lib import treewalkers

from bleach.callbacks import nofollow as _nofollow

DEFAULT_CALLBACKS = [_nofollow]

# URL regex patterns
url_re = re.compile(
    r'''(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»""'']))'''
)

email_re = re.compile(
    r'''(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b'''
)


def build_url_re(tlds=None):
    """Build a URL-matching regex with optional custom TLDs."""
    if tlds is None:
        return url_re
    tld_pattern = '|'.join(sorted(re.escape(tld) for tld in tlds))
    return re.compile(
        r'''(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.](?:'''
        + tld_pattern
        + r''')(?::\d+)?/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»""'']))'''
    )


def linkify(text, callbacks=DEFAULT_CALLBACKS, skip_tags=None, parse_email=False):
    """Convert URL-like strings in an HTML fragment to links.

    This is the module-level convenience function. It creates a Linker
    internally and calls its linkify method.
    """
    linker = Linker(
        callbacks=callbacks,
        skip_tags=skip_tags,
        parse_email=parse_email,
    )
    return linker.linkify(text)


class Linker:
    """Convert URL-like strings in HTML to links."""

    def __init__(self, callbacks=None, skip_tags=None, parse_email=False,
                 url_re=url_re, email_re=email_re, recognized_tags=None):
        self.callbacks = callbacks if callbacks is not None else []
        self.skip_tags = skip_tags if skip_tags is not None else {'pre', 'code'}
        self.parse_email = parse_email
        self.url_re = url_re
        self.email_re = email_re
        self.recognized_tags = recognized_tags if recognized_tags is not None else set()

    def linkify(self, text):
        """Convert URLs in text to links and return the result."""
        tree = parseFragment(text)
        walker = treewalkers.getTreeWalker('etree')
        tokens = walker(tree)

        linkify_filter = LinkifyFilter(
            tokens,
            callbacks=self.callbacks,
            skip_tags=self.skip_tags,
            parse_email=self.parse_email,
            url_re=self.url_re,
            email_re=self.email_re,
        )

        return _serialize(linkify_filter)


class LinkifyFilter:
    """An html5lib filter that converts URLs to links during tree traversal."""

    def __init__(self, source, callbacks=None, skip_tags=None,
                 parse_email=False, url_re=url_re, email_re=email_re):
        self.source = source
        self.callbacks = callbacks if callbacks is not None else []
        self.skip_tags = skip_tags if skip_tags is not None else {'pre', 'code'}
        self.parse_email = parse_email
        self.url_re = url_re
        self.email_re = email_re
        self._skip_tag_depth = 0

    def __iter__(self):
        for token in self.source:
            token_type = token['type']

            # Track nesting depth for skip_tags
            if token_type == 'StartTag':
                if token['name'] in self.skip_tags:
                    self._skip_tag_depth += 1
                yield token
                continue

            if token_type == 'EndTag':
                if token['name'] in self.skip_tags and self._skip_tag_depth > 0:
                    self._skip_tag_depth -= 1
                yield token
                continue

            # For text tokens, search for URLs and emit linkified tokens
            if token_type == 'Characters' and self._skip_tag_depth == 0:
                yield from self._linkify_text(token['data'])
            else:
                yield token

    def _linkify_text(self, text):
        """Split text by URL matches and yield tokens for each segment."""
        # Build combined regex for URLs and optionally emails
        patterns = [('url', self.url_re)]
        if self.parse_email:
            patterns.append(('email', self.email_re))

        # Find all matches
        matches = []
        for pattern_type, pattern in patterns:
            for m in pattern.finditer(text):
                matches.append((m.start(), m.end(), m.group(0), pattern_type))

        if not matches:
            # No matches - just emit the text as-is
            yield {'type': 'Characters', 'data': text}
            return

        # Sort matches by position; handle overlaps by preferring first
        matches.sort(key=lambda x: x[0])

        # Build non-overlapping match list
        final_matches = []
        last_end = 0
        for start, end, url, ptype in matches:
            if start >= last_end:
                final_matches.append((start, end, url, ptype))
                last_end = end

        # Emit tokens
        pos = 0
        for start, end, url, ptype in final_matches:
            # Text before this match
            if pos < start:
                yield {'type': 'Characters', 'data': text[pos:start]}

            # Build the link token(s)
            if ptype == 'email':
                href = 'mailto:' + url
            else:
                href = url
                if not ('://' in href or href.startswith('mailto:')):
                    href = 'http://' + href

            # Build attributes
            attrs = {(None, 'href'): href}
            for callback in self.callbacks:
                attrs = callback(attrs, new=False)
                if attrs is None:
                    break

            if attrs is not None:
                # Emit start tag
                yield {'type': 'StartTag', 'name': 'a', 'data': dict(attrs)}

                # Emit the URL as text
                yield {'type': 'Characters', 'data': url}

                # Emit end tag
                yield {'type': 'EndTag', 'name': 'a'}
            else:
                # Callback returned None — emit URL as plain text (no link)
                yield {'type': 'Characters', 'data': url}

            pos = end

        # Text after the last match
        if pos < len(text):
            yield {'type': 'Characters', 'data': text[pos:]}


def _serialize(tokens):
    """Serialize a token stream into an HTML string."""
    result = []

    for token in tokens:
        token_type = token['type']

        if token_type == 'StartTag':
            tag_name = token['name']
            attr_parts = []
            for (_, attr_name), attr_value in token.get('data', {}).items():
                escaped_value = attr_value.replace('&', '&amp;').replace('"', '&quot;')
                attr_parts.append(' %s="%s"' % (attr_name, escaped_value))
            result.append('<%s%s>' % (tag_name, ''.join(attr_parts)))

        elif token_type == 'EndTag':
            result.append('</%s>' % token['name'])

        elif token_type == 'EmptyTag':
            tag_name = token['name']
            attr_parts = []
            for (_, attr_name), attr_value in token.get('data', {}).items():
                escaped_value = attr_value.replace('&', '&amp;').replace('"', '&quot;')
                attr_parts.append(' %s="%s"' % (attr_name, escaped_value))
            result.append('<%s%s />' % (tag_name, ''.join(attr_parts)))

        elif token_type == 'Characters':
            data = token['data']
            data = data.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            result.append(data)

        elif token_type == 'SpaceCharacters':
            result.append(token['data'])

        elif token_type == 'Comment':
            result.append('<!--%s-->' % token['data'])

    return ''.join(result)
