"""Tests for bleach.html5lib_shim."""

import pytest
from bleach.html5lib_shim import Filter, convert_entities
from bleach._vendor.html5lib.filters.base import Filter as BaseFilter


class TestFilter:
    """Tests for the Filter class."""

    def test_filter_is_subclass_of_base_filter(self):
        """Filter should be a subclass of html5lib's Filter."""
        assert issubclass(Filter, BaseFilter)

    def test_filter_instantiation(self):
        """Filter should be instantiable with a source iterable."""
        tokens = [
            {'type': 'Characters', 'data': 'hello'},
        ]
        f = Filter(iter(tokens))
        result = list(f)
        assert result == tokens

    def test_filter_passes_tokens_through(self):
        """Filter should pass all tokens through by default."""
        tokens = [
            {'type': 'StartTag', 'name': 'p', 'data': {}},
            {'type': 'Characters', 'data': 'Hello'},
            {'type': 'EndTag', 'name': 'p', 'data': {}},
        ]
        f = Filter(iter(tokens))
        result = list(f)
        assert result == tokens

    def test_filter_can_be_subclassed(self):
        """Users should be able to subclass Filter for custom filtering."""

        class UpperFilter(Filter):
            def __iter__(self):
                for token in self.source:
                    if token['type'] == 'Characters':
                        token = dict(token)
                        token['data'] = token['data'].upper()
                    yield token

        tokens = [
            {'type': 'Characters', 'data': 'hello'},
        ]
        f = UpperFilter(iter(tokens))
        result = list(f)
        assert result[0]['data'] == 'HELLO'


class TestConvertEntities:
    """Tests for convert_entities function."""

    def test_ampersand(self):
        """&amp; should round-trip back to &amp; (re-escaped by serializer)."""
        assert convert_entities('&amp;') == '&amp;'

    def test_less_than(self):
        """&lt; should round-trip back to &lt; (re-escaped by serializer)."""
        assert convert_entities('&lt;') == '&lt;'

    def test_greater_than(self):
        """&gt; should round-trip back to &gt; (re-escaped by serializer)."""
        assert convert_entities('&gt;') == '&gt;'

    def test_plain_text_passes_through(self):
        """Plain text without entities should pass through unchanged."""
        assert convert_entities('hello world') == 'hello world'

    def test_empty_string(self):
        """Empty string should remain empty."""
        assert convert_entities('') == ''

    def test_multiple_entities(self):
        """Essential entities round-trip, non-essential get converted."""
        result = convert_entities('&amp; &lt; &gt;')
        # Essential entities round-trip
        assert '&amp;' in result
        assert '&lt;' in result
        assert '&gt;' in result

    def test_non_essential_entity_converted(self):
        """Non-essential entities (like &ouml;) should be converted to Unicode."""
        result = convert_entities('&ouml;')
        assert 'ö' in result
        assert '&ouml;' not in result
