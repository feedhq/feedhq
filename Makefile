JSHINT=node_modules/.bin/jshint
JSHINTFLAGS=

UGLIFY=node_modules/.bin/uglifyjs
UGLIFYFLAGS=

proj = feedhq
django = python $(CURDIR)/manage.py

test:
	@$(django) test --failfast --noinput

run:
	@foreman start

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

# Asset management
# ----------------

# SASS files
scss_files = $(shell find scss -name '*.scss')

# CSS target
css = "feedhq/core/static/core/css/screen.css"

# Internal files that we want to jshint
core_js_files = $(shell find js -name '*.js' | grep -v '\.min\.js')

# JS target (concat+minify)
bundle = "feedhq/core/static/core/js/bundle.min.js"

# JS source files
js_files = $(shell find vendor js -name '*.js')

jshint: $(core_js_files)
	$(JSHINT) $(JSHINTFLAGS) $(core_js_files)

watch:
	watchman watch $(shell pwd)
	watchman -- trigger $(shell pwd) remake -X $(bundle) -I *.js -I *.scss -- make assets

$(bundle): $(js_files)
	@$(UGLIFY) $(UGLIFYFLAGS) \
		vendor/fastclick.js \
		vendor/jquery.min.js \
		vendor/bootstrap-tooltip.js \
		vendor/bootstrap-modal.js \
		vendor/mousetrap.min.js \
		vendor/highlight.min.js \
		vendor/hammer.min.js \
		js/feedhq.js \
		> $@

$(css): $(scss_files)
	@compass compile

npm:
	@npm install

assets: npm jshint $(bundle) $(css)

.PHONY: \
	test run makemessages compilemessages txpush txpull coverage jshint npm
