"""Tests for bleach.parse_shim."""

import pytest
from bleach.parse_shim import urlparse


class TestUrlParse:
    """Tests for the urlparse shim function."""

    def test_scheme(self):
        """Scheme should be correctly extracted."""
        p = urlparse('http://example.com/path')
        assert p.scheme == 'http'

    def test_netloc(self):
        """Netloc should be correctly extracted."""
        p = urlparse('http://example.com/path')
        assert p.netloc == 'example.com'

    def test_path(self):
        """Path should be correctly extracted."""
        p = urlparse('http://example.com/some/path')
        assert p.path == '/some/path'

    def test_query_includes_question_mark(self):
        """Query should include the leading '?' character (legacy behavior)."""
        p = urlparse('http://example.com/path?q=1')
        assert p.query == '?q=1'

    def test_empty_query(self):
        """URL without query string should have empty query."""
        p = urlparse('http://example.com/path')
        assert p.query == ''

    def test_no_question_mark_on_empty_query(self):
        """Query should remain empty string (not '?') when there is no query."""
        p = urlparse('http://example.com/path')
        assert not p.query.startswith('?')

    def test_fragment(self):
        """Fragment should be correctly extracted."""
        p = urlparse('http://example.com/path#section')
        assert p.fragment == 'section'

    def test_params(self):
        """Params should be correctly extracted."""
        p = urlparse('http://example.com/path;params')
        assert p.params == 'params'

    def test_https_scheme(self):
        """HTTPS scheme should work."""
        p = urlparse('https://secure.example.com/')
        assert p.scheme == 'https'
        assert p.netloc == 'secure.example.com'

    def test_ftp_scheme(self):
        """FTP scheme should work."""
        p = urlparse('ftp://files.example.com/pub/')
        assert p.scheme == 'ftp'

    def test_mailto_scheme(self):
        """mailto scheme should work."""
        p = urlparse('mailto:user@example.com')
        assert p.scheme == 'mailto'
        assert p.path == 'user@example.com'

    def test_query_with_multiple_params(self):
        """Multiple query parameters should include '?' prefix."""
        p = urlparse('http://example.com/path?a=1&b=2')
        assert p.query == '?a=1&b=2'

    def test_query_with_fragment(self):
        """Query with fragment should handle both correctly."""
        p = urlparse('http://example.com/path?q=1#section')
        assert p.query == '?q=1'
        assert p.fragment == 'section'

    def test_no_scheme(self):
        """URL without scheme should have empty scheme."""
        p = urlparse('//example.com/path')
        assert p.scheme == ''
        assert p.netloc == 'example.com'
        assert p.path == '/path'

    def test_relative_url(self):
        """Relative URL should have empty scheme and netloc."""
        p = urlparse('/relative/path')
        assert p.scheme == ''
        assert p.netloc == ''
        assert p.path == '/relative/path'

    def test_empty_string(self):
        """Empty string should return empty components."""
        p = urlparse('')
        assert p.scheme == ''
        assert p.netloc == ''
        assert p.path == ''

    def test_complex_url(self):
        """Complex URL with all components should parse correctly."""
        p = urlparse('https://user:pass@example.com:8080/path;params?q=1#frag')
        assert p.scheme == 'https'
        assert p.netloc == 'user:pass@example.com:8080'
        assert p.path == '/path'
        assert p.params == 'params'
        assert p.query == '?q=1'
        assert p.fragment == 'frag'

    def test_query_only_question_mark(self):
        """Query with just '?' should still have the '?'."""
        p = urlparse('http://example.com/path?')
        # stdlib urlparse returns empty string for query when only '?' is present
        assert p.query == ''
