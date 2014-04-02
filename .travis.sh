#! /usr/bin/env bash
set -xe

psql -c 'CREATE DATABASE feedhq;' -U postgres

if [ $TOXENV == "coverage" ]
then
	pip install -r requirements-dev.txt coverage coveralls
	PYTHONPATH=. envdir tests/envdir coverage run `which django-admin.py` test
	coveralls
else
	tox -e $TOXENV
fi
