"""Callbacks for the bleach linkifier.

Provides standard callbacks like nofollow and target_blank
that can be used with the Linker to modify link attributes.
"""


def nofollow(attrs, new=False):
    """Add rel="nofollow" to link attributes.

    Args:
        attrs: Dict of link attributes.
        new: Whether this is a new link (unused).

    Returns:
        Modified attributes dict.
    """
    attrs['rel'] = 'nofollow'
    return attrs


def target_blank(attrs, new=False):
    """Add target="_blank" and rel="noopener noreferrer" to link attributes.

    Args:
        attrs: Dict of link attributes.
        new: Whether this is a new link (unused).

    Returns:
        Modified attributes dict.
    """
    attrs['target'] = '_blank'
    # Merge with existing rel if present
    existing_rel = attrs.get('rel', '')
    rels = set(existing_rel.split()) if existing_rel else set()
    rels.update(['noopener', 'noreferrer'])
    attrs['rel'] = ' '.join(sorted(rels))
    return attrs


#: Default callbacks applied by the linker
DEFAULT_CALLBACKS = [nofollow]
