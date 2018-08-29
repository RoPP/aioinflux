#!/usr/bin/env python
from pathlib import Path

from setuptools import setup

with open('README.rst', 'r') as f:
    long_description = f.read()

meta = {}  # type: dict
with open(str(Path(__file__).parent / 'aioinflux' / '__init__.py')) as f:
    exec('\n'.join(l for l in f if l.startswith('__')), meta)


setup(name='aioinflux',
      version=meta['__version__'],
      description='Asynchronous Python client for InfluxDB',
      long_description=long_description,
      author='Gustavo Bezerra',
      author_email='gusutabopb@gmail.com',
      url='https://github.com/plugaai/aioinflux',
      packages=['aioinflux'],
      include_package_data=True,
      python_requires='>=3.5',
      install_requires=['aiohttp>=3.0', 'ciso8601', 'async-generator'],
      extras_require={
          'test': [
              'pytest',
              'pytest-asyncio',
              'pytest-cov',
              'pyyaml',
              'pytz',
              'flake8',
          ],
          'docs': [
              'sphinx',
              'sphinx_rtd_theme',
              'sphinx-autodoc-typehints',
          ],
          'pandas': [
              'pandas>=0.21',
              'numpy'
          ]
      },
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Topic :: Database',
      ])
