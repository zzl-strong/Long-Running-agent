"""Bleach CSS sanitizer.

Provides the CSSSanitizer class for sanitizing inline CSS.
Uses tinycss2 to parse and filter CSS declarations, removing
dangerous properties and URL values.
"""

import tinycss2


#: Default allowed CSS properties
ALLOWED_CSS_PROPERTIES = frozenset((
    'background',
    'background-color',
    'background-image',
    'background-position',
    'background-repeat',
    'background-size',
    'border',
    'border-bottom',
    'border-bottom-color',
    'border-bottom-left-radius',
    'border-bottom-right-radius',
    'border-bottom-style',
    'border-bottom-width',
    'border-collapse',
    'border-color',
    'border-image',
    'border-left',
    'border-left-color',
    'border-left-style',
    'border-left-width',
    'border-radius',
    'border-right',
    'border-right-color',
    'border-right-style',
    'border-right-width',
    'border-spacing',
    'border-style',
    'border-top',
    'border-top-color',
    'border-top-left-radius',
    'border-top-right-radius',
    'border-top-style',
    'border-top-width',
    'border-width',
    'bottom',
    'clear',
    'color',
    'cursor',
    'direction',
    'display',
    'float',
    'font',
    'font-family',
    'font-size',
    'font-style',
    'font-weight',
    'height',
    'left',
    'letter-spacing',
    'line-height',
    'list-style',
    'list-style-type',
    'margin',
    'margin-bottom',
    'margin-left',
    'margin-right',
    'margin-top',
    'max-height',
    'max-width',
    'min-height',
    'min-width',
    'opacity',
    'overflow',
    'padding',
    'padding-bottom',
    'padding-left',
    'padding-right',
    'padding-top',
    'position',
    'right',
    'table-layout',
    'text-align',
    'text-decoration',
    'text-indent',
    'text-transform',
    'top',
    'vertical-align',
    'visibility',
    'white-space',
    'width',
    'word-spacing',
    'z-index',
))

#: Default allowed SVG CSS properties
ALLOWED_SVG_PROPERTIES = frozenset((
    'clip-path',
    'clip-rule',
    'color-interpolation',
    'color-interpolation-filters',
    'color-profile',
    'color-rendering',
    'fill',
    'fill-opacity',
    'fill-rule',
    'filter',
    'flood-color',
    'flood-opacity',
    'font-family',
    'font-size',
    'font-size-adjust',
    'font-stretch',
    'font-style',
    'font-variant',
    'font-weight',
    'lighting-color',
    'marker-end',
    'marker-mid',
    'marker-start',
    'mask',
    'opacity',
    'paint-order',
    'shape-rendering',
    'stop-color',
    'stop-opacity',
    'stroke',
    'stroke-dasharray',
    'stroke-dashoffset',
    'stroke-linecap',
    'stroke-linejoin',
    'stroke-miterlimit',
    'stroke-opacity',
    'stroke-width',
    'text-anchor',
    'text-decoration',
    'text-rendering',
    'writing-mode',
))


class CSSSanitizer:
    """Sanitizes inline CSS, filtering out disallowed properties and URL values.

    Uses tinycss2 to parse CSS and then filters declarations based on
    a whitelist of allowed properties.
    """

    def __init__(self, allowed_properties=None, allowed_svg_properties=None):
        """Initialize the CSS sanitizer.

        Args:
            allowed_properties: Whitelist of allowed CSS property names.
                Defaults to ALLOWED_CSS_PROPERTIES.
            allowed_svg_properties: Whitelist of allowed SVG CSS property
                names. Defaults to ALLOWED_SVG_PROPERTIES.
        """
        self.allowed_properties = (
            allowed_properties
            if allowed_properties is not None
            else ALLOWED_CSS_PROPERTIES
        )
        self.allowed_svg_properties = (
            allowed_svg_properties
            if allowed_svg_properties is not None
            else ALLOWED_SVG_PROPERTIES
        )

        # Combine for quick lookup
        self._allowed = frozenset(
            set(self.allowed_properties) | set(self.allowed_svg_properties)
        )

    def sanitize_css(self, style):
        """Sanitize a CSS style string.

        Parses the CSS, removes declarations with disallowed properties,
        and strips URL values. Returns the sanitized CSS as a string.

        Args:
            style: A CSS style string (e.g., "color: red; font-size: 12px;").

        Returns:
            The sanitized CSS string, or an empty string if no valid
            declarations remain.
        """
        if not style:
            return ''

        # Parse the CSS
        try:
            rules = tinycss2.parse_declaration_list(style)
        except Exception:
            return ''

        result_parts = []

        for declaration in rules:
            # Skip anything that's not a declaration (e.g., parse errors)
            if declaration.type != 'declaration':
                continue

            # Get the lowercased property name
            prop_name = declaration.lower_name

            # Skip disallowed properties
            if prop_name not in self._allowed:
                continue

            # Check for url() in values - remove them
            values = []
            for token in declaration.value:
                if token.type == 'url':
                    # Skip URL tokens entirely
                    continue
                elif token.type == 'function':
                    func_name = token.lower_name
                    if func_name == 'url':
                        # Skip url() functions
                        continue
                    elif func_name == 'expression':
                        # Skip CSS expression() - IE-specific XSS vector
                        continue
                    else:
                        values.append(token)
                else:
                    values.append(token)

            # Serialize the declaration back
            if values:
                style_text = _serialize_declaration(prop_name, values)
                if style_text:
                    result_parts.append(style_text)

        return ' '.join(result_parts)


def _serialize_declaration(prop_name, value_tokens):
    """Serialize a CSS property name and list of value tokens back to a string.

    Args:
        prop_name: The CSS property name.
        value_tokens: A list of tinycss2 token objects.

    Returns:
        A CSS declaration string like "color: red;".
    """
    # Serialize the tokens back to a string
    value_str = ''
    for tok in value_tokens:
        value_str += _token_serialize(tok)

    value_str = value_str.strip()

    if not value_str:
        return ''

    return '%s: %s;' % (prop_name, value_str)


def _token_serialize(token):
    """Serialize a single tinycss2 token back to its CSS representation.

    Args:
        token: A tinycss2 token object.

    Returns:
        The token serialized as a string.
    """
    token_type = token.type

    if token_type == 'whitespace':
        return ' '
    elif token_type == 'literal':
        return str(token.value)
    elif token_type == 'ident':
        return str(token.value)
    elif token_type == 'string':
        return str(token.value)
    elif token_type == 'dimension':
        # Use int_value if it matches value exactly, otherwise use value
        int_val = getattr(token, 'int_value', None)
        if int_val is not None and float(int_val) == token.value:
            return str(int_val) + str(token.unit)
        return str(token.value) + str(token.unit)
    elif token_type == 'percentage':
        int_val = getattr(token, 'int_value', None)
        if int_val is not None and float(int_val) == token.value:
            return str(int_val) + '%'
        return str(token.value) + '%'
    elif token_type == 'number':
        int_val = getattr(token, 'int_value', None)
        if int_val is not None and float(int_val) == token.value:
            return str(int_val)
        return str(token.value)
    elif token_type == 'hash':
        return '#' + str(token.value)
    elif token_type == 'function':
        args_str = ''.join(_token_serialize(a) for a in token.arguments)
        return str(token.name) + '(' + args_str + ')'
    elif token_type == 'url':
        return ''
    elif token_type == 'comment':
        return ''
    elif token_type == 'colon':
        return ': '
    elif token_type == 'semicolon':
        return ';'
    elif token_type == 'comma':
        return ','
    elif token_type == 'bad-string':
        return ''
    elif token_type == 'bad-url':
        return ''
    else:
        return getattr(token, 'value', '')
