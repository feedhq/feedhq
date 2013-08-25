/**
 * @preserve FeedHQ
 */
(function($) {
	var load_kb_modal = function() {
		var kb = $('#keyboard')
		kb.modal('show');
		window.location.hash = 'keyboard';

		if (kb.find('.modal-header').length === 0) {
			kb.load(kb.data('url'));
		}

		kb.on('hidden', function() {
			if ('replaceState' in history) {

				history.replaceState(null, {}, window.location.href.split('#')[0]);
			} else {
				window.location.hash = '';
			}
		});
	};
	$.extend($.fn, {
		hl: function() {
			if (!$('.feedhq-highlight')) {
				return this;
			}
			hljs.initHighlightingOnLoad();
			$('pre').each(function(index, element) {
				hljs.highlightBlock(element, '	', false)
			});
			return this;
		},
		more: function() {
			if (!$('.feedhq-more')) {
				return this;
			}
			$('.feedhq-more').click(function(event) {
				event.preventDefault();
				var link = $(this),
					container = $('#entries'),
					pages = $('#id_pages');
				var parsed_pages = $.parseJSON(pages.val());
				link.text(link.attr('loading'));
				$.get(link.attr('href'), function(fragment) {
					$(fragment).appendTo(container);
					var include = $('<div>').append(fragment).find('.entries-include');
					var next = include.attr('next');
					if (typeof next == "undefined") {
						link.remove();
					} else {
						link.attr('href', next);
						link.text(link.attr('title'));
					}
					parsed_pages.push(parseInt(include.attr('page')));
					pages.val(JSON.stringify(parsed_pages));
				});
				return this;
			});
			return this;
		},
		keys: function() {
			var view = $('body').data('view');

			Mousetrap.bind('?', function() {
				load_kb_modal();
				return false;
			});

			Mousetrap.bind('esc', function() {
				$('#keyboard').modal('hide');
				return false;
			});

			Mousetrap.bind('up up down down left right left right b a', function() {
				window.open('http://www.youtube.com/watch?v=dQw4w9WgXcQ', '_blank');
				return false;
			});

			$('[data-mousetrap]').each(function() {
				var self = $(this);
				Mousetrap.bind(self.data('mousetrap').split(','), function() {
					window.foo = self;
					var tagName = self.prop('tagName');
					if (tagName === 'A') {
						self[0].click();
					} else if (tagName === 'FORM') {
						self.submit();
					}
					return false;
				});
			});

			Mousetrap.bind('g a', function() {
				window.location.pathname = $($('#header a.home')[0]).data('all');
				return false;
			});

			Mousetrap.bind('g u', function() {
				window.location.pathname = $($('#header a.home')[0]).data('unread');
				return false;
			});

			Mousetrap.bind('r', function() {
				window.location.reload();
				return false;
			});

			if (view === 'detail') {
				var navigate = function(target) {
					var link = $('.feedhq-' + target);
					if (link && link.attr('href')) {
						window.location.href = link.attr('href');
					}
				}

				Mousetrap.bind('v', function() {
					window.open($('.date a').attr('href'), '_blank');
					return false;
				});
			}

			return this;
		},
		images: function() {
			if (!$('.feedhq-images')) {
				return this;
			}
			var timer;
			$(document).on('scroll feedhq-loaded mousemove', function() {
				$('.feedhq-image .imgmenu').fadeIn(function() {
					if (timer) {
						window.clearTimeout(timer);
					}

					timer = window.setTimeout(function() {
						$('.feedhq-image .imgmenu').fadeOut();
					}, 2000);
				});
			});

			$(document).bind('feedhq-loaded', function() {
				$('.feedhq-image .imgmenu a').click(function() {
					var link = $(this);
					if (link.hasClass('selected')) {
						return false;
					}
					link.parent().find('.selected').removeClass('selected');
					link.addClass('selected');
					link.parent().parent().find('img').each(function() {
						var image = $(this);
						if (link.hasClass('zoom1')) {
							image.width('auto');
						};

						if (link.hasClass('fit')) {
							image.width('100%');
						};

						if (link.hasClass('retina')) {
							image.width(parseInt(image.attr('data-width')) / 2);
						};
					});
					return false;
				});
			});

			var entry_width = function() {
				return $('#entry').width();
			};

			var retina = window.devicePixelRatio >= 1.5;

			var images = $('.content img');
			var count = images.length;

			images.one('load', function() {
				var image = $(this);
				var tmp = new Image();
				tmp.src = image.attr('src');
				if (tmp.width <= entry_width()) {
					if (!--count) {
						$(document).trigger('feedhq-loaded');
					}
					return;
				}

				var menu_items = [$('<a class="zoom1" href="#"><span class="text">1:1</span></a>'), $('<a class="fit selected" href="#"><span class="icon-fullscreen"></span></a>')];

				if (retina) {
					menu_items.push($('<a class="retina" href="#"><span class="icon-eye-open"></span></a>'));
				}

				if (image.parent('a').length > 0) {
					image = image.parent('a');
				}
				var inner = $(image).clone().wrap('<p>').parent().html()
				var container = $('<div class="feedhq-image"></div>');
				var menu = $('<div class="imgmenu"></div>');
				for (var index in menu_items) {
					menu.append(menu_items[index]);
				}
				container.append(menu);
				container.append(inner);
				container.find('img').each(function() {
					var image = $(this);
					image.removeAttr('width');
					image.removeAttr('height');
					var tmp = new Image();
					tmp.src = image.attr('src');
					$(tmp).load(function() {
						image.attr('data-width', this.width);
					});
					image.width('100%');
					--count;
				});
				image.replaceWith(container);
				if (!count) {
					$(document).trigger('feedhq-loaded');
				}
			}).each(function() {
				if (this.complete) {
					$(this).load();
				}
			});
			return this;
		}
	});
	$(function() {
		setTimeout(function() {
			if (window.pageYOffset === 0) {
				window.scrollTo(0, 1);
			}
		}, 0);

		new FastClick(document.body);

		var touchDevice = 'ontouchstart' in document.documentElement;

		if (!touchDevice) {
			$('.tultip').tooltip();
		}

		$('#navigation .profile').click(function() {
			return false;
		});

		$(document).hl().images().keys().more();

		$('#shortcuts').click(function() {
			load_kb_modal();
			return false;
		});
	});
})(jQuery);
