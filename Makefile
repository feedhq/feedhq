proj = feedhq
django = envdir $(CURDIR)/envdir django-admin.py
testdjango = envdir $(CURDIR)/tests/envdir django-admin.py


test:
	@$(testdjango) test --failfast --noinput

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
	@envdir tests/envdir coverage run --source=feedhq `which django-admin.py` test
	@coverage html

.PHONY: test run db user shell dbshell updatefeeds favicons \
	      makemessages compilemessages txpush txpull coverage
