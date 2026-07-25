Bleach
======

.. image:: https://github.com/mozilla/bleach/workflows/tests/badge.svg
    :target: https://github.com/mozilla/bleach/actions

.. image:: https://badge.fury.io/py/bleach.svg
    :target: https://badge.fury.io/py/bleach

Bleach is an allowed-list-based HTML sanitizing library that escapes or strips
markup and attributes.

Bleach can also linkify text safely, applying filters that Django's ``urlize``
filter cannot, and optionally setting ``rel`` attributes, even on links
already in the text.

Bleach is intended for sanitizing text from *untrusted* sources. If you find
yourself jumping through hoops to allow your site administrators to do lots of
things, you're probably outside its use cases. Either trust those users, or
don't.

Because it relies on html5lib_, Bleach is as good as modern browsers at
dealing with weird, quirky HTML fragments. And *any* of Bleach's methods will
fix unbalanced or mis-nested tags.

The version on GitHub_ is the most up-to-date and contains the latest
bug fixes.

Basic Use
---------

The simplest way to use Bleach is:

.. code-block:: python

    >>> import bleach

    >>> bleach.clean('an <script>evil()</script> example')
    'an &lt;script&gt;evil()&lt;/script&gt; example'

    >>> bleach.linkify('a http://example.com link')
    'a <a href="http://example.com" rel="nofollow">http://example.com</a> link'

    >>> bleach.clean('a <strong> > <em>b</em></strong>')
    'a <strong> &gt; <em>b</em></strong>'

License
-------

Bleach is released under the Apache 2.0 license.

.. _html5lib: https://github.com/html5lib/html5lib-python
.. _GitHub: https://github.com/mozilla/bleach
