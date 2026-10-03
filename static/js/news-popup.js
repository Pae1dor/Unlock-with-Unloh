// Latest-news pop-up on the home page (rendered only for logged-in users).
// Shows on every visit to the home page. If the "ไม่แสดงอีกภายในวันนี้" box is ticked when it
// is closed (any way), it stays hidden until tomorrow for that user on this device (localStorage).
(function () {
  var pop = document.getElementById('news-pop');
  if (!pop) return;

  // Per user, so someone else logging in on the same device still gets it.
  var HIDE_KEY = 'newsPopupHideDate:' + pop.dataset.userId;

  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
  }
  try {
    if (localStorage.getItem(HIDE_KEY) === today()) return;
  } catch (e) { /* storage blocked: just show it */ }

  function open() {
    pop.hidden = false;
    pop.querySelector('.news-pop__close').focus({ preventScroll: true });
    document.addEventListener('keydown', onKey);
  }
  var hideToday = document.getElementById('news-pop-hide-today');

  function close() {
    if (hideToday.checked) {
      try { localStorage.setItem(HIDE_KEY, today()); } catch (e) { /* private mode etc. */ }
    }
    pop.classList.add('is-leaving');
    document.removeEventListener('keydown', onKey);
    setTimeout(function () { pop.hidden = true; pop.classList.remove('is-leaving'); }, 250);
  }
  function onKey(e) {
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowRight') goTo(current + 1);
    else if (e.key === 'ArrowLeft') goTo(current - 1);
  }

  pop.addEventListener('click', function (e) {
    if (e.target === pop || e.target.closest('[data-pop-close]')) close();
  });
  // Following an article with the box ticked counts too.
  pop.querySelectorAll('.news-pop__read').forEach(function (link) {
    link.addEventListener('click', function () {
      if (hideToday.checked) {
        try { localStorage.setItem(HIDE_KEY, today()); } catch (e) { /* private mode etc. */ }
      }
    });
  });

  // ---- swipe between news: the track is a CSS scroll-snap strip (native touch swipe);
  // arrows, dots and the counter just scroll it / follow it.
  var track = document.getElementById('news-pop-track');
  var slides = track.children;
  var dots = pop.querySelectorAll('[data-pop-go]');
  var count = document.getElementById('news-pop-count');
  var current = 0;

  function goTo(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    track.scrollTo({ left: i * track.clientWidth, behavior: 'smooth' });
  }
  function sync() {
    var i = Math.round(track.scrollLeft / track.clientWidth);
    if (i === current) return;
    current = i;
    dots.forEach(function (d, n) { d.classList.toggle('is-active', n === i); });
    if (count) count.textContent = (i + 1) + ' / ' + slides.length;
  }
  track.addEventListener('scroll', sync, { passive: true });
  pop.querySelectorAll('[data-pop-step]').forEach(function (btn) {
    btn.addEventListener('click', function () { goTo(current + Number(btn.dataset.popStep)); });
  });
  dots.forEach(function (d) {
    d.addEventListener('click', function () { goTo(Number(d.dataset.popGo)); });
  });

  // Wait for the after-login welcome screen to finish first.
  setTimeout(open, document.getElementById('welcome') ? 2000 : 450);
})();
