"""Integration tests for bleach - combined usage of clean, CSSSanitizer, and linkify."""

from bleach import clean, linkify
from bleach.css_sanitizer import CSSSanitizer
from bleach.linkifier import LinkifyFilter
from bleach.sanitizer import Cleaner


def test_combined():
    """Test combined usage of clean, CSSSanitizer, and linkify.

    Takes dirty HTML with scripts, styles, and URLs, runs clean with
    CSSSanitizer, then linkify with nofollow and parse_email, and
    verifies final output is safe and contains proper links.
    """
    dirty = (
        '<p>Hello <script>alert("xss")</script>World!</p>'
        '<p style="color: red; background: url(\'javascript:evil()\')">Styled text</p>'
        '<a href="javascript:alert(1)">Bad link</a>'
        '<p>Visit http://example.com or email user@example.com for info</p>'
    )

    css_sanitizer = CSSSanitizer()

    # Clean with CSSSanitizer; allow style attribute on p tags so CSS gets sanitized
    tags = {'p', 'a'}
    attributes = {
        'p': ['style'],
        'a': ['href'],
    }
    cleaned = clean(
        dirty,
        tags=tags,
        attributes=attributes,
        css_sanitizer=css_sanitizer,
    )

    # Script tags should be escaped (not executable)
    assert '<script>' not in cleaned
    assert '</script>' not in cleaned

    # javascript: protocol should not appear
    assert 'javascript:' not in cleaned.lower()

    # Safe CSS properties should be preserved, dangerous ones removed
    assert 'color:' in cleaned.lower()

    # Step 2: Linkify the cleaned HTML (converts URLs to links with nofollow)
    result = linkify(cleaned, parse_email=True)

    # Result should contain the http://example.com link
    assert 'http://example.com' in result
    assert '<a ' in result and 'href=' in result

    # Result should have rel="nofollow" from default callbacks
    assert 'rel="nofollow"' in result

    # Result should contain the email as a mailto link
    assert 'mailto:' in result
    assert 'user@example.com' in result

    # Result should NOT re-introduce scripts or javascript
    assert '<script>' not in result
    assert 'javascript:' not in result.lower()


def test_linkify_filter():
    """Test using LinkifyFilter as a filter with Cleaner.

    Creates a Cleaner with a LinkifyFilter and processes HTML,
    verifying that links are created inside allowed elements.
    """
    from bleach.linkifier import LinkifyFilter
    from bleach.callbacks import nofollow

    html = '<p>Visit http://example.com today</p><pre>http://skipme.com</pre>'

    cleaner = Cleaner(
        tags={'p', 'pre', 'a'},
        attributes={'a': ['href', 'rel']},
        filters=[LinkifyFilter],
    )

    result = cleaner.clean(html)

    # http://example.com should be linkified inside <p>
    assert 'http://example.com' in result
    assert '<a ' in result
    assert 'href=' in result

    # http://skipme.com should NOT be linkified (inside <pre>)
    assert 'http://skipme.com' in result
    # The skipme URL should not be in an <a> tag
    import re
    # Count how many <a> tags are in the result
    a_count = len(re.findall(r'<a\s', result))
    assert a_count == 1, f"Expected 1 link, found {a_count}: {result}"
