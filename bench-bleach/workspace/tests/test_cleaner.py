"""Tests for bleach.sanitizer.Cleaner class."""

import pytest
from bleach.sanitizer import Cleaner, ALLOWED_TAGS, ALLOWED_ATTRIBUTES, ALLOWED_PROTOCOLS


def test_cleaner():
    """Test Cleaner class with custom tags/attributes, cleaning multiple texts."""
    # Create Cleaner with custom tags
    custom_tags = {'p', 'b', 'i', 'a', 'span'}
    custom_attrs = {
        'a': ['href', 'title'],
        'span': ['class'],
    }
    cleaner = Cleaner(tags=custom_tags, attributes=custom_attrs)

    # Clean multiple texts
    result1 = cleaner.clean('<p>Hello <b>World</b></p>')
    assert '<p>Hello <b>World</b></p>' in result1

    result2 = cleaner.clean('<a href="http://example.com" onclick="bad()">link</a>')
    assert 'href="http://example.com"' in result2
    assert 'onclick' not in result2

    result3 = cleaner.clean('<span class="foo">text</span>')
    assert 'class="foo"' in result3

    # Test that div is not in custom tags (should be escaped)
    result4 = cleaner.clean('<div>block</div>')
    assert '&lt;div&gt;' in result4

    # Test with strip=True
    cleaner_strip = Cleaner(tags=custom_tags, attributes=custom_attrs, strip=True)
    result5 = cleaner_strip.clean('<div>block</div>')
    assert '<div' not in result5.lower()
    assert 'block' in result5

    # Test with custom protocols
    custom_protocols = {'https'}
    cleaner_proto = Cleaner(protocols=custom_protocols)
    result6 = cleaner_proto.clean('<a href="http://example.com">link</a>')
    assert 'href' not in result6.lower()

    result7 = cleaner_proto.clean('<a href="https://example.com">link</a>')
    assert 'href="https://example.com"' in result7

    # Test Cleaner with defaults
    cleaner_default = Cleaner()
    result8 = cleaner_default.clean('<script>alert(1)</script>')
    assert '&lt;script&gt;' in result8 or '&lt;script' in result8
    assert 'alert(1)' in result8

    # Test strip_comments=False
    cleaner_comments = Cleaner(strip_comments=False)
    result9 = cleaner_comments.clean('<!-- note --><b>text</b>')
    assert '<!--' in result9
