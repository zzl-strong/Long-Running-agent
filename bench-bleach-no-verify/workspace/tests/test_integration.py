"""Integration tests for bleach that exercise combined usage of
clean, linkify, Cleaner, Linker, CSSSanitizer, and advanced patterns.

These tests demonstrate real-world usage scenarios as described in
the spec examples.
"""

import re

import bleach
from bleach.callbacks import nofollow, target_blank
from bleach.html5lib_shim import Filter
from bleach.linkifier import Linker, build_url_re


class TestCleanAndLinkify:
    """Test combined usage of clean() and linkify()."""

    def test_clean_then_linkify(self):
        """Clean HTML, then linkify URLs in the result."""
        dirty = '<p>Hello http://example.com <script>alert(1)</script></p>'
        cleaned = bleach.clean(dirty)
        result = bleach.linkify(cleaned)
        assert '<a ' in result
        assert 'href="http://example.com"' in result
        assert '<script>' not in result
        assert '&lt;script&gt;' in result

    def test_linkify_then_clean(self):
        """Linkify text, then clean the result to ensure safety."""
        text = 'Visit http://evil.com/"><script>alert(1)</script> for info'
        linked = bleach.linkify(text)
        result = bleach.clean(linked)
        # The URL should still be a link
        assert '<a ' in result
        # But the script tag in the URL should be escaped
        assert '<script>' not in result
        assert '&lt;script&gt;' in result or 'script' not in result.lower()

    def test_clean_with_linkify(self):
        """Clean and linkify in sequence on XSS payload."""
        dirty = '<div>http://safe.com <img src=x onerror=alert(1)></div>'
        cleaned = bleach.clean(dirty, tags=['div', 'a'])
        result = bleach.linkify(cleaned)
        assert 'onerror' not in result
        assert '<a ' in result
        assert 'href="http://safe.com"' in result


class TestCleanerWithFilters:
    """Test Cleaner with custom filters including linkification."""

    def test_cleaner_with_single_filter(self):
        """Cleaner should apply user-provided filters after sanitization."""

        class UpperFilter(Filter):
            def __iter__(self):
                for token in self.source:
                    yield token

        cleaner = bleach.Cleaner(filters=[UpperFilter])
        result = cleaner.clean('<p>hello</p>')
        assert 'hello' in result

    def test_cleaner_with_multiple_filters(self):
        """Cleaner should apply multiple filters in order."""
        call_order = []

        class FilterA(Filter):
            def __iter__(self):
                call_order.append('A')
                for token in self.source:
                    yield token

        class FilterB(Filter):
            def __iter__(self):
                call_order.append('B')
                for token in self.source:
                    yield token

        cleaner = bleach.Cleaner(filters=[FilterA, FilterB])
        cleaner.clean('<p>test</p>')
        # Filters chain: FilterB wraps FilterA wraps sanitizer.
        # When iterated, outermost runs first: B -> A -> sanitizer.
        assert call_order == ['B', 'A']

    def test_cleaner_linkify_filter_concept(self):
        """Demonstrate a filter that adds linkification as post-processing.

        This simulates what a LinkifyFilter would do — converting plain-text
        URLs within character data tokens into <a> links.
        """
        class LinkifyFilter(Filter):
            """Filter that linkifies URLs in text content."""
            def __iter__(self):
                linker = Linker()
                for token in self.source:
                    if token.get('type') == 'Characters':
                        data = token.get('data', '')
                        if data:
                            token = dict(token)
                            token['data'] = linker.linkify(data)
                    yield token

        cleaner = bleach.Cleaner(
            tags=['p', 'a', 'span'],
            filters=[LinkifyFilter],
        )
        result = cleaner.clean(
            '<p>Visit http://example.com for info</p>'
        )
        # The linkified HTML injected into character data gets escaped
        # by the serializer. This is expected behavior — for proper
        # linkification within the cleaning pipeline, the filter would
        # need to yield actual HTML tokens, not character data.
        assert '&lt;a ' in result
        assert 'http://example.com' in result

    def test_cleaner_linkify_filter_preserves_existing_links(self):
        """LinkifyFilter should preserve existing <a> tags."""

        class LinkifyFilter(Filter):
            def __iter__(self):
                linker = Linker()
                for token in self.source:
                    if token.get('type') == 'Characters':
                        data = token.get('data', '')
                        if data:
                            token = dict(token)
                            token['data'] = linker.linkify(data)
                    yield token

        cleaner = bleach.Cleaner(
            tags=['p', 'a', 'span'],
            filters=[LinkifyFilter],
        )
        result = cleaner.clean(
            '<p><a href="http://existing.com">click</a> and http://new.com</p>'
        )
        assert 'href="http://existing.com"' in result
        assert 'href="http://new.com"' in result


class TestCustomUrlRegex:
    """Test linkify with custom URL regex patterns."""

    def test_custom_url_re_only_matches_specific_domain(self):
        """Custom regex can limit linkification to specific domains."""
        custom_re = re.compile(
            r'(?<!["\':;.,=?!])\b(?:https?://(?:www\.)?mycompany\.com[^\s()<>]+)',
            re.IGNORECASE,
        )
        linker = bleach.Linker(url_re=custom_re)
        result = linker.linkify(
            'Visit http://mycompany.com/page and http://other.com/page'
        )
        assert 'href="http://mycompany.com/page"' in result
        assert '<a href="http://other.com"' not in result

    def test_custom_url_re_with_https_only(self):
        """Custom regex can restrict to https-only URLs."""
        custom_re = re.compile(
            r'(?<!["\':;.,=?!])\b(?:https://[^\s()<>]+)',
            re.IGNORECASE,
        )
        linker = bleach.Linker(url_re=custom_re)
        result = linker.linkify(
            'Safe https://secure.com vs http://insecure.com'
        )
        assert 'href="https://secure.com"' in result
        assert 'href="http://insecure.com"' not in result

    def test_build_url_re_with_custom_tlds(self):
        """build_url_re should accept custom TLD list."""
        custom_re = build_url_re(tlds='com|org|net')
        assert custom_re is not None

    def test_build_url_re_with_email(self):
        """build_url_re with parse_email=True should match emails."""
        email_re = build_url_re(parse_email=True)
        assert email_re is not None
        assert email_re.search('user@example.com') is not None

    def test_linkify_with_custom_callbacks(self):
        """Linkify should apply custom callbacks in order."""
        def add_class(attrs, new=False):
            attrs['class'] = 'custom-link'
            return attrs

        result = bleach.linkify(
            'Visit http://example.com',
            callbacks=[add_class, nofollow],
        )
        assert 'class="custom-link"' in result
        assert 'rel="nofollow"' in result

    def test_linkify_with_target_blank(self):
        """Linkify with target_blank should add security attributes."""
        result = bleach.linkify(
            'Visit http://example.com',
            callbacks=[target_blank],
        )
        assert 'target="_blank"' in result
        assert 'noopener' in result
        assert 'noreferrer' in result


class TestBatchProcessing:
    """Test batch processing of multiple HTML strings."""

    def test_clean_multiple_strings(self):
        """Clean should handle multiple strings in batch."""
        texts = [
            '<p>Text 1</p>',
            '<script>evil()</script>',
            '<b>Text 3</b>',
        ]
        results = [bleach.clean(text) for text in texts]
        assert '<p>Text 1</p>' in results[0]
        assert '<script>' not in results[1]
        assert '<b>Text 3</b>' in results[2]

    def test_linkify_multiple_strings(self):
        """Linkify should handle multiple strings in batch."""
        texts = [
            'Visit http://example.com',
            'Email user@example.com',
            'Plain text',
        ]
        results = [bleach.linkify(text) for text in texts]
        assert '<a ' in results[0]
        assert 'user@example.com' in results[1]
        assert results[2] == 'Plain text'

    def test_reuse_cleaner_instance(self):
        """Cleaner should be reusable across multiple calls."""
        cleaner = bleach.Cleaner(tags=['p', 'b', 'i'])
        result1 = cleaner.clean('<p>First <b>bold</b></p>')
        result2 = cleaner.clean('<p>Second <i>italic</i></p>')
        result3 = cleaner.clean('<script>evil</script>')
        assert '<b>bold</b>' in result1
        assert '<i>italic</i>' in result2
        assert '<script>' not in result3

    def test_reuse_linker_instance(self):
        """Linker should be reusable across multiple calls."""
        linker = bleach.Linker()
        result1 = linker.linkify('First http://example.com')
        result2 = linker.linkify('Second http://test.com')
        result3 = linker.linkify('No URL here')
        assert 'href="http://example.com"' in result1
        assert 'href="http://test.com"' in result2
        assert '<a' not in result3

    def test_clean_and_linkify_batch(self):
        """Combined clean+linkify on a batch of inputs."""
        inputs = [
            '<p>http://safe.com <script>xss</script></p>',
            '<div>http://other.com</div>',
            'plain http://text.com',
        ]
        results = []
        for text in inputs:
            cleaned = bleach.clean(text, tags=['p', 'div', 'a'])
            linked = bleach.linkify(cleaned)
            results.append(linked)
        # All results should be free of script tags
        for result in results:
            assert '<script>' not in result
        # URLs should be linked
        assert 'href="http://safe.com"' in results[0]
        assert 'href="http://other.com"' in results[1]


class TestFullStackIntegration:
    """End-to-end tests exercising all components together."""

    def test_clean_with_css_sanitizer_and_linkify(self):
        """Full pipeline: clean (with CSS sanitizer) + linkify."""
        css_sanitizer = bleach.CSSSanitizer()
        html = (
            '<p style="color: red; expression(alert(1))">'
            'Hello http://example.com'
            '</p>'
        )
        cleaned = bleach.clean(
            html,
            tags=['p', 'a'],
            attributes={'p': ['style']},
            css_sanitizer=css_sanitizer,
        )
        assert 'color: red' in cleaned
        assert 'expression' not in cleaned.lower()
        linked = bleach.linkify(cleaned)
        assert 'href="http://example.com"' in linked

    def test_custom_everything(self):
        """Test with completely custom tags, attributes, protocols, and callbacks."""
        custom_tags = ['div', 'span', 'a', 'img']
        custom_attrs = {
            'a': ['href', 'title'],
            'img': ['src', 'alt'],
        }
        custom_protocols = ['https']

        cleaner = bleach.Cleaner(
            tags=custom_tags,
            attributes=custom_attrs,
            protocols=custom_protocols,
        )

        # HTTPS link should be preserved
        result = cleaner.clean(
            '<div><a href="https://safe.com" title="ok">link</a>'
            '<a href="http://blocked.com">bad</a></div>'
        )
        assert 'href="https://safe.com"' in result
        assert 'href="http://blocked.com"' not in result

        # img src must use https
        result2 = cleaner.clean(
            '<img src="https://img.com/pic.png" alt="pic">'
            '<img src="http://evil.com/xss.png">'
        )
        assert 'src="https://img.com/pic.png"' in result2
        assert 'src="http://evil.com/xss.png"' not in result2

    def test_clean_with_strip(self):
        """Strip mode should remove disallowed tags entirely."""
        result = bleach.clean(
            '<p>Keep <script>evil</script> this</p>',
            tags=['p'],
            strip=True,
        )
        # With strip=True, the script tag is removed but its text
        # content "evil" is preserved by the tokenizer.
        assert '<p>Keep evil this</p>' in result

    def test_clean_without_strip(self):
        """Non-strip mode should escape disallowed tags."""
        result = bleach.clean(
            '<p>Keep <script>evil</script> this</p>',
            tags=['p'],
            strip=False,
        )
        assert '&lt;script&gt;' in result

    def test_linkify_with_parse_email(self):
        """Linkify with parse_email=True should linkify email addresses."""
        result = bleach.linkify(
            'Contact user@example.com',
            parse_email=True,
        )
        assert 'href="mailto:user@example.com"' in result

    def test_linkify_skip_tags(self):
        """Linkify should skip linkification inside certain HTML tags."""
        result = bleach.linkify(
            'Text http://example.com <pre>code http://nope.com</pre>',
            skip_tags=['pre'],
        )
        assert 'href="http://example.com"' in result
        # The URL inside <pre> should not be linked
        assert 'href="http://nope.com"' not in result
