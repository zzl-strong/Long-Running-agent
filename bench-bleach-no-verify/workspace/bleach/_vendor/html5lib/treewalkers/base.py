"""Base tree walker that yields tokens from a token stream."""


class TreeWalker:
    """Base tree walker."""

    def __init__(self, tokens):
        self._tokens = tokens

    def __iter__(self):
        return iter(self._tokens)


class NonRecursiveTreeWalker(TreeWalker):
    """Non-recursive tree walker."""

    def getTreeWalker(self, tree, *args, **kwargs):
        return TreeWalker(tree)


def getTreeWalker(tree, *args, **kwargs):
    """Get a tree walker for the given tree."""
    if isinstance(tree, list):
        return TreeWalker(tree)
    return TreeWalker(tree)
