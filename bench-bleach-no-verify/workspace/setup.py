"""Setup script for bleach, an HTML sanitizing library."""

from setuptools import setup, find_packages
import os


def get_version():
    """Get the version from bleach/__init__.py without importing."""
    version_ns = {}
    with open(os.path.join(os.path.dirname(__file__), 'bleach', '__init__.py')) as f:
        for line in f:
            if line.startswith('__version__'):
                exec(line, version_ns)
                return version_ns['__version__']
    return '0.0.0'


def get_long_description():
    """Get the long description from README.rst."""
    with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as f:
        return f.read()


setup(
    name='bleach',
    version=get_version(),
    description='An easy whitelist-based HTML-sanitizing tool',
    long_description=get_long_description(),
    url='https://github.com/mozilla/bleach',
    author='Will Kahn-Greene',
    author_email='willkg@mozilla.com',
    license='Apache-2.0',
    packages=find_packages(),
    python_requires='>=3.6',
    install_requires=[
        'html5lib>=1.0.1',
        'six>=1.9.0',
        'webencodings',
        'tinycss2>=1.1.0,<1.2',
    ],
    extras_require={
        'css': ['tinycss2>=1.1.0,<1.2'],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Topic :: Text Processing :: Markup :: HTML',
    ],
)
