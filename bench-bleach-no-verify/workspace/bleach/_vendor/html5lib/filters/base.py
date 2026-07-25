"""Base Filter class for html5lib token stream filtering."""


class Filter:
    """Base class for token stream filters.

    Filters wrap an input source (iterable of tokens) and provide
    a filtered output stream. Subclasses override __iter__ to
    implement filtering logic.
    """

    def __init__(self, source):
        """Initialize the filter with a source token iterator.

        Args:
            source: An iterable of html5lib token dictionaries.
        """
        self.source = source

    def __iter__(self):
        """Iterate over filtered tokens. Override in subclasses."""
        for token in self.source:
            yield token
