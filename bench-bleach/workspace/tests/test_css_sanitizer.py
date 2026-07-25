"""Tests for bleach.css_sanitizer.CSSSanitizer."""

from bleach.css_sanitizer import CSSSanitizer


def test_css_sanitizer():
    """Verify CSS sanitization removes dangerous values and preserves safe ones."""
    sanitizer = CSSSanitizer()

    # Remove background with url(javascript:...)
    result = sanitizer.sanitize_css("background: url('javascript:alert(1)')")
    assert 'url' not in result.lower() or 'javascript' not in result.lower()

    # Preserve color: red
    result = sanitizer.sanitize_css("color: red")
    assert 'color' in result
    assert 'red' in result

    # Handle comments - CSS comments should be removed
    result = sanitizer.sanitize_css("color: red; /* comment */ font-size: 12px")
    assert 'comment' not in result
    assert 'color: red' in result
    assert 'font-size' in result

    # SVG properties - fill should be allowed by default
    result = sanitizer.sanitize_css("fill: #fff")
    assert 'fill' in result

    # Disallowed properties should be stripped
    result = sanitizer.sanitize_css("position: absolute; color: red")
    assert 'position' not in result
    assert 'color: red' in result

    # url(...) without javascript should also be stripped (unsafe)
    result = sanitizer.sanitize_css("background: url('image.png')")
    assert 'url(' not in result

    # expression() should be stripped
    result = sanitizer.sanitize_css("width: expression(alert(1))")
    assert 'expression' not in result

    # Multiple safe properties
    result = sanitizer.sanitize_css("color: red; font-size: 12px; margin: 10px")
    assert 'color: red' in result
    assert 'font-size: 12px' in result
    assert 'margin: 10px' in result

    # Custom property sets
    custom = CSSSanitizer(
        allowed_css_properties={'color'},
        allowed_svg_properties=set(),
    )
    result = custom.sanitize_css("color: blue; font-size: 20px")
    assert 'color: blue' in result
    assert 'font-size' not in result
