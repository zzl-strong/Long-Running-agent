"""Tests for the public API of the bleach package.

Verifies that all public symbols are importable and have the
expected types and behavior.
"""

import bleach


class TestPublicImports:
    """Verify all public symbols are importable from bleach."""

    def test_clean_importable(self):
        """clean should be importable and callable."""
        from bleach import clean
        assert callable(clean)

    def test_linkify_importable(self):
        """linkify should be importable and callable."""
        from bleach import linkify
        assert callable(linkify)

    def test_cleaner_importable(self):
        """Cleaner should be importable and instantiable."""
        from bleach import Cleaner
        assert callable(Cleaner)

    def test_linker_importable(self):
        """Linker should be importable and instantiable."""
        from bleach import Linker
        assert callable(Linker)

    def test_css_sanitizer_importable(self):
        """CSSSanitizer should be importable and instantiable."""
        from bleach import CSSSanitizer
        assert callable(CSSSanitizer)

    def test_allowed_tags_importable(self):
        """ALLOWED_TAGS should be importable."""
        from bleach import ALLOWED_TAGS
        assert isinstance(ALLOWED_TAGS, frozenset)

    def test_allowed_attributes_importable(self):
        """ALLOWED_ATTRIBUTES should be importable."""
        from bleach import ALLOWED_ATTRIBUTES
        assert isinstance(ALLOWED_ATTRIBUTES, dict)

    def test_allowed_protocols_importable(self):
        """ALLOWED_PROTOCOLS should be importable."""
        from bleach import ALLOWED_PROTOCOLS
        assert isinstance(ALLOWED_PROTOCOLS, frozenset)

    def test_nofollow_importable(self):
        """nofollow callback should be importable."""
        from bleach import nofollow
        assert callable(nofollow)

    def test_target_blank_importable(self):
        """target_blank callback should be importable."""
        from bleach import target_blank
        assert callable(target_blank)

    def test_default_callbacks_importable(self):
        """DEFAULT_CALLBACKS should be importable."""
        from bleach import DEFAULT_CALLBACKS
        assert isinstance(DEFAULT_CALLBACKS, list)

    def test_version_importable(self):
        """__version__ should be importable and a string."""
        version = bleach.__version__
        assert isinstance(version, str)
        assert len(version) > 0


class TestAllList:
    """Verify __all__ contains all expected public symbols."""

    def test_all_list_contains_all_symbols(self):
        """__all__ should list all public API symbols."""
        expected = {
            'clean',
            'linkify',
            'Cleaner',
            'Linker',
            'CSSSanitizer',
            'ALLOWED_TAGS',
            'ALLOWED_ATTRIBUTES',
            'ALLOWED_PROTOCOLS',
            'nofollow',
            'target_blank',
            'DEFAULT_CALLBACKS',
            '__version__',
        }
        assert set(bleach.__all__) == expected


class TestModuleAliases:
    """Verify that submodule-level symbols match top-level imports."""

    def test_clean_is_same(self):
        """Top-level clean should be the same as sanitizer.clean."""
        from bleach.sanitizer import clean as sanitizer_clean
        from bleach import clean
        assert clean is sanitizer_clean

    def test_linkify_is_same(self):
        """Top-level linkify should be the same as linkifier.linkify."""
        from bleach.linkifier import linkify as linkifier_linkify
        from bleach import linkify
        assert linkify is linkifier_linkify

    def test_cleaner_is_same(self):
        """Top-level Cleaner should be the same as sanitizer.Cleaner."""
        from bleach.sanitizer import Cleaner as SanitizerCleaner
        from bleach import Cleaner
        assert Cleaner is SanitizerCleaner

    def test_linker_is_same(self):
        """Top-level Linker should be the same as linkifier.Linker."""
        from bleach.linkifier import Linker as LinkifierLinker
        from bleach import Linker
        assert Linker is LinkifierLinker

    def test_css_sanitizer_is_same(self):
        """Top-level CSSSanitizer should be the same as css_sanitizer.CSSSanitizer."""
        from bleach.css_sanitizer import CSSSanitizer as CssCSSSanitizer
        from bleach import CSSSanitizer
        assert CSSSanitizer is CssCSSSanitizer

    def test_allowed_tags_is_same(self):
        """Top-level ALLOWED_TAGS should be the same as sanitizer.ALLOWED_TAGS."""
        from bleach.sanitizer import ALLOWED_TAGS as sanitizer_tags
        from bleach import ALLOWED_TAGS
        assert ALLOWED_TAGS is sanitizer_tags

    def test_allowed_attributes_is_same(self):
        """Top-level ALLOWED_ATTRIBUTES should be the same as sanitizer.ALLOWED_ATTRIBUTES."""
        from bleach.sanitizer import ALLOWED_ATTRIBUTES as sanitizer_attrs
        from bleach import ALLOWED_ATTRIBUTES
        assert ALLOWED_ATTRIBUTES is sanitizer_attrs

    def test_allowed_protocols_is_same(self):
        """Top-level ALLOWED_PROTOCOLS should be the same as sanitizer.ALLOWED_PROTOCOLS."""
        from bleach.sanitizer import ALLOWED_PROTOCOLS as sanitizer_protos
        from bleach import ALLOWED_PROTOCOLS
        assert ALLOWED_PROTOCOLS is sanitizer_protos

    def test_nofollow_is_same(self):
        """Top-level nofollow should be the same as callbacks.nofollow."""
        from bleach.callbacks import nofollow as cb_nofollow
        from bleach import nofollow
        assert nofollow is cb_nofollow

    def test_target_blank_is_same(self):
        """Top-level target_blank should be the same as callbacks.target_blank."""
        from bleach.callbacks import target_blank as cb_target_blank
        from bleach import target_blank
        assert target_blank is cb_target_blank

    def test_default_callbacks_is_same(self):
        """Top-level DEFAULT_CALLBACKS should be the same as callbacks.DEFAULT_CALLBACKS."""
        from bleach.callbacks import DEFAULT_CALLBACKS as cb_defaults
        from bleach import DEFAULT_CALLBACKS
        assert DEFAULT_CALLBACKS is cb_defaults


class TestFunctionalBasics:
    """Basic functional tests to verify the API works end-to-end."""

    def test_clean_basic(self):
        """clean() should sanitize HTML."""
        result = bleach.clean('<script>alert("xss")</script>')
        assert '<script>' not in result
        assert 'script' not in result.lower() or '&lt;script&gt;' in result

    def test_linkify_basic(self):
        """linkify() should convert URLs to links."""
        result = bleach.linkify('a http://example.com link')
        assert '<a ' in result
        assert 'href="http://example.com"' in result

    def test_cleaner_basic(self):
        """Cleaner should be configurable and work."""
        cleaner = bleach.Cleaner(tags=['b', 'i'])
        result = cleaner.clean('<b>bold</b> <script>evil</script>')
        assert '<b>bold</b>' in result
        assert '<script>' not in result

    def test_linker_basic(self):
        """Linker should be configurable and work."""
        linker = bleach.Linker()
        result = linker.linkify('a http://example.com link')
        assert '<a ' in result

    def test_css_sanitizer_basic(self):
        """CSSSanitizer should sanitize CSS."""
        sanitizer = bleach.CSSSanitizer()
        result = sanitizer.sanitize_css('color: red; expression(alert(1))')
        assert 'color: red' in result.lower()
        assert 'expression' not in result.lower()

    def test_nofollow_callback(self):
        """nofollow callback should set rel=nofollow."""
        from bleach import nofollow
        attrs = nofollow({})
        assert attrs['rel'] == 'nofollow'

    def test_target_blank_callback(self):
        """target_blank callback should set target=_blank."""
        from bleach import target_blank
        attrs = target_blank({})
        assert attrs['target'] == '_blank'
        assert 'noopener' in attrs['rel']
        assert 'noreferrer' in attrs['rel']

    def test_default_callbacks_contains_nofollow(self):
        """DEFAULT_CALLBACKS should contain nofollow."""
        from bleach import DEFAULT_CALLBACKS, nofollow
        assert nofollow in DEFAULT_CALLBACKS

    def test_allowed_tags_contains_expected(self):
        """ALLOWED_TAGS should contain common safe tags."""
        from bleach import ALLOWED_TAGS
        assert 'a' in ALLOWED_TAGS
        assert 'p' in ALLOWED_TAGS
        assert 'b' in ALLOWED_TAGS

    def test_allowed_attributes_has_a_tag(self):
        """ALLOWED_ATTRIBUTES should have attributes for 'a' tag."""
        from bleach import ALLOWED_ATTRIBUTES
        assert 'a' in ALLOWED_ATTRIBUTES
        assert 'href' in ALLOWED_ATTRIBUTES['a']

    def test_allowed_protocols_contains_http(self):
        """ALLOWED_PROTOCOLS should contain http and https."""
        from bleach import ALLOWED_PROTOCOLS
        assert 'http' in ALLOWED_PROTOCOLS
        assert 'https' in ALLOWED_PROTOCOLS
