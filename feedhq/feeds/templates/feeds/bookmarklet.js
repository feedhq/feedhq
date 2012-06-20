(function() {{% if user.is_authenticated %}
	var html = document.head.innerHTML
	, source = window.location.toString()
	, url = '{{ scheme }}://{{ site.domain }}{% url "feeds:bookmarklet_subscribe" %}'
	, form = document.createElement('form');

	form.setAttribute('action', url);
	form.setAttribute('enctype', 'application/x-www-form-urlencoded');
	form.setAttribute('method', 'post');
	var inputs = {
		source: source,
		html: html,
	}
	for (input in inputs) {
		var form_input = document.createElement('input');
		form_input.setAttribute('type', 'hidden');
		form_input.setAttribute('name', input);
		form_input.setAttribute('value', inputs[input])
		form.appendChild(form_input);
	}
	document.body.appendChild(form);

	window.setTimeout(function() {
		form.submit();
	}, 50);{% else %}
	window.location = '{{ scheme }}://{{ site.domain }}{% url "login" %}?from=bookmarklet';
{% endif %}})();
