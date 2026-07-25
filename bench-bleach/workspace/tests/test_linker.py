"""Tests for bleach.linkifier.Linker class."""

from bleach.linkifier import Linker, build_url_re


def test_linker():
    """Verify Linker instantiation, custom TLDs, and batch processing."""
    # Basic instantiation with defaults
    linker = Linker()
    assert linker.callbacks == []
    assert linker.skip_tags == {'pre', 'code'}
    assert linker.parse_email is False

    # Custom parameters
    linker = Linker(
        callbacks=[],
        skip_tags={'pre'},
        parse_email=True,
    )
    assert linker.skip_tags == {'pre'}
    assert linker.parse_email is True

    # URL to link conversion
    linker = Linker()
    result = linker.linkify('Visit http://example.com now')
    assert '<a href="http://example.com">' in result

    # Batch processing - multiple texts
    linker = Linker()
    texts = [
        'First http://one.com',
        'Second http://two.com',
        'No URL here',
    ]
    for text in texts[:2]:
        result = linker.linkify(text)
        assert '<a' in result

    result = linker.linkify(texts[2])
    assert '<a' not in result

    # Custom TLD with build_url_re
    custom_re = build_url_re(['onion', 'bit', 'example'])
    linker = Linker(url_re=custom_re)
    result = linker.linkify('Visit http://site.onion now')
    assert '<a href="http://site.onion">' in result

    # Recognized tags parameter
    linker = Linker(recognized_tags={'p', 'div'})
    assert linker.recognized_tags == {'p', 'div'}

    # Custom email_re
    import re
    custom_email = re.compile(r'(?i)\b[A-Z0-9._%+-]+@example\.com\b')
    linker = Linker(email_re=custom_email, parse_email=True)
    result = linker.linkify('Contact user@example.com')
    assert '<a href="mailto:user@example.com">' in result
