# coding: utf-8
import datetime

extensions = []
templates_path = []

source_suffix = '.rst'

master_doc = 'index'

project = u'FeedHQ'
copyright = u'2013-{0}, Bruno Renié'.format(datetime.datetime.today().year)

# The short X.Y version.
version = '1.0'
# The full version, including alpha/beta/rc tags.
release = '1.0'

exclude_patterns = ['_build']

pygments_style = 'sphinx'

html_theme = 'default'

html_static_path = []

htmlhelp_basename = 'FeedHQdoc'

latex_elements = {
}

latex_documents = [
    ('index', 'FeedHQ.tex', u'FeedHQ Documentation',
     u'Bruno Renié', 'manual'),
]

man_pages = [
    ('index', 'feedhq', u'FeedHQ Documentation',
     [u'Bruno Renié'], 1)
]

texinfo_documents = [
    ('index', 'FeedHQ', u'FeedHQ Documentation',
     u'Bruno Renié', 'FeedHQ', 'One line description of project.',
     'Miscellaneous'),
]
