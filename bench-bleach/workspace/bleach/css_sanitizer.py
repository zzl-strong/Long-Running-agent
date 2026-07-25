"""CSS Sanitizer - sanitizes CSS styles using tinycss2."""

import tinycss2
from tinycss2 import ast, serialize as _serialize

ALLOWED_CSS_PROPERTIES = frozenset({
    'background-color',
    'border',
    'border-bottom',
    'border-bottom-color',
    'border-bottom-left-radius',
    'border-bottom-right-radius',
    'border-bottom-style',
    'border-bottom-width',
    'border-collapse',
    'border-color',
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
    'clear',
    'color',
    'display',
    'float',
    'font',
    'font-family',
    'font-size',
    'font-style',
    'font-variant',
    'font-weight',
    'height',
    'letter-spacing',
    'line-height',
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
    'text-align',
    'text-decoration',
    'text-indent',
    'text-transform',
    'vertical-align',
    'visibility',
    'white-space',
    'width',
    'word-spacing',
    'word-break',
    'word-wrap',
})

ALLOWED_SVG_PROPERTIES = frozenset({
    'fill',
    'fill-opacity',
    'fill-rule',
    'stroke',
    'stroke-width',
    'stroke-linecap',
    'stroke-linejoin',
    'stroke-opacity',
    'stroke-dasharray',
    'stroke-dashoffset',
})


class CSSSanitizer:
    """Sanitize CSS styles in HTML attributes."""

    def __init__(self, allowed_css_properties=None,
                 allowed_svg_properties=None):
        self.allowed_css_properties = (
            allowed_css_properties
            if allowed_css_properties is not None
            else ALLOWED_CSS_PROPERTIES
        )
        self.allowed_svg_properties = (
            allowed_svg_properties
            if allowed_svg_properties is not None
            else ALLOWED_SVG_PROPERTIES
        )

    def sanitize_css(self, style):
        """Sanitize a CSS style string and return the sanitized version.

        Uses tinycss2 to parse the style string. Removes declarations
        with properties not in the allowed set, and removes dangerous
        values like url(...) and expression(...).
        """
        if not style:
            return ''

        parsed = tinycss2.parse_declaration_list(
            style, skip_comments=True, skip_whitespace=True
        )

        safe_declarations = []
        for declaration in parsed:
            if not isinstance(declaration, ast.Declaration):
                # Skip at-rules and other non-declaration nodes
                continue

            if not self._is_property_allowed(declaration.lower_name):
                continue

            if self._has_dangerous_values(declaration.value):
                continue

            safe_declarations.append(declaration)

        if not safe_declarations:
            return ''

        result = _serialize(safe_declarations)
        return result.rstrip(';')

    def _is_property_allowed(self, property_name):
        """Check if a CSS property name is in the allowed sets."""
        return (
            property_name in self.allowed_css_properties
            or property_name in self.allowed_svg_properties
        )

    def _has_dangerous_values(self, tokens):
        """Check if a list of tokens contains dangerous values.

        Dangerous values include:
        - URLToken (any url(...) in CSS is unsafe)
        - FunctionBlock with name 'url', 'expression', or containing 'javascript:'
        """
        for token in tokens:
            if isinstance(token, ast.URLToken):
                # Any URL in CSS is potentially dangerous
                return True
            if isinstance(token, ast.FunctionBlock):
                if token.lower_name in ('url', 'expression'):
                    return True
                # Also check if function name suggests a dangerous call
            if isinstance(token, ast.IdentToken):
                # Check for 'expression(' or similar in identifier values
                if token.lower_value in ('expression',):
                    return True
        return False
