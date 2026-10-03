// Loading feedback shared by every page: most pages call slow outside APIs
// (prayer times, Quran, maps) while rendering, so show that something is happening.
(function () {
  var bar = document.createElement('div');
  bar.className = 'page-progress';
  document.body.appendChild(bar);

  function start() {
    bar.classList.remove('is-active');
    void bar.offsetWidth; // restart the animation
    bar.classList.add('is-active');
  }

  function stop() {
    bar.classList.remove('is-active');
    document.querySelectorAll('.is-loading[data-ui-loading]').forEach(function (el) {
      setLoading(el, false);
    });
  }

  // Swap a button's content for a spinner; the original markup comes back when loading ends.
  function setLoading(btn, on) {
    if (on) {
      if (btn.classList.contains('is-loading')) return;
      btn.dataset.uiLoading = btn.innerHTML;
      btn.classList.add('is-loading');
      btn.setAttribute('aria-busy', 'true');
      var hasLabel = btn.textContent.trim() !== '';
      btn.innerHTML = '<span class="spinner" aria-hidden="true"></span>' +
        (hasLabel ? '<span>กำลังโหลด…</span>' : '');
    } else if (btn.dataset.uiLoading !== undefined) {
      btn.innerHTML = btn.dataset.uiLoading;
      delete btn.dataset.uiLoading;
      btn.classList.remove('is-loading');
      btn.removeAttribute('aria-busy');
    }
  }
  window.uiSetLoading = setLoading;

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
    var url = new URL(a.href, location.href);
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    start();
  });

  // Regular (non-AJAX) forms: spinner on the submit button + top bar.
  // Checked on the next tick so page scripts that preventDefault() (e.g. comments) are skipped.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    var btn = e.submitter || form.querySelector('[type=submit], button:not([type])');
    setTimeout(function () {
      if (e.defaultPrevented) return;
      if (btn) setLoading(btn, true);
      start();
    }, 0);
  });

  // Welcome screen after login: clear the one-shot cookie. The fade-out itself is
  // a CSS animation; here we only allow tap-to-skip and drop the element afterwards.
  var welcome = document.getElementById('welcome');
  if (welcome) {
    document.cookie = 'welcome=; max-age=0; path=/';
    welcome.addEventListener('click', function () { welcome.classList.add('is-leaving'); });
    welcome.addEventListener('animationend', function (e) {
      if (e.animationName === 'welcome-out') welcome.remove();
    });
  }

  // ---- prayer alerts (logged-in only): a missed prayer is announced once (the server
  // remembers), "time almost up" once per prayer per day (remembered on this device).
  if (document.body.hasAttribute('data-logged-in')) {
    var alertQueue = [];
    var alertShowing = false;

    var nextAlert = function () {
      if (alertShowing || !alertQueue.length) return;
      var a = alertQueue.shift();
      alertShowing = true;
      var el = document.createElement('a');
      el.className = 'prayer-alert prayer-alert--' + a.kind;
      el.href = a.href || '/prayer-times';
      el.setAttribute('role', 'alert');
      el.textContent = a.text;
      document.body.appendChild(el);
      setTimeout(function () {
        el.classList.add('is-leaving');
        setTimeout(function () { el.remove(); alertShowing = false; nextAlert(); }, 300);
      }, 5000);
    };

    var systemNotify = function (title, body, tag) {
      if (!('Notification' in window) || Notification.permission !== 'granted') return;
      var opts = { body: body, tag: tag, icon: '/static/img/icon-192.png' };
      if (navigator.serviceWorker && navigator.serviceWorker.getRegistration) {
        navigator.serviceWorker.getRegistration().then(function (reg) {
          if (reg) reg.showNotification(title, opts); else new Notification(title, opts);
        }).catch(function () {});
      } else {
        try { new Notification(title, opts); } catch (e) { /* not allowed here */ }
      }
    };

    var checkPrayerAlerts = function () {
      fetch('/api/prayer-log/alerts', { headers: { Accept: 'application/json' } })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
          if (!data) return;
          (data.rewards || []).forEach(function (r) {
            alertQueue.push({ kind: 'reward', text: '\ud83c\udf89 ละหมาดครบ 5 เวลา! ได้รับชุดใหม่ "' + r.name + '" แตะเพื่อใส่ชุด', href: '/profile/outfits' });
            systemNotify('ได้รับชุดใหม่!', 'ละหมาดครบ 5 เวลา ได้รับ "' + r.name + '"', 'reward-' + r.key);
          });
          (data.missed || []).forEach(function (m) {
            var text = 'คุณขาดละหมาด' + m.label + (m.yesterday ? 'เมื่อวาน' : 'วันนี้');
            alertQueue.push({ kind: 'missed', text: text });
            systemNotify('ขาดละหมาด' + m.label, text, 'missed-' + m.date + '-' + m.prayer);
          });
          var due = data.due_soon;
          if (due) {
            var key = 'dueSoonShown:' + new Date().toDateString() + ':' + due.prayer;
            var seen = null;
            try { seen = localStorage.getItem(key); } catch (e) { /* storage blocked */ }
            if (!seen) {
              try { localStorage.setItem(key, '1'); } catch (e) { /* storage blocked */ }
              var dueText = 'ใกล้หมดเวลา' + due.label + ' อีก ' + due.minutes_left + ' นาที';
              alertQueue.push({ kind: 'due', text: dueText });
              systemNotify('ใกล้หมดเวลา' + due.label, dueText, 'due-' + due.prayer);
            }
          }
          nextAlert();
        })
        .catch(function () { /* offline: try again next minute */ });
    };

    checkPrayerAlerts();
    setInterval(checkPrayerAlerts, 60000);
    window.uiCheckPrayerAlerts = checkPrayerAlerts; // e.g. right after a Quran listen logs a prayer
  }

  // Back/forward cache restores the old page with the bar still running.
  window.addEventListener('pageshow', stop);
})();
