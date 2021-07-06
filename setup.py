from setuptools import find_packages
from setuptools import setup

setup(
    name='mercari-python-us',
    version='0.5',
    author='Philippe Remy',
    packages=find_packages(),
    install_requires=[
        'absl-py'
        'mailthon',
        'requests',
        'beautifulsoup4',
        'lxml',
        'wget'
    ]
)
