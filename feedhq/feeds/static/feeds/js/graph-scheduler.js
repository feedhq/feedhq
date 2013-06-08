(function($) {
    $(function() {
        var graph = $('#scheduler-graph');
        var url = graph.attr('data-url');
        $.get(url, function(data, status) {
            data = JSON.parse(data);

            var chart = d3.select('#scheduler-graph').append('svg')
            .attr('class', 'chart')
            .attr('width', '100%')
            .attr('height', '100px');

            chart.append('text')
            .attr('x', '80%')
            .attr('y', 20)
            .text('Time resolution: ' + (data.timespan / data.counts.length / 60).toFixed(2) + ' min');
            chart.append('text')
            .attr('x', '80%')
            .attr('y', 34)
            .text('Max count: ' + data.max);

            chart.append('text')
            .attr('x', '80%')
            .attr('y', 48)
            .text('Total jobs: ' + d3.sum(data.counts));

            chart.selectAll('rect')
            .data(data.counts)
            .enter().append('rect')
            .attr('x', function(d, i) {
                return i * 2;
            })
            .attr('y', function(d) {
                return Math.round(100 - 100 * d / data.max);
            })
            .attr('width', 2)
            .attr('height', function(d) {
                return Math.round(100 * d / data.max);
            });
        });
    });
})(django.jQuery);
