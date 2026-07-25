"""Tests for bleach.html5lib_shim module."""

from bleach.html5lib_shim import Filter, BleachHTMLSerializer, convert_entities
from html5lib.filters.base import Filter as BaseFilter


class TestConvertEntities:
    """Tests for convert_entities function."""

    def test_ampersand(self):
        """&amp; should be converted to &."""
        result = convert_entities('Hello &amp; World')
        assert result == 'Hello & World'

    def test_less_than(self):
        """&lt; should be converted to <."""
        result = convert_entities('x &lt; 3')
        assert result == 'x < 3'

    def test_greater_than(self):
        """&gt; should be converted to >."""
        result = convert_entities('x &gt; 3')
        assert result == 'x > 3'

    def test_quote(self):
        """&quot; should be converted to \"."""
        result = convert_entities('&quot;hello&quot;')
        assert result == '"hello"'

    def test_apos(self):
        """&apos; should be converted to '."""
        result = convert_entities("&apos;hello&apos;")
        assert result == "'hello'"

    def test_numeric_decimal(self):
        """Numeric decimal entities should be converted."""
        result = convert_entities('&#60;foo&#62;')
        assert result == '<foo>'

    def test_numeric_hex(self):
        """Numeric hex entities should be converted."""
        result = convert_entities('&#x3C;foo&#x3E;')
        assert result == '<foo>'

    def test_multiple_entities(self):
        """Multiple entities in the same string."""
        result = convert_entities('A &amp; B &lt; C &gt; D &quot;E&quot;')
        assert result == 'A & B < C > D "E"'

    def test_no_entities(self):
        """Text with no entities should be returned unchanged."""
        result = convert_entities('Hello World')
        assert result == 'Hello World'

    def test_empty_string(self):
        """Empty string should return empty string."""
        result = convert_entities('')
        assert result == ''


class TestFilterBaseClass:
    """Tests for the Filter base class."""

    def test_filter_is_subclass(self):
        """Filter should be a subclass of html5lib.filters.base.Filter."""
        assert issubclass(Filter, BaseFilter)

    def test_filter_instantiable(self):
        """Filter should be directly instantiable."""
        # Filter requires a source parameter
        class DummyFilter(Filter):
            def __iter__(self):
                return iter([])

        f = DummyFilter(source=[])
        assert isinstance(f, BaseFilter)


class TestBleachHTMLSerializer:
    """Tests for BleachHTMLSerializer."""

    def test_serializer_subclass(self):
        """BleachHTMLSerializer should be a subclass of HTMLSerializer."""
        from html5lib.serializer import HTMLSerializer
        assert issubclass(BleachHTMLSerializer, HTMLSerializer)

    def test_serializer_instantiable(self):
        """BleachHTMLSerializer should be instantiable."""
        s = BleachHTMLSerializer()
        assert s is not None
