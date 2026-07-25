"""Tests for bleach.sanitizer."""

import pytest
import warnings
from bleach.sanitizer import (
    clean,
    Cleaner,
    ALLOWED_TAGS,
    ALLOWED_ATTRIBUTES,
    ALLOWED_PROTOCOLS,
    NoCssSanitizerWarning,
    BleachSanitizerFilter,
)


class TestClean:
    """Tests for the clean() function."""

    def test_clean_removes_script_tags(self):
        """Script tags should be escaped by default (strip=False)."""
        result = clean('<script>evil()</script>')
        assert '<script>' not in result
        assert 'evil()' in result
        assert '&lt;script&gt;' in result

    def test_clean_strip_disallowed_tags(self):
        """With strip=True, disallowed tags should be removed entirely."""
        result = clean('<script>evil()</script>', strip=True)
        assert '<script>' not in result
        assert 'evil()' in result
        assert '&lt;' not in result

    def test_clean_preserves_allowed_tags(self):
        """Allowed tags should pass through unchanged."""
        result = clean('<p>hello</p>')
        assert '<p>' in result
        assert 'hello' in result

    def test_clean_strips_disallowed_attributes(self):
        """Disallowed attributes should be removed."""
        result = clean('<a href="http://example.com" onclick="evil()">link</a>')
        assert 'href="http://example.com"' in result
        assert 'onclick' not in result

    def test_clean_blocks_javascript_protocol(self):
        """javascript: protocol URLs should be removed."""
        result = clean('<a href="javascript:alert(1)">link</a>')
        assert 'javascript:' not in result
        assert 'link' in result

    def test_clean_allows_http_protocol(self):
        """http: protocol URLs should be allowed."""
        result = clean('<a href="http://example.com">link</a>')
        assert 'href="http://example.com"' in result

    def test_clean_allows_https_protocol(self):
        """https: protocol URLs should be allowed."""
        result = clean('<a href="https://example.com">link</a>')
        assert 'href="https://example.com"' in result

    def test_clean_allows_mailto_protocol(self):
        """mailto: protocol URLs should be allowed."""
        result = clean('<a href="mailto:user@example.com">email</a>')
        assert 'href="mailto:user@example.com"' in result

    def test_clean_allows_relative_urls(self):
        """Relative URLs should be allowed."""
        result = clean('<a href="/relative/path">link</a>')
        assert 'href="/relative/path"' in result

    def test_clean_strips_comments_by_default(self):
        """HTML comments should be stripped by default."""
        result = clean('<!-- secret --><p>text</p>')
        assert '<!--' not in result
        assert '<p>' in result

    def test_clean_preserves_comments_when_not_stripping(self):
        """Comments should be preserved when strip_comments=False."""
        result = clean('<!-- comment --><p>text</p>', strip_comments=False)
        assert '<!-- comment -->' in result
        assert '<p>' in result

    def test_clean_empty_string(self):
        """Empty string should return empty string."""
        assert clean('') == ''

    def test_clean_plain_text(self):
        """Plain text without HTML should pass through."""
        result = clean('hello world')
        assert 'hello world' in result

    def test_clean_xss_img_onerror(self):
        """XSS via img onerror should be blocked."""
        result = clean('<img src=x onerror="alert(1)">')
        assert 'onerror' not in result
        assert 'alert(1)' not in result

    def test_clean_nested_disallowed_tags(self):
        """Nested disallowed tags should all be handled."""
        result = clean('<div><script>evil()</script></div>', strip=True)
        assert '<div>' not in result
        assert '<script>' not in result
        assert 'evil()' in result

    def test_clean_allowed_tag_with_disallowed_child(self):
        """Allowed tag with disallowed child should handle child."""
        result = clean('<p>text<script>evil()</script>more</p>')
        assert '<p>' in result
        assert 'text' in result
        assert 'more' in result
        assert '<script>' not in result

    def test_clean_multiple_allowed_tags(self):
        """Multiple allowed tags should all pass through."""
        result = clean('<p>one</p><p>two</p><br>')
        assert result.count('<p>') == 2
        assert 'one' in result
        assert 'two' in result

    def test_clean_text_with_entities(self):
        """Text with HTML entities should be handled."""
        result = clean('<p>Hello &amp; Goodbye</p>')
        assert '<p>' in result
        assert 'Hello' in result
        assert 'Goodbye' in result

    def test_clean_with_custom_tags(self):
        """Custom allowed tags should work."""
        result = clean('<custom>content</custom>', tags={'custom'})
        assert '<custom>' in result

    def test_clean_with_custom_attributes(self):
        """Custom allowed attributes should work."""
        result = clean(
            '<span data-x="1">text</span>',
            tags={'span'},
            attributes={'span': ['data-x']},
        )
        assert 'data-x="1"' in result

    def test_clean_with_custom_protocols(self):
        """Custom allowed protocols should work."""
        result = clean(
            '<a href="ftp://files.com">ftp</a>',
            protocols={'http', 'https', 'ftp'},
        )
        assert 'href="ftp://files.com"' in result


class TestCleaner:
    """Tests for the Cleaner class."""

    def test_cleaner_basic(self):
        """Cleaner should sanitize HTML."""
        cleaner = Cleaner()
        result = cleaner.clean('<script>evil()</script>')
        assert '<script>' not in result
        assert 'evil()' in result

    def test_cleaner_custom_tags(self):
        """Cleaner with custom tags should work."""
        cleaner = Cleaner(tags={'p', 'b'})
        result = cleaner.clean('<p>hello <b>world</b></p><script>evil()</script>')
        assert '<p>' in result
        assert '<b>' in result
        assert '<script>' not in result

    def test_cleaner_custom_attributes(self):
        """Cleaner with custom attributes should work."""
        cleaner = Cleaner(
            tags={'span'},
            attributes={'span': ['class', 'data-x']},
        )
        result = cleaner.clean('<span class="c" data-x="1" onclick="bad()">text</span>')
        assert 'class="c"' in result
        assert 'data-x="1"' in result
        assert 'onclick' not in result

    def test_cleaner_custom_protocols(self):
        """Cleaner with custom protocols should work."""
        cleaner = Cleaner(protocols={'http', 'https', 'custom'})
        result = cleaner.clean('<a href="custom://resource">link</a>')
        assert 'href="custom://resource"' in result

    def test_cleaner_strip_mode(self):
        """Cleaner with strip=True should remove disallowed tags."""
        cleaner = Cleaner(strip=True)
        result = cleaner.clean('<script>evil()</script>')
        assert '<script>' not in result
        assert '&lt;' not in result
        assert 'evil()' in result

    def test_cleaner_strip_comments_false(self):
        """Cleaner with strip_comments=False should keep comments."""
        cleaner = Cleaner(strip_comments=False)
        result = cleaner.clean('<!-- comment -->')
        assert '<!-- comment -->' in result

    def test_cleaner_reuse(self):
        """Cleaner should be reusable across multiple calls."""
        cleaner = Cleaner()
        r1 = cleaner.clean('<script>a</script>')
        r2 = cleaner.clean('<script>b</script>')
        assert '<script>' not in r1
        assert '<script>' not in r2


class TestNoCssSanitizerWarning:
    """Tests for NoCssSanitizerWarning."""

    def test_warning_is_user_warning(self):
        """NoCssSanitizerWarning should be a UserWarning subclass."""
        assert issubclass(NoCssSanitizerWarning, UserWarning)

    def test_warning_when_style_allowed_without_sanitizer(self):
        """Should warn when style attribute is allowed without CSS sanitizer."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            Cleaner(
                tags={'p'},
                attributes={'p': ['style']},
            )
            assert len(w) == 1
            assert issubclass(w[0].category, NoCssSanitizerWarning)

    def test_no_warning_when_style_not_allowed(self):
        """No warning when style attribute is not in allowed attributes."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            Cleaner(
                tags={'p'},
                attributes={'p': ['class']},
            )
            style_warnings = [
                x for x in w
                if issubclass(x.category, NoCssSanitizerWarning)
            ]
            assert len(style_warnings) == 0

    def test_no_warning_when_css_sanitizer_provided(self):
        """No warning when CSS sanitizer is provided."""

        class MockCSSSanitizer:
            def sanitize_css(self, css):
                return css

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            Cleaner(
                tags={'p'},
                attributes={'p': ['style']},
                css_sanitizer=MockCSSSanitizer(),
            )
            style_warnings = [
                x for x in w
                if issubclass(x.category, NoCssSanitizerWarning)
            ]
            assert len(style_warnings) == 0


class TestAllAllowedTags:
    """Tests for the default ALLOWED_TAGS."""

    def test_p_tag_allowed(self):
        result = clean('<p>text</p>')
        assert '<p>' in result

    def test_b_tag_allowed(self):
        result = clean('<b>bold</b>')
        assert '<b>' in result

    def test_em_tag_allowed(self):
        result = clean('<em>italic</em>')
        assert '<em>' in result

    def test_i_tag_allowed(self):
        result = clean('<i>italic</i>')
        assert '<i>' in result

    def test_strong_tag_allowed(self):
        result = clean('<strong>bold</strong>')
        assert '<strong>' in result

    def test_a_tag_allowed(self):
        result = clean('<a href="http://x.com">link</a>')
        assert '<a href="http://x.com">' in result

    def test_br_tag_allowed(self):
        result = clean('text<br>more')
        assert '<br' in result

    def test_li_tag_allowed(self):
        result = clean('<li>item</li>')
        assert '<li>' in result

    def test_ol_tag_allowed(self):
        result = clean('<ol><li>item</li></ol>')
        assert '<ol>' in result

    def test_ul_tag_allowed(self):
        result = clean('<ul><li>item</li></ul>')
        assert '<ul>' in result

    def test_blockquote_tag_allowed(self):
        result = clean('<blockquote>quote</blockquote>')
        assert '<blockquote>' in result

    def test_code_tag_allowed(self):
        result = clean('<code>code</code>')
        assert '<code>' in result

    def test_abbr_tag_allowed(self):
        result = clean('<abbr title="abbreviation">abbr</abbr>')
        assert '<abbr' in result


class TestBleachSanitizerFilter:
    """Tests for the internal BleachSanitizerFilter."""

    def test_filter_passes_allowed_tokens(self):
        """Filter should pass through allowed tokens unmodified."""
        tokens = [
            {'type': 'StartTag', 'name': 'p', 'data': {}},
            {'type': 'Characters', 'data': 'hello'},
            {'type': 'EndTag', 'name': 'p', 'data': {}},
        ]
        f = BleachSanitizerFilter(iter(tokens))
        result = list(f)
        assert len(result) == 3
        assert result[0]['type'] == 'StartTag'
        assert result[1]['data'] == 'hello'

    def test_filter_escapes_disallowed_tags(self):
        """Filter should escape disallowed tags when strip=False."""
        tokens = [
            {'type': 'StartTag', 'name': 'script', 'data': {}},
            {'type': 'Characters', 'data': 'evil()'},
            {'type': 'EndTag', 'name': 'script', 'data': {}},
        ]
        f = BleachSanitizerFilter(iter(tokens), strip=False)
        result = list(f)
        # Should produce escaped characters tokens
        assert all(t['type'] == 'Characters' for t in result)
        assert result[0]['data'] == '<script>'
        assert result[1]['data'] == 'evil()'
        assert result[2]['data'] == '</script>'

    def test_filter_strips_disallowed_tags(self):
        """Filter should strip disallowed tags when strip=True."""
        tokens = [
            {'type': 'StartTag', 'name': 'script', 'data': {}},
            {'type': 'Characters', 'data': 'evil()'},
            {'type': 'EndTag', 'name': 'script', 'data': {}},
        ]
        f = BleachSanitizerFilter(iter(tokens), strip=True)
        result = list(f)
        assert len(result) == 1
        assert result[0]['data'] == 'evil()'

    def test_filter_removes_disallowed_attributes(self):
        """Filter should remove disallowed attributes from allowed tags."""
        tokens = [
            {'type': 'StartTag', 'name': 'a',
             'data': {'href': 'http://x.com', 'onclick': 'bad()'}},
            {'type': 'Characters', 'data': 'link'},
            {'type': 'EndTag', 'name': 'a', 'data': {}},
        ]
        f = BleachSanitizerFilter(iter(tokens))
        result = list(f)
        assert 'href' in result[0]['data']
        assert 'onclick' not in result[0]['data']

    def test_filter_removes_disallowed_protocols(self):
        """Filter should remove attributes with disallowed protocols."""
        tokens = [
            {'type': 'StartTag', 'name': 'a',
             'data': {'href': 'javascript:alert(1)'}},
            {'type': 'Characters', 'data': 'link'},
            {'type': 'EndTag', 'name': 'a', 'data': {}},
        ]
        f = BleachSanitizerFilter(iter(tokens))
        result = list(f)
        assert 'href' not in result[0]['data']

    def test_filter_allows_protocol_relative_urls(self):
        """Filter should allow protocol-relative URLs."""
        tokens = [
            {'type': 'StartTag', 'name': 'a',
             'data': {'href': '//example.com/path'}},
        ]
        f = BleachSanitizerFilter(iter(tokens))
        result = list(f)
        assert result[0]['data']['href'] == '//example.com/path'

    def test_filter_strips_comments(self):
        """Filter should strip comment tokens when strip_comments=True."""
        tokens = [
            {'type': 'Comment', 'data': ' secret '},
            {'type': 'Characters', 'data': 'text'},
        ]
        f = BleachSanitizerFilter(iter(tokens), strip_comments=True)
        result = list(f)
        assert len(result) == 1
        assert result[0]['data'] == 'text'

    def test_filter_keeps_comments(self):
        """Filter should keep comment tokens when strip_comments=False."""
        tokens = [
            {'type': 'Comment', 'data': ' comment '},
            {'type': 'Characters', 'data': 'text'},
        ]
        f = BleachSanitizerFilter(iter(tokens), strip_comments=False)
        result = list(f)
        assert len(result) == 2
        assert result[0]['data'] == ' comment '
