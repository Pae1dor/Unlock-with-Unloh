// Prayer log circles on /prayer-times: one tap marks that prayer (no popup), then a
// "บันทึกแล้ว · ยกเลิก" toast for 5 seconds. On time / qada is decided by the server.
(function () {
  var dots = Array.prototype.slice.call(document.querySelectorAll('.pl-dot[data-prayer]'));
  if (!dots.length) return;

  var countEl = document.getElementById('pl-count');
  var toast = document.getElementById('pl-toast');
  var toastText = document.getElementById('pl-toast-text');
  var toastSep = document.getElementById('pl-toast-sep');
  var undoBtn = document.getElementById('pl-toast-undo');
  var toastTimer = null;
  var undoPrayer = null;
  // Today's date in Asia/Bangkok (the server's day), not the device's own time zone.
  function bangkokDay() {
    try { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok' }).format(new Date()); }
    catch (e) { return new Date().toDateString(); }
  }
  var pageDay = bangkokDay();

  function setCount(n) { if (countEl) countEl.textContent = n; }

  function showToast(text, prayer) {
    toastText.textContent = text;
    undoPrayer = prayer || null;
    undoBtn.hidden = toastSep.hidden = !prayer;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, 5000);
  }

  function hideToast() {
    toast.hidden = true;
    undoPrayer = null;
  }

  function dotFor(prayer) {
    return dots.filter(function (d) { return d.dataset.prayer === prayer; })[0];
  }

  function paint(dot, entry) {
    dot.classList.remove('is-on-time', 'is-qada', 'is-checkin');
    if (entry) {
      dot.classList.add(entry.status === 'qada' ? 'is-qada' : 'is-on-time');
      if (entry.source === 'checkin') dot.classList.add('is-checkin');
      dot.disabled = true;
      dot.setAttribute('aria-label', 'บันทึก' + dot.dataset.name + 'แล้ว');
    } else {
      dot.disabled = false;
      dot.setAttribute('aria-label', 'บันทึกละหมาด' + dot.dataset.name);
    }
  }

  function send(method, url, body) {
    return fetch(url, {
      method: method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw (data.detail && data.detail.message) || 'บันทึกไม่สำเร็จ ลองใหม่อีกครั้ง';
        return data;
      });
    });
  }

  dots.forEach(function (dot) {
    dot.addEventListener('click', function () {
      if (dot.disabled || dot.classList.contains('is-busy')) return;
      dot.classList.add('is-busy');
      send('POST', '/api/prayer-log', { prayer: dot.dataset.prayer })
        .then(function (entry) {
          paint(dot, entry);
          setCount(entry.today_count);
          showToast('บันทึกแล้ว', entry.source === 'manual' ? entry.prayer : null);
        })
        .catch(function (msg) { showToast(typeof msg === 'string' ? msg : 'บันทึกไม่สำเร็จ ลองใหม่อีกครั้ง'); })
        .then(function () { dot.classList.remove('is-busy'); });
    });
  });

  undoBtn.addEventListener('click', function () {
    var prayer = undoPrayer;
    if (!prayer) return;
    hideToast();
    send('DELETE', '/api/prayer-log/' + prayer)
      .then(function (data) {
        var dot = dotFor(prayer);
        if (dot) paint(dot, null);
        setCount(data.today_count);
      })
      .catch(function (msg) { showToast(typeof msg === 'string' ? msg : 'ยกเลิกไม่สำเร็จ'); });
  });

  // Unlock a row once its prayer time arrives (the server checks again on tap).
  function unlockDue() {
    var now = Date.now();
    dots.forEach(function (dot) {
      var row = dot.closest('.prayer-list__row');
      var starts = Number(dot.dataset.starts || 0);
      if (row && row.classList.contains('is-locked') && starts && starts <= now) {
        row.classList.remove('is-locked');
        if (!dot.classList.contains('is-on-time') && !dot.classList.contains('is-qada')) paint(dot, null);
      }
    });
  }
  setInterval(unlockDue, 30000);

  // Only today can be logged: after midnight the page shows yesterday, so reload it.
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) return;
    if (bangkokDay() !== pageDay) window.location.reload();
    else unlockDue();
  });
})();
