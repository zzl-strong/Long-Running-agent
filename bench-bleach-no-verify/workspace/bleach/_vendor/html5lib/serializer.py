"""HTML serializer that converts token streams back to HTML strings."""

import re

from bleach._vendor.html5lib.constants import voidElements


class HTMLSerializer:
    """Serialize a token stream back into an HTML string."""

    def __init__(self, **kwargs):
        self.omit_optional_tags = kwargs.get('omit_optional_tags', False)
        self.sanitize = kwargs.get('sanitize', False)
        self.sanitize_fn = kwargs.get('sanitize_fn', None)

    def serialize(self, treewalker, encoding=None):
        """Serialize a token stream to an HTML string.

        Args:
            treewalker: An iterable of token dicts.
            encoding: Ignored (for compatibility).

        Returns:
            An HTML string.
        """
        parts = []
        for token in treewalker:
            token_type = token.get('type', '')
            if token_type in ('StartTag', 'EmptyTag'):
                parts.append(self._serialize_start_tag(token))
            elif token_type == 'EndTag':
                parts.append(self._serialize_end_tag(token))
            elif token_type in ('Characters', 'SpaceCharacters'):
                parts.append(self._escape_text(token.get('data', '')))
            elif token_type == 'Comment':
                parts.append('<!--%s-->' % token.get('data', ''))
            else:
                parts.append(token.get('data', ''))
        return ''.join(parts)

    def _serialize_start_tag(self, token):
        """Serialize a start or empty tag."""
        name = token.get('name', '')
        data = token.get('data', {})
        token_type = token.get('type', '')

        parts = ['<', name]

        for attr_name, attr_value in sorted(data.items()):
            if attr_value is None:
                parts.append(' %s' % attr_name)
            elif '"' in str(attr_value):
                parts.append(" %s='%s'" % (attr_name, str(attr_value)))
            else:
                parts.append(' %s="%s"' % (attr_name, str(attr_value)))

        if token_type == 'EmptyTag':
            parts.append(' />')
        else:
            parts.append('>')

        return ''.join(parts)

    def _serialize_end_tag(self, token):
        """Serialize an end tag."""
        name = token.get('name', '')
        return '</%s>' % name

    def _escape_text(self, text):
        """Escape text for HTML."""
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text

    def render(self, treewalker, encoding=None):
        """Alias for serialize."""
        return self.serialize(treewalker, encoding=encoding)
