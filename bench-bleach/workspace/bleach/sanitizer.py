"""HTML sanitizer module for bleach."""

from html5lib import parseFragment
from html5lib import treewalkers
from urllib.parse import urlparse

ALLOWED_TAGS = frozenset({
    'a', 'abbr', 'acronym', 'b', 'blockquote', 'code',
    'em', 'i', 'li', 'ol', 'strong', 'ul',
})

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'abbr': ['title'],
    'acronym': ['title'],
}

ALLOWED_PROTOCOLS = frozenset({'http', 'https', 'mailto'})

ALLOWED_STYLES = []


def _attr_filter(allowed_attrs, protocols, css_sanitizer, token_data):
    """Filter attributes, removing disallowed ones and bad protocols."""
    result = {}
    for attr_name, attr_value in token_data.items():
        if attr_name[0] is not None:
            # Namespaced attribute (non-None prefix) - skip
            continue
        local_name = attr_name[1]
        if local_name in allowed_attrs:
            # Check protocol if this is a URL attribute
            if _is_url_attribute(local_name) and attr_value:
                if not _allowed_protocol(attr_value, protocols):
                    continue
            # Sanitize CSS if needed
            if local_name == 'style' and css_sanitizer:
                attr_value = css_sanitizer.sanitize_css(attr_value)
            result[attr_name] = attr_value
    return result


def _is_url_attribute(attr_name):
    """Check if the attribute is a URL-bearing attribute."""
    return attr_name in {'href', 'src', 'action', 'cite', 'data',
                         'formaction', 'manifest', 'poster', 'profile'}


def _allowed_protocol(value, protocols):
    """Check if the URL value has an allowed protocol."""
    for url in value.split():
        if ':' in url:
            parsed = urlparse(url)
            if parsed.scheme:
                if parsed.scheme not in protocols:
                    return False
    return True


class Cleaner:
    """An HTML sanitizer that cleans HTML fragments.

    Example usage::

        from bleach.sanitizer import Cleaner

        cleaner = Cleaner()
        cleaned = cleaner.clean(html_text)

    """

    def __init__(self, tags=None, attributes=None, protocols=None,
                 strip=False, strip_comments=True, filters=None,
                 css_sanitizer=None):
        self.tags = tags if tags is not None else ALLOWED_TAGS
        self.attributes = attributes if attributes is not None else ALLOWED_ATTRIBUTES
        self.protocols = protocols if protocols is not None else ALLOWED_PROTOCOLS
        self.strip = strip
        self.strip_comments = strip_comments
        self.filters = filters if filters is not None else []
        self.css_sanitizer = css_sanitizer

    def clean(self, text):
        """Clean the given HTML fragment and return the result.

        Args:
            text: An HTML fragment to clean.

        Returns:
            A str containing the cleaned HTML fragment.
        """
        # Parse the HTML fragment into a tree
        tree = parseFragment(text)

        # Walk the tree to get tokens
        walker = treewalkers.getTreeWalker('etree')
        tokens = walker(tree)

        # Filter and serialize tokens
        return self._serialize(tokens)

    def _serialize(self, tokens):
        """Filter tokens and serialize to HTML string."""
        result = []

        # Build the attribute qualifier for each allowed tag
        allowed_attrs = {}
        for tag in self.tags:
            allowed_attrs[tag] = self.attributes.get(tag, [])
        # Also check for wildcard
        if '*' in self.attributes:
            for tag in self.tags:
                allowed_attrs[tag] = allowed_attrs.get(tag, []) + self.attributes['*']

        # Apply any extra filters to the token stream
        for f in self.filters:
            tokens = f(tokens)

        for token in tokens:
            token_type = token['type']

            if token_type == 'StartTag':
                tag_name = token['name']
                if tag_name in self.tags:
                    # Filter attributes
                    filtered_data = _attr_filter(
                        allowed_attrs.get(tag_name, []),
                        self.protocols,
                        self.css_sanitizer,
                        token['data'],
                    )
                    # Build the start tag
                    attr_parts = []
                    for (_, attr_name), attr_value in filtered_data.items():
                        escaped_value = attr_value.replace('&', '&amp;').replace('"', '&quot;')
                        attr_parts.append(' %s="%s"' % (attr_name, escaped_value))
                    result.append('<%s%s>' % (tag_name, ''.join(attr_parts)))
                else:
                    if self.strip:
                        continue  # Skip start tag, children pass through
                    else:
                        result.append('&lt;%s&gt;' % tag_name)

            elif token_type == 'EndTag':
                tag_name = token['name']
                if tag_name in self.tags:
                    result.append('</%s>' % tag_name)
                else:
                    if self.strip:
                        continue
                    else:
                        result.append('&lt;/%s&gt;' % tag_name)

            elif token_type == 'Characters':
                # Escape special characters
                data = token['data']
                data = data.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                result.append(data)

            elif token_type == 'SpaceCharacters':
                result.append(token['data'])

            elif token_type == 'Comment':
                if not self.strip_comments:
                    result.append('<!--%s-->' % token['data'])

            elif token_type == 'EmptyTag':
                tag_name = token['name']
                if tag_name in self.tags:
                    filtered_data = _attr_filter(
                        allowed_attrs.get(tag_name, []),
                        self.protocols,
                        self.css_sanitizer,
                        token['data'],
                    )
                    attr_parts = []
                    for (_, attr_name), attr_value in filtered_data.items():
                        escaped_value = attr_value.replace('&', '&amp;').replace('"', '&quot;')
                        attr_parts.append(' %s="%s"' % (attr_name, escaped_value))
                    result.append('<%s%s />' % (tag_name, ''.join(attr_parts)))
                else:
                    if self.strip:
                        continue
                    else:
                        result.append('&lt;%s /&gt;' % tag_name)

        return ''.join(result)
