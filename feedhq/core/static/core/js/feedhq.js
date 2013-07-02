/**
 * @preserve FeedHQ
 */
(function($) {
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
		keys: function() {
			var view = $('body').data('view');
			console.log(view);

			Mousetrap.bind('?', function() {
				$('#keyboard').modal('show');
				window.location.hash = 'keyboard';
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

			Mousetrap.bind('g h', function() {
				$('#header a.home')[0].click();
				return false;
			});

			Mousetrap.bind('g a', function() {
				window.location.pathname = $($('#header a.home')[0]).data('all');
				return false;
			});

			Mousetrap.bind('g u', function() {
				window.location.pathname = $($('#header a.home')[0]).data('unread');
				return false;
			});

			Mousetrap.bind('g s', function() {
				$('li a.starred')[0].click();
				return false;
			});

			Mousetrap.bind('g d', function() {
				$('li a.dashboard')[0].click();
				return false;
			});

			Mousetrap.bind('g m', function() {
				$('li a.manage')[0].click();
				return false;
			});

			Mousetrap.bind('a', function() {
				$('li a.subscription')[0].click();
				return false;
			});

			Mousetrap.bind('r', function() {
				window.location.reload();
				return false;
			});

			if (view === 'list') {
				Mousetrap.bind('shift+a', function() {
					$('form#read').submit();
					return false;
				});

				Mousetrap.bind('enter', function() {
					window.location.pathname = $('.entry').first().find('a').last().attr('href');
					return false
				});
			}

			if (view === 'detail') {
				var navigate = function(target) {
					var link = $('.feedhq-' + target);
					if (link && link.attr('href')) {
						window.location.href = link.attr('href');
					}
				}

				Mousetrap.bind(['k', 'left', 'up'], function() {
					navigate('previous');
					return false;
				});

				Mousetrap.bind(['j', 'right', 'down'], function() {
					navigate('next');
					return false;
				});

				Mousetrap.bind('s', function() {
					$('form#star').submit();
					return false;
				});

				Mousetrap.bind('e', function() {
					$('.actions .email')[0].click();
					return false;
				});

				Mousetrap.bind('m', function() {
					$('form#unread').submit();
					return false;
				});

				Mousetrap.bind('v', function() {
					window.open($('.date a').attr('href'), '_blank');
					return false;
				});

				Mousetrap.bind('t', function() {
					$('.actions .twitter')[0].click();
					return false;
				});

				Mousetrap.bind('+', function() {
					$('.actions .gplus')[0].click();
					return false;
				});

				Mousetrap.bind('i', function() {
					$('form#read-later').submit();
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

		$(document).hl().images().keys();

		$('#shortcuts').click(function() {
			$('#keyboard').modal('show');
			window.location.hash = 'keyboard';
			return false;
		});
	});
})(jQuery);
