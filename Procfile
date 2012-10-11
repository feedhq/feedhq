web: django-admin.py runserver --settings=$PROJ.settings 0.0.0.0:8000

compass: compass watch --force --no-line-comments --output-style compressed --require less --sass-dir $PROJ/$APP/static/$APP/css --css-dir $PROJ/$APP/static/$APP/css --image-dir /static/ $PROJ/$APP/static/$APP/css/screen.scss

worker: rqworker high default low
