// Whole-surah playback: one shared <audio> element advances ayah by ayah,
// driven by the bottom-tab FAB (progress ring) and the sticky audio bar.
(function () {
  var list = document.getElementById('ayah-list');
  if (!list) return;

  var ayahs = Array.prototype.slice.call(list.querySelectorAll('.ayah')).filter(function (el) {
    return el.getAttribute('data-audio');
  });
  if (!ayahs.length) return;

  var audio = new Audio();
  var current = -1; // index into `ayahs`
  var playing = false;

  var fabBtn = document.getElementById('fab-play-toggle');
  var fabIcon = document.getElementById('fab-play-icon');
  var fabProgress = document.getElementById('fab-progress-ring');
  var CIRCUMFERENCE = 188.5;

  var bar = document.getElementById('audio-bar');
  var barBtn = document.getElementById('audio-bar-toggle');
  var barIcon = document.getElementById('audio-bar-icon');
  var barAyah = document.getElementById('audio-bar-ayah');
  var barFill = document.getElementById('audio-bar-fill');

  function setIcons(isPlaying) {
    var href = isPlaying ? '#i-pause' : '#i-play';
    if (fabIcon) fabIcon.querySelector('use').setAttribute('href', href);
    if (barIcon) barIcon.querySelector('use').setAttribute('href', href);
  }

  function updateProgress(withinAyahFraction) {
    var done = current < 0 ? 0 : current + (withinAyahFraction || 0);
    var ratio = Math.min(1, done / ayahs.length);
    if (fabProgress) fabProgress.style.strokeDashoffset = String(CIRCUMFERENCE * (1 - ratio));
    if (barFill) barFill.style.width = (ratio * 100).toFixed(1) + '%';
  }

  function highlightCurrent() {
    ayahs.forEach(function (el) { el.classList.remove('is-playing'); });
    if (current >= 0) {
      var el = ayahs[current];
      el.classList.add('is-playing');
      if (barAyah) barAyah.textContent = 'อายะฮ์ ' + el.querySelector('.ayah__num').textContent + ' / ' + ayahs.length;
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function loadAndPlay(index) {
    if (index < 0 || index >= ayahs.length) {
      playing = false;
      current = -1;
      setIcons(false);
      updateProgress(0);
      highlightCurrent();
      return;
    }
    current = index;
    audio.src = ayahs[current].getAttribute('data-audio');
    audio.play().catch(function () { playing = false; setIcons(false); });
    playing = true;
    if (bar) bar.hidden = false;
    setIcons(true);
    highlightCurrent();
    updateProgress(0);
  }

  function togglePlay() {
    if (playing) {
      audio.pause();
      playing = false;
      setIcons(false);
      return;
    }
    if (current === -1) {
      loadAndPlay(0);
    } else {
      audio.play().catch(function () {});
      playing = true;
      setIcons(true);
      if (bar) bar.hidden = false;
    }
  }

  audio.addEventListener('timeupdate', function () {
    if (!audio.duration) return;
    updateProgress(audio.currentTime / audio.duration);
  });

  audio.addEventListener('ended', function () {
    loadAndPlay(current + 1);
  });

  // Listening during a prayer's time ticks that prayer in the prayer log (server decides
  // which one, and ignores it outside prayer times or when logged out). Needs a short
  // real listen so an accidental tap doesn't count; reported once per page.
  var LISTEN_SECONDS = 10;
  var listened = 0;
  var lastTick = null;
  var reported = false;

  audio.addEventListener('timeupdate', function () {
    if (reported) return;
    var t = audio.currentTime;
    if (lastTick !== null && t > lastTick && t - lastTick < 2) listened += t - lastTick;
    lastTick = t;
    if (listened >= LISTEN_SECONDS) {
      reported = true;
      reportListen();
    }
  });
  audio.addEventListener('emptied', function () { lastTick = null; }); // next ayah starts at 0

  function reportListen() {
    fetch('/api/prayer-log/listen', { method: 'POST' })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (data && data.logged && data.created) {
          listenToast('บันทึกละหมาด' + data.label + 'แล้ว จากการฟังอัลกุรอาน');
          // a fifth prayer may have earned an outfit: let ui.js announce it now
          if (window.uiCheckPrayerAlerts) setTimeout(window.uiCheckPrayerAlerts, 4500);
        }
      })
      .catch(function () { /* offline etc.: nothing to tell */ });
  }

  function listenToast(text) {
    var toast = document.createElement('div');
    toast.className = 'pl-toast';
    toast.setAttribute('role', 'status');
    toast.textContent = '\u2713 ' + text;
    document.body.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 4000);
  }

  if (fabBtn) fabBtn.addEventListener('click', togglePlay);
  if (barBtn) barBtn.addEventListener('click', togglePlay);

  ayahs.forEach(function (el, index) {
    el.style.cursor = 'pointer';
    el.addEventListener('click', function () { loadAndPlay(index); });
  });
})();
