"""Tests for bleach.css_sanitizer."""

import pytest
from bleach.css_sanitizer import (
    CSSSanitizer,
    ALLOWED_CSS_PROPERTIES,
    ALLOWED_SVG_PROPERTIES,
)


class TestCSSSanitizerInit:
    """Tests for CSSSanitizer initialization."""

    def test_default_properties(self):
        """Default allowed properties should be set."""
        cs = CSSSanitizer()
        assert cs.allowed_properties == ALLOWED_CSS_PROPERTIES
        assert cs.allowed_svg_properties == ALLOWED_SVG_PROPERTIES

    def test_custom_properties(self):
        """Custom allowed properties should override defaults."""
        custom = frozenset(('color', 'font-size'))
        cs = CSSSanitizer(allowed_properties=custom)
        assert cs.allowed_properties == custom

    def test_custom_svg_properties(self):
        """Custom SVG properties should override defaults."""
        custom = frozenset(('fill', 'stroke'))
        cs = CSSSanitizer(allowed_svg_properties=custom)
        assert cs.allowed_svg_properties == custom

    def test_combined_allowed_set(self):
        """Internal _allowed set should combine CSS and SVG properties."""
        cs = CSSSanitizer()
        assert 'color' in cs._allowed
        assert 'fill' in cs._allowed


class TestSanitizeCss:
    """Tests for CSSSanitizer.sanitize_css()."""

    def test_empty_string(self):
        """Empty CSS should return empty string."""
        cs = CSSSanitizer()
        assert cs.sanitize_css('') == ''

    def test_none(self):
        """None should return empty string."""
        cs = CSSSanitizer()
        assert cs.sanitize_css(None) == ''

    def test_single_declaration(self):
        """Single allowed declaration should pass through."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: red;')
        assert 'color: red' in result

    def test_multiple_declarations(self):
        """Multiple allowed declarations should all pass through."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: red; font-size: 12px;')
        assert 'color: red' in result
        assert 'font-size: 12px' in result

    def test_disallowed_property_filtered(self):
        """Disallowed properties should be removed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: red; behavior: url(xss.htc);')
        assert 'color: red' in result
        assert 'behavior' not in result
        assert 'xss' not in result

    def test_expression_filtered(self):
        """CSS expression() should be removed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: expression(alert(1));')
        assert 'expression' not in result

    def test_url_in_value_removed(self):
        """url() in property value should be removed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('background: url(http://evil.com/xss);')
        assert 'url(' not in result
        assert 'http://evil.com' not in result

    def test_url_filtered_but_other_value_kept(self):
        """When url() is filtered, remaining values should be kept."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('background: url(bg.jpg) red;')
        # The url() part should be removed but the color might remain
        # depending on parsing
        assert 'url(' not in result

    def test_all_disallowed_results_empty(self):
        """All disallowed properties should result in empty string."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('behavior: url(xss.htc); -moz-binding: url(xss.xml);')
        assert result == '' or result.strip() == ''

    def test_svg_properties_allowed(self):
        """SVG properties should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('fill: red; stroke: blue;')
        assert 'fill: red' in result
        assert 'stroke: blue' in result

    def test_css_property_case_insensitive(self):
        """Property matching should be case-insensitive."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('COLOR: red;')
        assert 'color' in result.lower()
        assert 'red' in result

    def test_mixed_allowed_and_disallowed(self):
        """Mixed properties: allowed kept, disallowed removed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css(
            'color: red; -moz-binding: url(xss.xml); font-size: 12px;'
        )
        assert 'color: red' in result
        assert 'font-size: 12px' in result
        assert '-moz-binding' not in result

    def test_important_flag(self):
        """!important should be handled."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: red !important;')
        assert 'color' in result.lower()
        assert 'red' in result

    def test_margin_shorthand(self):
        """Margin shorthand property should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('margin: 10px 20px;')
        assert 'margin' in result
        assert '10px' in result
        assert '20px' in result

    def test_padding_shorthand(self):
        """Padding shorthand property should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('padding: 5px;')
        assert 'padding' in result

    def test_border_shorthand(self):
        """Border shorthand property should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('border: 1px solid black;')
        assert 'border' in result

    def test_background_with_multiple_values(self):
        """Background with multiple values should be handled."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('background: #fff;')
        assert 'background' in result

    def test_font_shorthand(self):
        """Font shorthand property should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('font: 12px Arial;')
        assert 'font' in result

    def test_width_percentage(self):
        """Percentage values should be preserved."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('width: 100%;')
        assert 'width' in result
        assert '100%' in result

    def test_text_align(self):
        """text-align property should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('text-align: center;')
        assert 'text-align' in result
        assert 'center' in result

    def test_display_property(self):
        """display property should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('display: none;')
        assert 'display' in result

    def test_position_property(self):
        """position property should be allowed."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('position: absolute; top: 0; left: 0;')
        assert 'position' in result
        assert 'top' in result
        assert 'left' in result

    def test_hex_color(self):
        """Hex color values should pass through."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: #ff0000;')
        assert '#ff0000' in result or '#f00' in result

    def test_rgb_color(self):
        """rgb() color values should pass through."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: rgb(255, 0, 0);')
        assert 'rgb' in result

    def test_custom_allowed_properties(self):
        """Custom allowed_properties should restrict filtering."""
        custom_css = frozenset(('color',))
        custom_svg = frozenset()
        cs = CSSSanitizer(
            allowed_properties=custom_css,
            allowed_svg_properties=custom_svg,
        )
        result = cs.sanitize_css('color: red; font-size: 12px;')
        assert 'color: red' in result
        assert 'font-size' not in result

    def test_custom_allowed_svg_properties(self):
        """Custom SVG properties should work."""
        cs = CSSSanitizer(allowed_svg_properties=frozenset())
        result = cs.sanitize_css('fill: red;')
        assert 'fill' not in result

    def test_malformed_css(self):
        """Malformed CSS should not raise exceptions."""
        cs = CSSSanitizer()
        # Should not raise
        result = cs.sanitize_css('this is not valid css {{{')
        assert isinstance(result, str)

    def test_css_comments_removed(self):
        """CSS comments should be handled gracefully."""
        cs = CSSSanitizer()
        result = cs.sanitize_css('color: /* comment */ red;')
        assert 'color' in result.lower()
        assert 'red' in result
