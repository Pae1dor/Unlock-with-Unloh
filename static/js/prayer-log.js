// Prayer log circles on /prayer-times are status only: a prayer is ticked on the /profile
// grid or by a mosque check-in. This just keeps the rows' locked/unlocked look current while the page is open.
(function () {
  var dots = Array.prototype.slice.call(document.querySelectorAll('.pl-dot[data-prayer]'));
  if (!dots.length) return;

  // Today's date in Asia/Bangkok (the server's day), not the device's own time zone.
  function bangkokDay() {
    try { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok' }).format(new Date()); }
    catch (e) { return new Date().toDateString(); }
  }
  var pageDay = bangkokDay();

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

  // After midnight the page shows yesterday, and a check-in may have ticked something: reload.
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) return;
    if (bangkokDay() !== pageDay) window.location.reload();
    else unlockDue();
  });
})();
