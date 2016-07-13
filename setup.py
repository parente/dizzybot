import os
import sys
from setuptools import setup

setup_args = dict(
    name='dizzybot',
    author='Peter Parente',
    author_email='parente@cs.unc.edu',
    description='Slack Real Time Messaging API + Tornado',
    version='0.1.0',
    license='BSD',
    py_modules=[
        'dizzybot'
    ],
    include_package_data=True,
)

if __name__ == '__main__':
    setup(**setup_args)
