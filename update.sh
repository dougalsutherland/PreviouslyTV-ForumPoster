#!/bin/bash
set -e

cd `dirname $0`

git pull

./venv/bin/pip install -r requirements.txt
rm -f *.pyc
touch ptv_helper.wsgi
