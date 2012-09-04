(function($) {
	var POLL_INTERVAL = 2500;

	var error = function(xhr, textStatus, errorThrown) {
		var html = $('script[name=error-row]').html()

		var tbody = $('#queues tbody');
		tbody.empty();
		tbody.append(html)

		var tbody = $('#workers tbody');
		tbody.empty();
		tbody.append(html)
	}

	var success = function(data, textStatus, xhr) {
		if (textStatus != 'success') {
			return;
		}

		var tbody = $('#queues tbody');
		tbody.empty();

		if (data.queues.length > 0) {
			var template = _.template($('script[name=queue-row]').html());

			$.each(data.queues, function(i, queue) {
				queue.klass = i % 2 == 0 ? 'row2' : 'row1';
				var html = template(queue);
				tbody.append($(html));
			});
		} else {
			tbody.append($('script[name=no-queue-row]').html())
		}

		var tbody = $('#workers tbody');
		tbody.empty();

		if (data.workers.length > 0) {
			var template = _.template($('script[name=worker-row]').html())

			$.each(data.workers, function(i, worker) {
				worker.klass = i % 2 == 0 ? 'row2' : 'row1';
				worker.queues = worker.queues.join(', ');
				var html = template(worker);
				tbody.append($(html));
			});
		} else {
			tbody.append($('script[name=no-worker-row]').html())
		}
	};

	var refresh = function() {
		$.ajax({
			url: window.location.href,
			dataType: 'json',
			success: success,
			error: error,
		});
	};

	$(document).ready(function() {
		setInterval(refresh, POLL_INTERVAL);
	});
})($)
