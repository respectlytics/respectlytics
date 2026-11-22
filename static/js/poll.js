// Waiting for something to happen on the server (an app's first event, a first connection):
// checks every 3 seconds for the first 2 minutes, when it is most likely to happen, then every
// 15 seconds until 10 minutes, then every minute, and stops after half an hour. Never in a hidden
// tab: it checks again the moment the tab is shown. `check` returns true (or a promise of it) once
// it is done; `onGiveUp` runs when the half hour is over.
(function () {
    var SCHEDULE = [[2 * 60 * 1000, 3000], [10 * 60 * 1000, 15000], [Infinity, 60000]];
    window.pollUntil = function (check, options) {
        options = options || {};
        var started = Date.now();
        var limit = options.stopAfter || 30 * 60 * 1000;
        var timer = null, stopped = false, running = false;
        function delay() {
            var elapsed = Date.now() - started;
            for (var i = 0; i < SCHEDULE.length; i++) {
                if (elapsed < SCHEDULE[i][0]) return SCHEDULE[i][1];
            }
            return 60000;
        }
        function next() {
            if (!stopped) timer = setTimeout(tick, delay());
        }
        function tick() {
            timer = null;
            if (stopped || running) return;
            if (Date.now() - started > limit) {
                stopped = true;
                if (options.onGiveUp) options.onGiveUp();
                return;
            }
            if (document.hidden) return;  // the visibility listener picks it up again
            running = true;
            Promise.resolve().then(check).then(function (done) {
                running = false;
                if (done) { stopped = true; } else { next(); }
            }, function () { running = false; next(); });
        }
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden && !stopped && !running) { clearTimeout(timer); tick(); }
        });
        next();
        return { stop: function () { stopped = true; clearTimeout(timer); } };
    };
})();
