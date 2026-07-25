"""Tests for bleach.callbacks module."""

from bleach.callbacks import nofollow, target_blank


def test_callbacks():
    """Test nofollow and target_blank callbacks with attrs dicts."""

    # --- nofollow tests ---

    # nofollow adds rel='nofollow' when no rel exists
    attrs = {(None, 'href'): 'http://example.com'}
    result = nofollow(attrs)
    assert (None, 'rel') in result
    assert result[(None, 'rel')] == 'nofollow'
    assert result[(None, 'href')] == 'http://example.com'

    # nofollow appends 'nofollow' to existing rel
    attrs = {(None, 'href'): 'http://example.com', (None, 'rel'): 'noopener'}
    result = nofollow(attrs)
    assert result[(None, 'rel')] == 'noopener nofollow'

    # nofollow does NOT duplicate 'nofollow' if already present
    attrs = {(None, 'href'): 'http://example.com', (None, 'rel'): 'nofollow'}
    result = nofollow(attrs)
    assert result[(None, 'rel')] == 'nofollow'

    # nofollow when 'nofollow' is part of a multi-value rel
    attrs = {(None, 'href'): 'http://example.com', (None, 'rel'): 'nofollow noopener'}
    result = nofollow(attrs)
    assert result[(None, 'rel')] == 'nofollow noopener'

    # --- target_blank tests ---

    # target_blank adds target='_blank' when no target exists
    attrs = {(None, 'href'): 'http://example.com'}
    result = target_blank(attrs)
    assert (None, 'target') in result
    assert result[(None, 'target')] == '_blank'
    assert result[(None, 'href')] == 'http://example.com'

    # target_blank sets target='_blank' even if target already exists
    attrs = {(None, 'href'): 'http://example.com', (None, 'target'): '_self'}
    result = target_blank(attrs)
    assert result[(None, 'target')] == '_blank'
