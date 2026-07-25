"""Callback functions for bleach linkification."""


def nofollow(attrs, new=False):
    """Add rel="nofollow" to link attributes.

    If a rel attribute already exists, 'nofollow' is appended to it
    (unless already present). If no rel exists, it is set to 'nofollow'.
    """
    rel_key = (None, 'rel')
    existing_rel = attrs.get(rel_key, '')
    rel_values = existing_rel.split()

    if 'nofollow' not in rel_values:
        rel_values.append('nofollow')

    attrs[rel_key] = ' '.join(rel_values)
    return attrs


def target_blank(attrs, new=False):
    """Add target="_blank" to link attributes."""
    attrs[(None, 'target')] = '_blank'
    return attrs
