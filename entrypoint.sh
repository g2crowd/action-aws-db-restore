#!/bin/bash -l
pipenv install
PYTHONPATH='/' pipenv run main -c "$1"
BUILD_RESULT=$?
if [ $BUILD_RESULT -eq 0 ]; then
  echo ::set-output name=success::true
  exit 0
else
  echo ::set-output name=success::false
  exit 1
fi
