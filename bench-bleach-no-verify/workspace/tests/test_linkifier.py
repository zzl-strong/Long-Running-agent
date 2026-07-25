"""Tests for bleach.linkifier."""

import pytest
from bleach.linkifier import linkify, Linker, build_url_re, URL_RE
from bleach.callbacks import nofollow, target_blank, DEFAULT_CALLBACKS


class TestLinkify:
    """Tests for the linkify() convenience function."""

    def test_linkify_http_url(self):
        """HTTP URL should be converted to a link."""
        result = linkify('Check out http://example.com')
        assert '<a href="http://example.com"' in result

    def test_linkify_https_url(self):
        """HTTPS URL should be converted to a link."""
        result = linkify('Check out https://example.com')
        assert '<a href="https://example.com"' in result

    def test_linkify_ftp_url(self):
        """FTP URL should be converted to a link."""
        result = linkify('Check out ftp://files.example.com')
        assert '<a href="ftp://files.example.com"' in result

    def test_linkify_www_url(self):
        """www URL without protocol should get http:// prepended."""
        result = linkify('Check out www.example.com')
        assert '<a href="http://www.example.com"' in result

    def test_linkify_url_with_path(self):
        """URL with path should be preserved."""
        result = linkify('http://example.com/some/path')
        assert '<a href="http://example.com/some/path"' in result

    def test_linkify_url_with_query(self):
        """URL with query string should be preserved."""
        result = linkify('http://example.com/path?q=1')
        assert '<a href="http://example.com/path?q=1"' in result

    def test_linkify_url_with_fragment(self):
        """URL with fragment should be preserved."""
        result = linkify('http://example.com/path#section')
        assert '<a href="http://example.com/path#section"' in result

    def test_linkify_nofollow_default(self):
        """Default callbacks should include nofollow."""
        result = linkify('http://example.com')
        assert 'rel="nofollow"' in result

    def test_linkify_target_blank(self):
        """target_blank callback should add target and rel."""
        result = linkify('http://example.com', callbacks=[target_blank])
        assert 'target="_blank"' in result
        assert 'noopener' in result
        assert 'noreferrer' in result

    def test_linkify_multiple_urls(self):
        """Multiple URLs should all be linkified."""
        result = linkify('http://a.com and http://b.com')
        assert result.count('<a ') == 2

    def test_linkify_no_url(self):
        """Text without URLs should remain unchanged."""
        result = linkify('just plain text')
        assert '<a ' not in result
        assert 'just plain text' in result

    def test_linkify_empty_string(self):
        """Empty string should return empty string."""
        result = linkify('')
        assert result == ''

    def test_linkify_email(self):
        """Email should be linkified when parse_email=True."""
        result = linkify('user@example.com', parse_email=True)
        assert '<a href="mailto:user@example.com"' in result

    def test_linkify_email_mailto_provided(self):
        """mailto: prefix should be preserved but not shown."""
        result = linkify('mailto:user@example.com', parse_email=True)
        assert 'href="mailto:user@example.com"' in result
        assert '>user@example.com<' in result

    def test_linkify_email_not_parsed_by_default(self):
        """Email should not be linkified when parse_email=False."""
        result = linkify('user@example.com')
        assert '<a ' not in result


class TestLinker:
    """Tests for the Linker class."""

    def test_linker_basic(self):
        """Linker should linkify URLs."""
        linker = Linker()
        result = linker.linkify('http://example.com')
        assert '<a href="http://example.com"' in result

    def test_linker_custom_callbacks(self):
        """Linker should apply custom callbacks."""

        def custom_cb(attrs, new=False):
            attrs['class'] = 'custom'
            return attrs

        linker = Linker(callbacks=[custom_cb])
        result = linker.linkify('http://example.com')
        assert 'class="custom"' in result
        # Default nofollow should NOT be applied since we overrode callbacks
        assert 'rel="nofollow"' not in result

    def test_linker_parse_email(self):
        """Linker with parse_email=True should linkify emails."""
        linker = Linker(parse_email=True)
        result = linker.linkify('user@example.com')
        assert '<a href="mailto:user@example.com"' in result

    def test_linker_reuse(self):
        """Linker should be reusable across multiple calls."""
        linker = Linker()
        r1 = linker.linkify('http://a.com')
        r2 = linker.linkify('http://b.com')
        assert '<a href="http://a.com"' in r1
        assert '<a href="http://b.com"' in r2

    def test_linker_with_existing_html(self):
        """Linker should handle text with existing HTML."""
        linker = Linker()
        result = linker.linkify('<p>http://example.com</p>')
        assert '<p>' in result
        assert '<a href="http://example.com"' in result


class TestBuildUrlRe:
    """Tests for build_url_re()."""

    def test_build_url_re_default(self):
        """Default build_url_re should match URLs."""
        pattern = build_url_re()
        assert pattern.search('http://example.com')

    def test_build_url_re_parse_email(self):
        """build_url_re with parse_email=True should match emails."""
        pattern = build_url_re(parse_email=True)
        assert pattern.search('user@example.com')

    def test_build_url_re_compiled(self):
        """Result should be a compiled regex."""
        pattern = build_url_re()
        assert hasattr(pattern, 'search')


class TestCallbacks:
    """Tests for the callbacks module."""

    def test_nofollow(self):
        """nofollow callback should set rel=nofollow."""
        attrs = nofollow({'href': 'http://example.com'})
        assert attrs['rel'] == 'nofollow'

    def test_target_blank(self):
        """target_blank callback should set target and rel."""
        attrs = target_blank({'href': 'http://example.com'})
        assert attrs['target'] == '_blank'
        assert 'noopener' in attrs['rel']
        assert 'noreferrer' in attrs['rel']

    def test_target_blank_preserves_existing_rel(self):
        """target_blank should merge with existing rel attribute."""
        attrs = target_blank({'href': 'http://example.com', 'rel': 'nofollow'})
        assert attrs['target'] == '_blank'
        assert 'nofollow' in attrs['rel']
        assert 'noopener' in attrs['rel']
        assert 'noreferrer' in attrs['rel']

    def test_default_callbacks(self):
        """DEFAULT_CALLBACKS should include nofollow."""
        assert nofollow in DEFAULT_CALLBACKS
