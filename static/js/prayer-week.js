// Weekly prayer grid on /profile. The first week comes embedded in the page; the arrows
// fetch other weeks from /api/prayer-log/week, which never goes past this week.
// A dot whose prayer is in its on-time window (day.open, decided by the server) can be ticked:
// tap it, confirm, and POST /api/prayer-log; the server checks the window again.
(function () {
  var card = document.getElementById('prayer-week');
  var initial = document.getElementById('prayer-week-data');
  if (!card || !initial) return;

  var $ = function (id) { return document.getElementById(id); };
  var grid = $('pw-grid');
  var detail = $('pw-detail');
  var prevBtn = $('pw-prev');
  var nextBtn = $('pw-next');
  var week = null;
  var thisWeekStart = null;
  var busy = false;
  var confirming = false; // the ยืนยัน / ยกเลิก row is showing: a redraw would take it away
  var pendingMessage = null; // shown once after the next render (e.g. "saved")
  var HINT = 'แตะจุดเพื่อดูรายละเอียด';

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function isMissed(key, day) { return (day.missed || []).indexOf(key) !== -1; }
  function isOpen(key, day) { return (day.open || []).indexOf(key) !== -1; }

  function dotClass(entry, day, key) {
    if (day.is_future) return 'pl-dot is-future';
    if (!entry) {
      if (isOpen(key, day)) return 'pl-dot is-open';
      return isMissed(key, day) ? 'pl-dot is-missed' : 'pl-dot';
    }
    return 'pl-dot ' + (entry.status === 'qada' ? 'is-qada' : 'is-on-time') +
      (entry.source === 'checkin' || entry.source === 'quran' ? ' is-' + entry.source : '');
  }

  function describe(prayer, day) {
    var entry = day.prayers[prayer.key];
    var head = prayer.label + ' · ' + day.label + ' — ';
    if (day.is_future) return head + 'ยังไม่ถึงวันนี้';
    if (!entry) {
      if (isOpen(prayer.key, day)) return head + 'อยู่ในเวลาละหมาด บันทึกว่าละหมาดแล้ว?';
      return head + (isMissed(prayer.key, day) ? 'ขาด (เลยเวลาแล้ว)' : 'ยังไม่ได้บันทึก');
    }
    var parts = ['บันทึกเวลา ' + entry.time + ' น.', entry.status === 'qada' ? 'ชดเชย' : 'ทันเวลา'];
    if (entry.source === 'checkin') {
      parts.push(entry.mosque_name ? 'ญะมาอะฮ์ที่' + entry.mosque_name : 'เช็คอินที่มัสยิด');
    } else if (entry.source === 'quran') {
      parts.push('จากการฟังอัลกุรอาน');
    }
    return head + parts.join(' · ');
  }

  function render(data) {
    week = data;
    if (!thisWeekStart) thisWeekStart = data.start;
    var isThisWeek = data.start === thisWeekStart;

    $('pw-total').textContent = data.total + '/' + data.max;
    $('pw-total-label').textContent = isThisWeek ? 'สัปดาห์นี้' : 'สัปดาห์นั้น';
    $('pw-range').textContent = data.range;
    // A missed day simply restarts the count — the wording never scolds.
    $('pw-streak').textContent = data.streak > 0
      ? 'ครบ 5 เวลาต่อเนื่อง ' + data.streak + ' วัน'
      : 'เริ่มนับใหม่ได้ทุกวัน';
    prevBtn.disabled = false;
    nextBtn.disabled = !data.next;
    confirming = false;
    detail.textContent = pendingMessage || HINT;
    pendingMessage = null;

    grid.textContent = '';
    grid.appendChild(el('div', 'pw-corner'));
    data.days.forEach(function (day) {
      var head = el('div', 'pw-day' + (day.is_today ? ' is-today' : ''));
      head.appendChild(el('span', 'pw-day__wd', day.weekday));
      head.appendChild(el('span', 'pw-day__num', String(day.day)));
      grid.appendChild(head);
    });

    data.prayers.forEach(function (prayer, row) {
      grid.appendChild(el('div', 'pw-name', prayer.label));
      data.days.forEach(function (day) {
        var cell = el('div', 'pw-cell' + (day.is_today ? ' is-today' : '') +
          (row === data.prayers.length - 1 ? ' is-last' : ''));
        var dot = el('button', dotClass(day.prayers[prayer.key], day, prayer.key));
        dot.type = 'button';
        dot.setAttribute('aria-label', describe(prayer, day));
        var entry = day.prayers[prayer.key];
        dot.innerHTML = '<svg class="ico"><use href="#i-' +
          (entry && entry.source === 'quran' ? 'book' : 'mosque') + '"></use></svg>';
        dot.addEventListener('click', function () {
          grid.querySelectorAll('.pl-dot.is-selected').forEach(function (d) { d.classList.remove('is-selected'); });
          dot.classList.add('is-selected');
          if (!entry && isOpen(prayer.key, day)) showConfirm(prayer, day);
          else detail.textContent = describe(prayer, day);
        });
        cell.appendChild(dot);
        grid.appendChild(cell);
      });
    });
  }

  // "Prayed?" with ยืนยัน / ยกเลิก in the detail line, so a stray tap never logs anything.
  function showConfirm(prayer, day) {
    confirming = true;
    detail.textContent = describe(prayer, day);
    var row = el('span', 'pw-confirm');
    var yes = el('button', 'btn btn--sm', 'ยืนยัน');
    var no = el('button', 'btn btn--sm btn--ghost', 'ยกเลิก');
    yes.type = no.type = 'button';
    yes.addEventListener('click', function () { submit(prayer, yes, no); });
    no.addEventListener('click', function () {
      grid.querySelectorAll('.pl-dot.is-selected').forEach(function (d) { d.classList.remove('is-selected'); });
      confirming = false;
      detail.textContent = HINT;
    });
    row.appendChild(yes);
    row.appendChild(no);
    detail.appendChild(row);
  }

  function submit(prayer, yes, no) {
    if (busy) return;
    busy = true;
    yes.disabled = no.disabled = true;
    fetch('/api/prayer-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ prayer: prayer.key })
    })
      .then(function (res) {
        return res.json().catch(function () { return null; }).then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (r) {
        if (r.ok) {
          pendingMessage = 'บันทึก' + prayer.label + 'แล้ว';
          // the fifth prayer of a day may have earned an outfit: let ui.js announce it
          if (window.uiCheckPrayerAlerts) setTimeout(window.uiCheckPrayerAlerts, 800);
        } else {
          var info = r.body && r.body.detail;
          pendingMessage = (info && info.message) || 'บันทึกไม่สำเร็จ ลองใหม่อีกครั้ง';
        }
        load(week.start); // either way the grid is redrawn from the server's view
      })
      .catch(function () {
        detail.textContent = 'บันทึกไม่สำเร็จ ตรวจสอบการเชื่อมต่อแล้วลองใหม่';
        yes.disabled = no.disabled = false;
      })
      .then(function () { busy = false; });
  }

  function load(start) {
    prevBtn.disabled = nextBtn.disabled = true;
    card.classList.add('is-loading-week');
    fetch('/api/prayer-log/week?start=' + encodeURIComponent(start))
      .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
      .then(render)
      .catch(function () {
        detail.textContent = 'โหลดข้อมูลไม่สำเร็จ ลองใหม่อีกครั้ง';
        prevBtn.disabled = false;
        nextBtn.disabled = !(week && week.next);
      })
      .then(function () { card.classList.remove('is-loading-week'); });
  }

  prevBtn.addEventListener('click', function () { if (week) load(week.prev); });
  nextBtn.addEventListener('click', function () { if (week && week.next) load(week.next); });

  // Windows open and close while the page sits in a tab: redraw when it comes back.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && week && !busy && !confirming) load(week.start);
  });

  render(JSON.parse(initial.textContent));
})();
