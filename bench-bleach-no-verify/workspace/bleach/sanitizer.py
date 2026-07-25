"""Bleach HTML sanitizer.

Provides the clean() function and Cleaner class for sanitizing HTML
by removing or escaping unsafe tags, attributes, and protocols.
"""

import warnings

from bleach._vendor.html5lib.constants import tokenTypes
from bleach.html5lib_shim import Filter


#: Default set of allowed HTML tags
ALLOWED_TAGS = frozenset((
    'a', 'abbr', 'acronym', 'b', 'blockquote', 'br', 'code',
    'em', 'i', 'li', 'ol', 'p', 'strong', 'ul',
))

#: Default allowed attributes per tag
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'abbr': ['title'],
    'acronym': ['title'],
}

#: Default allowed URL protocols
ALLOWED_PROTOCOLS = frozenset(('http', 'https', 'mailto', 'ftp'))


class NoCssSanitizerWarning(UserWarning):
    """Warning issued when CSS sanitization is requested but no
    CSS sanitizer is available."""
    pass


class BleachSanitizerFilter(Filter):
    """Token stream filter that sanitizes HTML tokens.

    Removes tokens for disallowed tags, strips disallowed attributes,
    and validates URL protocols on allowed attributes.
    """

    def __init__(self, source, tags=None, attributes=None, protocols=None,
                 strip=False, strip_comments=True, css_sanitizer=None):
        super().__init__(source)
        self.tags = tags if tags is not None else ALLOWED_TAGS
        self.attributes = attributes if attributes is not None else ALLOWED_ATTRIBUTES
        self.protocols = protocols if protocols is not None else ALLOWED_PROTOCOLS
        self.strip = strip
        self.strip_comments = strip_comments
        self.css_sanitizer = css_sanitizer

    def __iter__(self):
        for token in self.source:
            token_type = token.get('type', '')
            name = token.get('name', '')

            if token_type in ('StartTag', 'EndTag', 'EmptyTag'):
                if name not in self.tags:
                    if not self.strip:
                        # Emit raw tag as text — the serializer will
                        # escape < and > to &lt; and &gt;
                        if token_type == 'EndTag':
                            yield {'type': 'Characters',
                                   'data': '</%s>' % name}
                        elif token_type == 'EmptyTag':
                            yield {'type': 'Characters',
                                   'data': '<%s/>' % name}
                        else:
                            yield {'type': 'Characters',
                                   'data': '<%s>' % name}
                    # If strip=True, just skip the token
                    continue

                # Filter attributes for allowed tags
                if token_type in ('StartTag', 'EmptyTag'):
                    token = self._sanitize_attributes(token)

            elif token_type == 'Comment':
                if self.strip_comments:
                    continue

            yield token

    def _sanitize_attributes(self, token):
        """Remove disallowed attributes and validate URL protocols."""
        name = token.get('name', '')
        attrs = token.get('data', {})

        allowed_attrs = self.attributes.get(name, [])
        # Also check wildcard attribute ('*' key means all tags)
        allowed_attrs = allowed_attrs + self.attributes.get('*', [])

        sanitized_attrs = {}
        for attr_name, attr_value in attrs.items():
            if attr_name not in allowed_attrs:
                continue
            # Validate URL protocols for href/src attributes
            if attr_name in ('href', 'src', 'action', 'cite', 'data', 'formaction'):
                if not self._is_allowed_protocol(attr_value):
                    continue
            # Sanitize CSS in style attributes
            if attr_name == 'style' and self.css_sanitizer is not None:
                attr_value = self.css_sanitizer.sanitize_css(attr_value)
                if not attr_value:
                    continue
            sanitized_attrs[attr_name] = attr_value

        return {
            'type': token['type'],
            'name': token['name'],
            'data': sanitized_attrs,
        }

    def _is_allowed_protocol(self, value):
        """Check if a URL value uses an allowed protocol."""
        if not value:
            return True
        # Find the protocol
        if ':' not in value:
            return True  # Relative URL
        protocol = value.split(':', 1)[0].lower().strip()
        # Handle protocol-relative URLs
        if protocol == '':
            return True
        return protocol in self.protocols


class Cleaner:
    """Configurable HTML sanitizer.

    Can be configured with custom tags, attributes, protocols,
    and other options to control sanitization behavior.
    """

    def __init__(self, tags=None, attributes=None, protocols=None,
                 strip=False, strip_comments=True, filters=None,
                 css_sanitizer=None):
        self.tags = tags if tags is not None else ALLOWED_TAGS
        self.attributes = attributes if attributes is not None else ALLOWED_ATTRIBUTES
        self.protocols = protocols if protocols is not None else ALLOWED_PROTOCOLS
        self.strip = strip
        self.strip_comments = strip_comments
        self.filters = filters or []
        self.css_sanitizer = css_sanitizer

        # Check if style attribute is allowed but no CSS sanitizer
        if self.css_sanitizer is None:
            for attr_list in self.attributes.values():
                if 'style' in attr_list:
                    warnings.warn(
                        "No css_sanitizer provided but style attribute is "
                        "in allowed attributes. Style attributes will be "
                        "passed through unsanitized.",
                        NoCssSanitizerWarning,
                        stacklevel=2,
                    )
                    break

    def clean(self, text):
        """Sanitize an HTML string.

        Args:
            text: HTML string to sanitize.

        Returns:
            Sanitized HTML string.
        """
        from bleach._vendor.html5lib.html5parser import HTMLParser
        from bleach._vendor.html5lib.serializer import HTMLSerializer
        from bleach._vendor.html5lib.treewalkers.base import TreeWalker

        if not text:
            return text

        # Parse HTML into tokens
        parser = HTMLParser()
        tokens = parser.parseFragment(text)

        # Apply sanitization filter
        sanitizer = BleachSanitizerFilter(
            iter(tokens),
            tags=self.tags,
            attributes=self.attributes,
            protocols=self.protocols,
            strip=self.strip,
            strip_comments=self.strip_comments,
            css_sanitizer=self.css_sanitizer,
        )

        # Apply additional user filters
        filtered_tokens = sanitizer
        for filt in self.filters:
            filtered_tokens = filt(filtered_tokens)

        # Serialize back to HTML
        serializer = HTMLSerializer()
        walker = TreeWalker(list(filtered_tokens))
        result = serializer.serialize(walker)

        # Convert entities
        from bleach.html5lib_shim import convert_entities
        result = convert_entities(result)

        return result


def clean(text, tags=None, attributes=None, protocols=None,
          strip=False, strip_comments=True, filters=None,
          css_sanitizer=None):
    """Sanitize an HTML string.

    Convenience function that creates a Cleaner and calls clean().

    Args:
        text: HTML string to sanitize.
        tags: Set of allowed tags (uses ALLOWED_TAGS by default).
        attributes: Dict mapping tags to allowed attributes.
        protocols: Set of allowed URL protocols.
        strip: If True, strip disallowed tags; if False, escape them.
        strip_comments: If True, remove HTML comments.
        filters: Optional list of additional filters to apply.
        css_sanitizer: Optional CSS sanitizer instance.

    Returns:
        Sanitized HTML string.
    """
    cleaner = Cleaner(
        tags=tags,
        attributes=attributes,
        protocols=protocols,
        strip=strip,
        strip_comments=strip_comments,
        filters=filters,
        css_sanitizer=css_sanitizer,
    )
    return cleaner.clean(text)
