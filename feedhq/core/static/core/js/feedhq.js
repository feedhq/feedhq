(function($) {
	$.extend($.fn, {
		hl: function() {
			hljs.initHighlightingOnLoad();
			$('pre').each(function(index, element) {
				hljs.highlightBlock(element, '    ', false)
			});
			return this;
		},
		keys: function() {
			$(document).keydown(function(e) {
				if (e.keyCode == 39) {
					var link = $('.feedhq-next');
				} else if (e.keyCode == 37) {
					var link = $('.feedhq-previous');
				} else {
					return;
				}
				var href = link.attr('href');
				if (href) {
					window.location.href = href;
				}
			});
			return this;
		},
		images: function() {
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
		},
	});
})(jQuery);

