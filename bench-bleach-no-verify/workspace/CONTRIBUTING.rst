Contributing to Bleach
=====================

Development Setup
-----------------

1. Clone the repository::

    git clone https://github.com/mozilla/bleach.git
    cd bleach

2. Create and activate a virtual environment::

    python -m venv venv
    source venv/bin/activate

3. Install development dependencies::

    pip install -e ".[css]"
    pip install pytest

4. Run the tests::

    pytest tests/

Running Tests
-------------

Run the full test suite::

    pytest tests/

Run a specific test file::

    pytest tests/test_sanitizer.py

Coding Style
------------

Follow PEP 8 with a maximum line length of 100 characters.
