import os
from setuptools import setup, find_packages

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as f:
    long_description = f.read() if os.path.exists('README.md') else ''

setup(
    name='bleach',
    version='6.2.0',
    description='An easy safelist-based HTML-sanitizing tool.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Will Kahn-Greene',
    author_email='willkg@mozilla.com',
    url='https://github.com/mozilla/bleach',
    license='Apache-2.0',
    packages=find_packages(exclude=['tests', 'tests.*']),
    python_requires='>=3.9',
    install_requires=[
        'html5lib>=1.0.1',
        'tinycss2>=1.1.0',
        'webencodings',
    ],
    extras_require={
        'css': ['tinycss2>=1.1.0'],
        'test': ['pytest>=7.0'],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Text Processing :: Markup :: HTML',
    ],
)
