#!/bin/sh -l

cd /opt/app || exit
RESULT="false"

python src/main.py --source "$1" --target "$2" --delete "$3" --cluster "$4" --sg "$5" \
  --az "$6" --subnet "$7" --tags "$8" --share "$9" --assume "${10}" --key "${11}" --account "${12}"
BUILD_RESULT=$?
if [ $BUILD_RESULT -ne 0 ]; then
  RESULT="true"
else
  RESULT="false"
fi

echo $RESULT
echo ::set-output name=success::$RESULT
