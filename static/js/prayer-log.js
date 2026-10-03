// Prayer log circles on /prayer-times are status only: a prayer is ticked by listening to the
// Quran during its time (static/js/quran-player.js -> /api/prayer-log/listen) or by a mosque
// check-in. This just keeps the rows' locked/unlocked look current while the page is open.
(function () {
  var dots = Array.prototype.slice.call(document.querySelectorAll('.pl-dot[data-prayer]'));
  if (!dots.length) return;

  var pageDay = new Date().toDateString();

  function unlockDue() {
    var now = Date.now();
    dots.forEach(function (dot) {
      var row = dot.closest('.prayer-list__row');
      var starts = Number(dot.dataset.starts || 0);
      if (row && row.classList.contains('is-locked') && starts && starts <= now) {
        row.classList.remove('is-locked');
      }
    });
  }
  setInterval(unlockDue, 30000);

  // After midnight the page shows yesterday, and a listen may have ticked something: reload.
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) return;
    if (new Date().toDateString() !== pageDay) window.location.reload();
    else unlockDue();
  });
})();
