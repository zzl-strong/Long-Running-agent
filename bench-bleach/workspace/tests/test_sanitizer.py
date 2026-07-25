"""Tests for bleach.sanitizer.clean"""

import pytest
from bleach.sanitizer import Cleaner, ALLOWED_TAGS, ALLOWED_ATTRIBUTES, ALLOWED_PROTOCOLS


class TestCleanBasic:
    """Basic tests for the clean function."""

    def test_clean_passthrough(self):
        """clean should pass through safe HTML unchanged."""
        cleaner = Cleaner()
        html = '<b>bold</b>'
        result = cleaner.clean(html)
        assert '<b>bold</b>' in result, f"Expected <b>bold</b> in result, got: {result!r}"

    def test_clean_escapes_script(self):
        """clean should escape disallowed tags like <script>."""
        cleaner = Cleaner()
        html = '<script>alert(1)</script>'
        result = cleaner.clean(html)
        assert '&lt;script&gt;' in result or '&lt;script' in result, \
            f"Expected escaped script, got: {result!r}"
        assert 'alert(1)' in result, \
            f"Expected content preserved, got: {result!r}"

    def test_clean_strips_script_when_strip(self):
        """clean with strip=True should remove disallowed tags but keep content."""
        cleaner = Cleaner(strip=True)
        html = '<script>alert(1)</script>'
        result = cleaner.clean(html)
        assert '<script' not in result.lower(), \
            f"Expected no script tag, got: {result!r}"
        assert 'alert(1)' in result, \
            f"Expected content preserved, got: {result!r}"

    def test_clean_strips_comments(self):
        """clean should strip HTML comments by default."""
        cleaner = Cleaner()
        html = '<!-- comment --><b>text</b>'
        result = cleaner.clean(html)
        assert '<!--' not in result, f"Expected no comment, got: {result!r}"

    def test_clean_keeps_comments_when_false(self):
        """clean should preserve comments when strip_comments=False."""
        cleaner = Cleaner(strip_comments=False)
        html = '<!-- comment --><b>text</b>'
        result = cleaner.clean(html)
        assert '<!--' in result, f"Expected comment preserved, got: {result!r}"

    def test_clean_removes_disallowed_attributes(self):
        """clean should remove attributes that are not in the whitelist."""
        cleaner = Cleaner()
        html = '<a href="http://example.com" onclick="bad()">link</a>'
        result = cleaner.clean(html)
        assert 'href="http://example.com"' in result
        assert 'onclick' not in result

    def test_clean_removes_bad_protocols(self):
        """clean should remove URLs with disallowed protocols."""
        cleaner = Cleaner()
        html = '<a href="javascript:alert(1)">link</a>'
        result = cleaner.clean(html)
        assert 'javascript:' not in result.lower(), \
            f"Expected no javascript protocol, got: {result!r}"

    def test_clean_nested_escaping(self):
        """clean should handle nested disallowed tags."""
        cleaner = Cleaner()
        html = '<div><script>alert(1)</script></div>'
        result = cleaner.clean(html)
        # div is not in allowed tags, so both tags should be escaped
        assert 'alert(1)' in result
        assert '<script' not in result.lower()


def test_clean_basic():
    """Basic test for the clean function covering script tag removal,
    allowing safe tags, escaping when tag not allowed, and strip behavior."""
    cleaner = Cleaner()

    # Script tag removal / escaping
    result = cleaner.clean('<script>alert(1)</script>')
    assert '&lt;script&gt;' in result or '&lt;script' in result
    assert 'alert(1)' in result

    # Allowing safe tags (p, b, i)
    result = cleaner.clean('<b>bold</b>')
    assert '<b>bold</b>' in result

    # Escaping when tag not allowed
    result = cleaner.clean('<div>text</div>')
    assert '&lt;div&gt;' in result

    # Strip behavior
    cleaner_strip = Cleaner(strip=True)
    result = cleaner_strip.clean('<script>alert(1)</script>')
    assert '<script' not in result.lower()
    assert 'alert(1)' in result


def test_clean_advanced():
    """Advanced tests covering: removing javascript: protocol from href,
    stripping src from img if not allowed, removing HTML comments,
    preserving valid entities like &amp;."""
    cleaner = Cleaner()

    # Removing javascript: protocol from a href
    result = cleaner.clean('<a href="javascript:alert(1)">link</a>')
    assert 'javascript:' not in result.lower()
    assert 'href' not in result

    # Allowing safe http protocol
    result = cleaner.clean('<a href="http://example.com">link</a>')
    assert 'href="http://example.com"' in result

    # Stripping src from img if not allowed (img not in ALLOWED_TAGS)
    result = cleaner.clean('<img src="http://example.com/pic.jpg" alt="pic">')
    assert 'src' not in result

    # Removing HTML comments
    result = cleaner.clean('<!-- secret --><b>visible</b>')
    assert '<!--' not in result
    assert '<b>visible</b>' in result

    # Preserving valid entities like &amp; through round-trip
    result = cleaner.clean('<b>foo &amp; bar</b>')
    assert '&amp;' in result
    assert '<b>' in result

    # Mailto protocol should be allowed
    result = cleaner.clean('<a href="mailto:user@example.com">email</a>')
    assert 'href="mailto:user@example.com"' in result
