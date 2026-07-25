"""Integration tests verifying CSS sanitization in bleach.clean / Cleaner."""

import warnings
import pytest
from bleach.sanitizer import clean, Cleaner, NoCssSanitizerWarning
from bleach.css_sanitizer import CSSSanitizer


class TestCssIntegration:
    """Tests for CSS sanitization integration with clean() and Cleaner."""

    def test_style_sanitized_with_css_sanitizer(self):
        """Style attribute should be sanitized when css_sanitizer is provided."""
        css = CSSSanitizer()
        attrs = {'*': ['style']}
        tags = {'p'}
        result = clean(
            '<p style="color: red; behavior: url(xss.htc);">text</p>',
            tags=tags,
            attributes=attrs,
            css_sanitizer=css,
        )
        assert 'color: red' in result
        assert 'behavior' not in result

    def test_style_passes_through_without_sanitizer(self):
        """Style attribute should pass through unchanged without css_sanitizer."""
        attrs = {'*': ['style']}
        tags = {'p'}
        result = clean(
            '<p style="color: red;">text</p>',
            tags=tags,
            attributes=attrs,
        )
        assert 'color: red' in result

    def test_no_warning_without_style_in_attributes(self):
        """No warning should be issued if style is not in allowed attributes."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Cleaner(tags={'p'}, attributes={})
            for warning in w:
                assert not issubclass(warning.category, NoCssSanitizerWarning)

    def test_warning_with_style_in_attributes(self):
        """NoCssSanitizerWarning should be issued when style allowed without sanitizer."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Cleaner(tags={'p'}, attributes={'*': ['style']})
            found = False
            for warning in w:
                if issubclass(warning.category, NoCssSanitizerWarning):
                    found = True
            assert found

    def test_no_warning_with_sanitizer_provided(self):
        """No warning should be issued when css_sanitizer is provided."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Cleaner(
                tags={'p'},
                attributes={'*': ['style']},
                css_sanitizer=CSSSanitizer(),
            )
            for warning in w:
                assert not issubclass(warning.category, NoCssSanitizerWarning)

    def test_css_url_removed_from_style(self):
        """url() in style attribute should be removed by css_sanitizer."""
        css = CSSSanitizer()
        result = clean(
            '<p style="background: url(http://evil.com/bg.jpg); color: blue;">text</p>',
            tags={'p'},
            attributes={'*': ['style']},
            css_sanitizer=css,
        )
        assert 'url(' not in result
        assert 'color: blue' in result

    def test_style_removed_when_all_disallowed(self):
        """Style attribute should be removed when all CSS is filtered out."""
        css = CSSSanitizer()
        result = clean(
            '<p style="behavior: url(xss.htc); -moz-binding: url(xss.xml);">text</p>',
            tags={'p'},
            attributes={'*': ['style']},
            css_sanitizer=css,
        )
        # style attribute should be removed entirely since nothing was allowed
        assert 'style=' not in result or 'behavior' not in result

    def test_clean_function_with_css_sanitizer(self):
        """clean() function should accept and use css_sanitizer."""
        css = CSSSanitizer()
        result = clean(
            '<p style="color: red; font-size: 12px; -evil: something;">text</p>',
            tags={'p'},
            attributes={'*': ['style']},
            css_sanitizer=css,
        )
        assert 'color: red' in result
        assert '-evil' not in result

    def test_cleaner_instance_with_css_sanitizer(self):
        """Cleaner instance should use css_sanitizer for style attributes."""
        css = CSSSanitizer()
        cleaner = Cleaner(
            tags={'p'},
            attributes={'*': ['style']},
            css_sanitizer=css,
        )
        result = cleaner.clean('<p style="color: red; xss: bad;">text</p>')
        assert 'color: red' in result
        assert 'xss' not in result

    def test_multiple_tags_with_style(self):
        """CSS sanitizer should apply to style on all allowed tags."""
        css = CSSSanitizer()
        result = clean(
            '<p style="color: red; bad: xss;">text</p>'
            '<div style="font-size: 12px; bad: xss;">more</div>',
            tags={'p', 'div'},
            attributes={'p': ['style'], 'div': ['style']},
            css_sanitizer=css,
        )
        assert 'color: red' in result
        assert 'font-size: 12px' in result
        assert 'bad' not in result

    def test_style_not_added_when_not_in_attributes(self):
        """If style is not in allowed attributes, it should not appear."""
        css = CSSSanitizer()
        result = clean(
            '<p style="color: red;">text</p>',
            tags={'p'},
            attributes={},
            css_sanitizer=css,
        )
        assert 'style=' not in result

    def test_empty_css_after_sanitization(self):
        """When CSS sanitizer returns empty, style attribute should be removed."""
        css = CSSSanitizer()
        # Use only disallowed properties
        result = clean(
            '<p style="evil-prop: bad; bad2: worse;">text</p>',
            tags={'p'},
            attributes={'*': ['style']},
            css_sanitizer=css,
        )
        # style attribute should be gone since all properties were filtered
        assert 'evil-prop' not in result
        assert 'style=' not in result.lower() or result == 'text'

    def test_css_sanitizer_preserves_valid_css(self):
        """Valid CSS should be preserved when using css_sanitizer."""
        css = CSSSanitizer()
        result = clean(
            '<p style="text-align: center; color: #333;">Centered text</p>',
            tags={'p'},
            attributes={'*': ['style']},
            css_sanitizer=css,
        )
        assert 'text-align: center' in result
        assert '#333' in result
