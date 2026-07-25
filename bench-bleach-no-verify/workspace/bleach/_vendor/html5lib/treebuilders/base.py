"""Base tree builder."""

from bleach._vendor.html5lib.constants import voidElements


class TreeBuilder:
    """Base tree builder that constructs a DOM tree from tokens."""

    def __init__(self, namespaceHTMLElements=True):
        self.namespaceHTMLElements = namespaceHTMLElements

    def insertDoctype(self, token):
        pass

    def insertComment(self, token, parent=None):
        pass

    def insertElement(self, token):
        pass

    def insertText(self, token):
        pass


def getTreeBuilder(treebuilder_type, implementation=None, **kwargs):
    """Get a tree builder instance."""
    return TreeBuilder(**kwargs)
