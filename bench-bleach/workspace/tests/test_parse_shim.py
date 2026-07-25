"""Tests for bleach.parse_shim.urlparse."""

from bleach.parse_shim import urlparse


def test_urlparse():
    """Test that urlparse correctly parses a URL and exposes components."""
    result = urlparse('https://user:pass@example.com:8080/path/to/page?a=1&b=2#section')

    assert result.scheme == 'https'
    assert result.netloc == 'user:pass@example.com:8080'
    assert result.path == '/path/to/page'
    assert result.params == ''
    assert result.query == 'a=1&b=2'
    assert result.fragment == 'section'


def test_urlparse_simple():
    """Test urlparse with a simple URL."""
    result = urlparse('http://example.com')

    assert result.scheme == 'http'
    assert result.netloc == 'example.com'
    assert result.path == ''
    assert result.params == ''
    assert result.query == ''
    assert result.fragment == ''


def test_urlparse_repr():
    """Test that repr shows all components."""
    result = urlparse('https://example.com')
    r = repr(result)
    assert 'scheme' in r
    assert 'netloc' in r
    assert 'path' in r
    assert 'params' in r
    assert 'query' in r
    assert 'fragment' in r
