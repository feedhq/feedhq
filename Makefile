proj = feedhq
django = python $(CURDIR)/manage.py


test:
	@$(django) test --failfast --noinput

run:
	@foreman start

db:
	@$(django) syncdb --noinput

user:
	@$(django) createsuperuser

shell:
	@$(django) shell

dbshell:
	@$(django) dbshell

updatefeeds:
	@$(django) updatefeeds

favicons:
	@$(django) favicons

makemessages:
	@cd $(proj) && $(django) makemessages -a

compilemessages:
	@cd $(proj) && $(django) compilemessages

txpush:
	@tx push -s

txpull:
	@tx pull -a

coverage:
	@envdir tests/envdir coverage run `which django-admin.py` test
	@coverage html

compress:
	@cd $(proj)/core/static/core/js && closure \
		--js fastclick.js \
		--js jquery.min.js \
		--js bootstrap-tooltip.js \
		--js bootstrap-modal.js \
		--js mousetrap.min.js \
		--js highlight.min.js \
		--js feedhq.js \
		--js_output_file bundle.min.js

.PHONY: test run db user shell dbshell updatefeeds favicons \
	      makemessages compilemessages txpush txpull coverage compress
