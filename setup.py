# -*- coding: utf-8 -*-
from distutils.core import setup
from setuptools import find_packages

with open('README.rst') as readme:
    long_description = readme.read()

with open('requirements.txt') as reqs:
    install_requires = [
        line for line in reqs.read().split('\n') if (line and not
                                                     line.startswith('--'))
    ]

setup(
    name='feedhq',
    version=__import__('feedhq').__version__,
    author='Bruno Renie',
    author_email='bruno@renie.fr',
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    url='https://github.com/feedhq/feedhq',
    license='BSD',
    description='FeedHQ is a web-based feed reader',
    long_description=long_description,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    zip_safe=False,
    install_requires=install_requires,
)
