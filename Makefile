proj = feedhq
settings = --settings=$(proj).settings
test_settings = --settings=$(proj).test_settings


test:
	@django-admin.py test $(test_settings) --failfast --noinput

run:
	@foreman start

db:
	@django-admin.py syncdb --noinput $(settings)

user:
	@django-admin.py createsuperuser $(settings)

shell:
	@django-admin.py shell $(settings)

dbshell:
	@django-admin.py dbshell $(settings)

updatefeeds:
	@django-admin.py updatefeeds $(settings)

favicons:
	@django-admin.py favicons $(settings)

makemessages:
	@cd $(proj) && django-admin.py makemessages -a $(settings)

compilemessages:
	@cd $(proj) && django-admin.py compilemessages $(settings)

txpush:
	@tx push -s

txpull:
	@tx pull -a

.PHONY: test run db user shell dbshell updatefeeds favicons \
	      makemessages compilemessages txpush txpull
