"""Tests for bleach.linkifier module."""

from bleach.linkifier import Linker


def test_linkify_basic():
    """Basic linkify tests: URL to link, nofollow, skip tags, no URL present."""
    linker = Linker()

    # Conversion of http://example.com to a link
    result = linker.linkify('Check out http://example.com today')
    assert '<a href="http://example.com"' in result
    assert 'http://example.com</a>' in result

    # nofollow attribute added
    linker_nofollow = Linker()
    from bleach.callbacks import nofollow
    linker_nofollow.callbacks = [nofollow]
    result = linker_nofollow.linkify('http://example.com')
    assert 'rel="nofollow"' in result

    # Skipping content inside <pre> and <code> tags
    result = linker.linkify('<pre>http://example.com</pre>')
    assert '<a' not in result

    result = linker.linkify('<code>http://example.com</code>')
    assert '<a' not in result

    # Correct handling when no URL present
    result = linker.linkify('No URLs here at all.')
    assert result == 'No URLs here at all.'
    assert '<a' not in result

    # URL inside allowed tag
    result = linker.linkify('<p>Visit http://example.com now</p>')
    assert '<a href="http://example.com"' in result
    assert '<p>' in result

    # www URL should be auto-prefixed with http://
    result = linker.linkify('Go to www.example.com now')
    assert 'href="http://www.example.com"' in result


def test_linkify_advanced():
    """Advanced linkify: email linking, parentheses, trailing punctuation,
    multiple callbacks."""
    linker = Linker(parse_email=True)
    from bleach.callbacks import nofollow, target_blank

    # Email linking with mailto:
    result = linker.linkify('Contact: user@example.com')
    assert '<a href="mailto:user@example.com">user@example.com</a>' in result

    # Parenthetical URLs like (http://example.com)
    result = linker.linkify('See (http://example.com) here')
    assert 'href="http://example.com"' in result

    # Trailing punctuation like 'http://example.com.' is not included
    result = linker.linkify('Visit http://example.com. Next')
    assert 'href="http://example.com"' in result
    # The period should be after the </a> tag
    assert 'example.com</a>. Next' in result

    # Applying multiple callbacks (nofollow and target_blank)
    linker_multi = Linker(callbacks=[nofollow, target_blank])
    result = linker_multi.linkify('http://example.com')
    assert 'rel="nofollow"' in result
    assert 'target="_blank"' in result


def test_custom_callbacks():
    """Test custom callbacks: adding attributes, blocking URLs by returning None,
    and combined effects."""
    from bleach.linkifier import Linker

    # Custom callback that adds a title attribute
    def add_title(attrs, new=False):
        attrs[(None, 'title')] = 'My Link'
        return attrs

    linker = Linker(callbacks=[add_title])
    result = linker.linkify('Visit http://example.com')
    assert 'title="My Link"' in result
    assert '<a href="http://example.com"' in result

    # Custom callback that blocks evil.com by returning None
    def block_evil(attrs, new=False):
        href = attrs.get((None, 'href'), '')
        if 'evil.com' in href:
            return None
        return attrs

    linker = Linker(callbacks=[block_evil])
    result = linker.linkify('Go to http://evil.com/malware')
    # The URL text should still appear, just not as a link
    assert '<a' not in result
    assert 'http://evil.com/malware' in result

    # Combined: add_title AND block_evil
    linker = Linker(callbacks=[add_title, block_evil])
    result = linker.linkify('Visit http://example.com and http://evil.com')
    # example.com should be linked with title
    assert 'title="My Link"' in result
    assert '<a href="http://example.com"' in result
    # evil.com should be plain text (blocked)
    assert 'http://evil.com' in result
    # evil.com should NOT have an <a> tag
    assert '<a href="http://evil.com"' not in result

