// Keep the "current prayer" highlight and "ละหมาดถัดไป" countdown live
// without a full page reload — poll a lightweight JSON endpoint on a timer.
(function () {
  var rows = document.querySelectorAll('[data-prayer-key]');
  if (!rows.length) return;

  // City is resolved server-side from the same cookie the page itself used,
  // so no need to pass it here.
  var nextName = document.getElementById('prayer-next-name');
  var nextTime = document.getElementById('prayer-next-time');

  function refresh() {
    fetch('/api/prayer-status')
      .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
      .then(function (data) {
        if (!data.ok) return;
        rows.forEach(function (row) {
          row.classList.toggle('is-now', row.getAttribute('data-prayer-key') === data.current);
        });
        if (nextName && data.next_name) nextName.textContent = data.next_name;
        if (nextTime && data.next_time) nextTime.textContent = data.next_time;
      })
      .catch(function () { /* keep last known state on a failed poll */ });
  }

  // The clock only needs rechecking once a minute; re-check sooner when the
  // tab regains focus so it doesn't look stale after being backgrounded.
  setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) refresh();
  });
})();
