"""Vendored html5lib - a pure-Python HTML parser and serializer.

This is a minimal implementation providing the subset of html5lib's API
that bleach needs: tokenizer, serializer, tree walkers, and filters.
"""

from bleach._vendor.html5lib.html5parser import HTMLParser
from bleach._vendor.html5lib.serializer import HTMLSerializer
from bleach._vendor.html5lib.constants import tokenTypes, voidElements, namespace, namespaces
from bleach._vendor.html5lib.treewalkers.base import getTreeWalker, TreeWalker
from bleach._vendor.html5lib.treebuilders.base import getTreeBuilder, TreeBuilder
from bleach._vendor.html5lib.filters.base import Filter

__all__ = [
    'HTMLParser',
    'HTMLSerializer',
    'tokenTypes',
    'voidElements',
    'namespace',
    'namespaces',
    'getTreeWalker',
    'TreeWalker',
    'getTreeBuilder',
    'TreeBuilder',
    'Filter',
]
