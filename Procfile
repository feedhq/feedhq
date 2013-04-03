web: envdir envdir django-admin.py runserver 0.0.0.0:8000

compass: compass watch --force --no-line-comments --output-style compressed --require less --sass-dir $PROJ/$APP/static/$APP/css --css-dir $PROJ/$APP/static/$APP/css --image-dir /static/ $PROJ/$APP/static/$APP/css/screen.scss

worker: envdir envdir django-admin.py rqworker high default low

store: envdir envdir django-admin.py rqworker store
