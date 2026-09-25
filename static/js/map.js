// Mosque finder: mosques from OpenStreetMap, served by our backend.
// Two modes:
//   'near' — "มัสยิดใกล้ฉัน": the 10 mosques closest to the visitor (/api/mosques/nearest),
//            wherever they are; the map is fitted to show the visitor and all 10.
//   'bbox' — whatever the map shows (/api/mosques/nearby). Entered as soon as the visitor
//            drags/zooms the map themselves, or picks an area in the search.
// The markers and the list are both rendered from the one `mosques` array, so they
// always contain the same mosques.
// Check-in ("เช็คอิน") buttons sit in each row and popup; the server (/api/checkins)
// decides — it checks the distance with its own mosque coordinates and the prayer window.
(function () {
  var mapEl = document.getElementById('map');
  if (!mapEl || typeof L === 'undefined') return;

  var MIN_ZOOM = 10;
  var USER_ZOOM = 14;
  var MOVE_DEBOUNCE_MS = 500;
  var SEARCH_DEBOUNCE_MS = 400;
  var REQUEST_TIMEOUT_MS = 45000;   // the server may try 3 Overpass mirrors x 10 s
  var CHECK_IN_RADIUS_M = 100;
  var NEAREST_COUNT = 10;
  var MAX_MOSQUE_SUGGESTIONS = 5;
  var BANGKOK = [13.7563, 100.5018];
  var CONSENT_KEY = 'mosqueFinder.geoConsent';      // localStorage: 'yes' after อนุญาต
  var DISMISSED_KEY = 'mosqueFinder.geoDismissed';  // sessionStorage: 'yes' after ไม่ตอนนี้
  var LOGGED_IN = mapEl.dataset.loggedIn === 'true';
  var CHECKIN_REFRESH_MS = 60000;   // windows open/close by the minute
  var MAX_STATUS_IDS = 100;

  var map = L.map('map').setView(BANGKOK, 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);
  var markerLayer = L.layerGroup().addTo(map);

  var listEl = document.getElementById('mosque-list');
  var statusEl = document.getElementById('mosque-status');
  var statusText = document.getElementById('mosque-status-text');
  var retryBtn = document.getElementById('mosque-retry');
  var staleEl = document.getElementById('mosque-stale');
  var noteEl = document.getElementById('geo-note');
  var toastEl = document.getElementById('checkin-toast');
  var searchWrap = document.getElementById('mosque-search-wrap');
  var searchInput = document.getElementById('mosque-search');
  var suggestEl = document.getElementById('mosque-suggest');

  // { id: "node/123" | "way/456" | "relation/789", name, lat, lng, dist (metres, or null) }
  // The OSM "type/id" is the key check-ins are stored under.
  var mosques = [];
  var markersById = {};
  var checkinStatus = {};      // osm id -> {state, label, message, ...} from /api/checkins/status
  var checkinButtons = {};     // osm id -> [row button, popup button]
  var checkinBusy = false;
  var mode = 'bbox';           // 'near' | 'bbox' (see top of file)
  var userPos = null;          // [lat, lng] once geolocation succeeds
  var userAccuracy = null;     // metres
  var userMarker = null;
  var inflight = null;         // AbortController of the data request in progress
  var moveTimer = null;
  var query = '';              // text in the search box (filters the dropdown only)

  function storage(kind) {
    try { return window[kind]; } catch (e) { return null; }
  }
  function readFlag(kind, key) {
    try { var s = storage(kind); return !!s && s.getItem(key) === 'yes'; } catch (e) { return false; }
  }
  function writeFlag(kind, key) {
    try { var s = storage(kind); if (s) s.setItem(key, 'yes'); } catch (e) { /* private mode etc. */ }
  }

  // ---------- status line (loading / zoom in / error + retry) ----------
  function setStatus(text, withRetry) {
    statusText.textContent = text || '';
    retryBtn.hidden = !withRetry;
    statusEl.hidden = !text;
  }
  retryBtn.addEventListener('click', function () {
    if (mode === 'near') loadNearest(); else loadVisibleArea();
  });

  // ---------- data: our backend ----------
  // GET `url`, then hand the mosques to `onData`; a newer request (or a mode change)
  // supersedes this one, and a failure shows the retry button without breaking the page.
  function request(url, onData) {
    if (inflight) { inflight.superseded = true; inflight.abort(); }
    var ctrl = new AbortController();
    inflight = ctrl;
    var timer = setTimeout(function () { ctrl.abort(); }, REQUEST_TIMEOUT_MS);
    if (!mosques.length) setStatus('กำลังโหลดมัสยิด…');

    fetch(url, { signal: ctrl.signal, headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (ctrl.superseded) return;
        mosques = (data.mosques || []).map(function (m) {
          return { id: m.id, name: m.name, lat: m.lat, lng: m.lng, dist: null };
        });
        staleEl.hidden = !data.stale;
        onData();
      })
      .catch(function () {
        if (ctrl.superseded) return;
        setStatus('โหลดไม่สำเร็จ ลองใหม่', true);
      })
      .then(function () {
        clearTimeout(timer);
        if (inflight === ctrl) inflight = null;
      });
  }

  function cancelRequest() {
    if (inflight) { inflight.superseded = true; inflight.abort(); }
    inflight = null;
  }

  // 'bbox' mode: whatever the map shows
  function loadVisibleArea() {
    if (mode !== 'bbox') return;
    if (map.getZoom() < MIN_ZOOM) {
      cancelRequest();
      setStatus('ซูมเข้าอีกหน่อยเพื่อดูมัสยิด');
      return;
    }
    var b = map.getBounds();
    var bbox = [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()]
      .map(function (v) { return v.toFixed(5); }).join(',');
    request('/api/mosques/nearby?bbox=' + bbox, render);
  }

  // 'near' mode: the NEAREST_COUNT closest mosques, and a map that shows them and the visitor
  function loadNearest() {
    if (mode !== 'near' || !userPos) return;
    request('/api/mosques/nearest?lat=' + userPos[0].toFixed(6) + '&lng=' + userPos[1].toFixed(6) +
            '&limit=' + NEAREST_COUNT, function () {
      render();
      var points = [userPos].concat(mosques.map(function (m) { return [m.lat, m.lng]; }));
      if (points.length > 1) map.fitBounds(points, { padding: [28, 28], maxZoom: 16 });
      else map.setView(userPos, USER_ZOOM);
    });
  }

  function enterNearMode() {
    mode = 'near';
    clearTimeout(moveTimer);
    setNote('แสดง ' + NEAREST_COUNT + ' มัสยิดที่ใกล้คุณที่สุด · เลื่อนแผนที่เพื่อดูบริเวณอื่น');
    loadNearest();
  }

  function enterBboxMode() {
    if (mode === 'bbox') return;
    mode = 'bbox';
    setNote(userPos ? 'เรียงตามระยะทางจากตำแหน่งของคุณ' : 'เปิดสิทธิ์ตำแหน่งที่ตั้งเพื่อดูระยะทางจากคุณถึงแต่ละมัสยิด');
  }

  // Map moves we make ourselves (fitBounds, panning to a row) keep 'near' mode; only the
  // visitor's own drag/zoom switches to 'bbox'. These events only come from the visitor.
  map.on('dragstart', enterBboxMode);
  mapEl.addEventListener('wheel', enterBboxMode, { passive: true });
  mapEl.addEventListener('dblclick', enterBboxMode);
  mapEl.addEventListener('touchstart', function (e) { if (e.touches.length > 1) enterBboxMode(); }, { passive: true });
  mapEl.addEventListener('keydown', enterBboxMode);
  mapEl.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('.leaflet-control-zoom')) enterBboxMode();
  }, true);

  map.on('moveend', function () {
    if (mode !== 'bbox') return;
    clearTimeout(moveTimer);
    moveTimer = setTimeout(loadVisibleArea, MOVE_DEBOUNCE_MS);
  });

  // ---------- distance ----------
  function haversineM(lat1, lon1, lat2, lon2) {
    var toRad = function (d) { return (d * Math.PI) / 180; };
    var R = 6371000;
    var dLat = toRad(lat2 - lat1);
    var dLon = toRad(lon2 - lon1);
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function formatDist(m) {
    if (m == null) return '—';
    // 999.6 m would round to "1000 ม." — switch to km before that
    return m < 999.5 ? Math.round(m) + ' ม.' : (m / 1000).toFixed(1) + ' กม.';
  }

  // Client-side hint only (greys the button); the server re-checks with its own coordinates.
  // Accepts a mosque object or a list row's dataset ({ lat, lng } as numbers or strings).
  function canCheckIn(mosque) {
    if (!userPos || !mosque) return false;
    var lat = Number(mosque.lat);
    var lng = Number(mosque.lng);
    if (!isFinite(lat) || !isFinite(lng)) return false;
    return haversineM(userPos[0], userPos[1], lat, lng) <= CHECK_IN_RADIUS_M;
  }

  // ---------- check-in ----------
  var toastTimer = null;
  function toast(text, isError) {
    toastEl.textContent = text;
    toastEl.classList.toggle('is-error', !!isError);
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, 5000);
  }

  // What the check-in button of mosque `m` should say/do right now.
  function checkinState(m) {
    if (!LOGGED_IN) return { kind: 'login', text: 'เข้าสู่ระบบเพื่อเช็คอิน' };
    var st = checkinStatus[m.id];
    if (!st) return { kind: 'loading', text: 'เช็คอิน', disabled: true };
    if (st.state === 'done') return { kind: 'done', text: st.message, disabled: true };
    if (st.state === 'done_elsewhere') return { kind: 'elsewhere', text: st.message, disabled: true };
    if (st.state === 'closed') return { kind: 'closed', text: st.message, disabled: true };
    if (!userPos) return { kind: 'locate', text: 'เปิดตำแหน่งเพื่อเช็คอิน' };
    if (!canCheckIn(m)) {
      var d = haversineM(userPos[0], userPos[1], m.lat, m.lng);
      return { kind: 'far', text: 'อยู่ห่าง ' + formatDist(d) + ' ต้องไม่เกิน ' + CHECK_IN_RADIUS_M + ' ม.', disabled: true };
    }
    return { kind: 'open', text: 'เช็คอิน ' + st.label };
  }

  function applyCheckinState(btn, m) {
    var s = checkinBusy && btn.dataset.busy ? { kind: 'busy', text: 'กำลังเช็คอิน…', disabled: true } : checkinState(m);
    btn.textContent = s.text;
    btn.disabled = !!s.disabled;
    btn.className = 'checkin-btn checkin-btn--' + s.kind;
  }

  function updateCheckinButtons() {
    mosques.forEach(function (m) {
      (checkinButtons[m.id] || []).forEach(function (btn) { applyCheckinState(btn, m); });
    });
  }

  function makeCheckinButton(m) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      onCheckinClick(m, btn);
    });
    (checkinButtons[m.id] = checkinButtons[m.id] || []).push(btn);
    applyCheckinState(btn, m);
    return btn;
  }

  var statusCtrl = null;
  function refreshCheckinStatus() {
    if (!LOGGED_IN || !mosques.length) return;
    if (statusCtrl) statusCtrl.abort();
    var ctrl = new AbortController();
    statusCtrl = ctrl;
    var ids = mosques.slice(0, MAX_STATUS_IDS).map(function (m) { return m.id; }).join(',');
    fetch('/api/checkins/status?osm_ids=' + encodeURIComponent(ids), { signal: ctrl.signal, headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (statusCtrl !== ctrl) return;
        checkinStatus = data.mosques || {};
        updateCheckinButtons();
      })
      .catch(function () { /* buttons stay in their last state; retried on the next refresh */ });
  }
  setInterval(function () {
    if (document.visibilityState === 'visible') refreshCheckinStatus();
  }, CHECKIN_REFRESH_MS);

  function onCheckinClick(m, btn) {
    var s = checkinState(m);
    if (s.kind === 'login') { window.location.href = '/login?next=' + encodeURIComponent('/mosques'); return; }
    if (s.kind === 'locate') { startLocation(true); return; }
    if (s.kind !== 'open' || checkinBusy) return;

    checkinBusy = true;
    btn.dataset.busy = '1';
    updateCheckinButtons();
    var done = function () {
      checkinBusy = false;
      delete btn.dataset.busy;
      updateCheckinButtons();
    };
    // A fresh fix, not the one from when the page opened: the visitor may have walked in since.
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        userPos = [pos.coords.latitude, pos.coords.longitude];
        userAccuracy = pos.coords.accuracy;
        if (userMarker) userMarker.setLatLng(userPos);
        fetch('/api/checkins', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ osm_id: m.id, lat: userPos[0], lng: userPos[1], accuracy: userAccuracy })
        })
          .then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (body) { return { ok: res.ok, body: body }; });
          })
          .then(function (r) {
            if (r.ok) {
              toast(r.body.message + ' — ' + r.body.mosque_name);
            } else {
              var d = r.body.detail || {};
              toast(d.message || 'เช็คอินไม่สำเร็จ ลองใหม่อีกครั้ง', true);
            }
            done();
            refreshCheckinStatus();
          })
          .catch(function () { toast('เช็คอินไม่สำเร็จ ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่', true); done(); });
      },
      function (err) {
        toast(err.code === err.PERMISSION_DENIED ? 'ไม่ได้รับสิทธิ์ตำแหน่งที่ตั้ง' : 'หาตำแหน่งไม่สำเร็จ ลองใหม่อีกครั้ง', true);
        done();
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  }

  // ---------- rendering (markers + list from the same array) ----------
  function navUrl(m) {
    return 'https://www.google.com/maps/dir/?api=1&destination=' + m.lat + ',' + m.lng;
  }

  function popupContent(m) {
    var box = document.createElement('div');
    box.className = 'mosque-popup';
    var name = document.createElement('strong');
    name.className = 'mosque-popup__name';
    name.textContent = m.name;
    box.appendChild(name);
    if (m.dist != null) {
      var dist = document.createElement('span');
      dist.className = 'mosque-popup__dist';
      dist.textContent = 'ห่างจากคุณ ' + formatDist(m.dist);
      box.appendChild(dist);
    }
    var nav = document.createElement('a');
    nav.className = 'btn';
    nav.href = navUrl(m);
    nav.target = '_blank';
    nav.rel = 'noopener';
    nav.textContent = 'นำทาง';
    box.appendChild(nav);
    box.appendChild(makeCheckinButton(m));
    // "ดูรายละเอียด" is hidden until RSVP/events are keyed by OSM id (see app/routers/mosques.py).
    return box;
  }

  // Row = a keyboard-operable "show on map" area + the check-in button next to it
  // (siblings, because a button must not sit inside another interactive element).
  function buildRow(m) {
    var row = document.createElement('div');
    row.className = 'list-row mosque-row';
    row.dataset.id = m.id;
    row.dataset.name = m.name;
    row.dataset.lat = m.lat;
    row.dataset.lng = m.lng;
    row.dataset.dist = m.dist == null ? '' : Math.round(m.dist);

    var ns = 'http://www.w3.org/2000/svg';
    var ico = document.createElementNS(ns, 'svg');
    ico.setAttribute('class', 'ico');
    ico.style.color = 'var(--green)';
    var use = document.createElementNS(ns, 'use');
    use.setAttribute('href', '#i-map-pin');
    ico.appendChild(use);

    var title = document.createElement('span');
    title.className = 'list-row__title';
    title.textContent = m.name;

    var dist = document.createElement('span');
    dist.className = 'list-row__dist';
    dist.setAttribute('data-dist', '');
    dist.textContent = formatDist(m.dist);

    var main = document.createElement('div');
    main.className = 'mosque-row__main';
    main.setAttribute('role', 'button');
    main.tabIndex = 0;
    main.setAttribute('aria-label', 'แสดง ' + m.name + ' บนแผนที่');
    main.appendChild(ico);
    main.appendChild(title);
    main.appendChild(dist);
    main.addEventListener('click', function () { focusMosque(m.id); });
    main.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();   // Space would otherwise scroll the page
        focusMosque(m.id);
      }
    });

    row.appendChild(main);
    row.appendChild(makeCheckinButton(m));
    return row;
  }

  function focusMosque(id) {
    var marker = markersById[id];
    if (!marker) return;
    mapEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    map.panTo(marker.getLatLng());
    marker.openPopup();
  }

  function render() {
    // Nearest first. Without the visitor's location, sort from the map centre instead
    // (badges still show "—" because that is not a distance from the visitor).
    var c = map.getCenter();
    mosques.forEach(function (m) {
      m.dist = userPos ? haversineM(userPos[0], userPos[1], m.lat, m.lng) : null;
      m._sort = userPos ? m.dist : haversineM(c.lat, c.lng, m.lat, m.lng);
    });
    mosques.sort(function (a, b) { return a._sort - b._sort; });

    // Keep the popup that is open (if its mosque is still in the new data).
    var openId = null;
    Object.keys(markersById).forEach(function (id) {
      if (markersById[id].isPopupOpen()) openId = id;
    });

    markerLayer.clearLayers();
    markersById = {};
    checkinButtons = {};
    Array.prototype.slice.call(listEl.querySelectorAll('.list-row')).forEach(function (r) { r.remove(); });

    var frag = document.createDocumentFragment();
    mosques.forEach(function (m) {
      markersById[m.id] = L.marker([m.lat, m.lng], { title: m.name }).bindPopup(popupContent(m));
      markerLayer.addLayer(markersById[m.id]);
      frag.appendChild(buildRow(m));
    });
    listEl.appendChild(frag);

    setStatus(mosques.length ? '' : 'ไม่พบมัสยิดในบริเวณนี้');
    if (openId && markersById[openId]) markersById[openId].openPopup();
    refreshCheckinStatus();
  }

  // Search text only narrows the dropdown; the map and list keep showing everything loaded.
  function matches(m) {
    return !query || m.name.toLowerCase().indexOf(query.toLowerCase()) !== -1;
  }

  // ---------- visitor location ----------
  var prompt = {
    el: document.getElementById('geo-prompt'),
    title: document.getElementById('geo-prompt-title'),
    body: document.getElementById('geo-prompt-body'),
    primary: document.getElementById('geo-prompt-primary'),
    secondary: document.getElementById('geo-prompt-secondary'),
    onPrimary: null,
    onSecondary: null,
    returnFocus: null
  };
  var PROMPTS = {
    ask: {
      title: 'ใช้ตำแหน่งของคุณ?',
      body: 'เพื่อแสดงมัสยิดใกล้คุณและบอกระยะทางไปแต่ละแห่ง หลังกด "อนุญาต" เบราว์เซอร์จะถามยืนยันอีกครั้ง',
      primary: 'อนุญาต',
      secondary: 'ไม่ตอนนี้'
    },
    denied: {
      title: 'ตำแหน่งถูกปิดอยู่',
      body: 'เปิดได้ที่การตั้งค่าเบราว์เซอร์ → การตั้งค่าเว็บไซต์ → ตำแหน่ง แล้วโหลดหน้านี้ใหม่',
      primary: 'ตกลง'
    },
    insecure: {
      title: 'ใช้ตำแหน่งไม่ได้บนลิงก์นี้',
      body: 'เบราว์เซอร์อนุญาตให้ใช้ตำแหน่งเฉพาะเว็บที่เปิดผ่าน https เท่านั้น',
      primary: 'ตกลง'
    },
    unsupported: {
      title: 'เบราว์เซอร์นี้ไม่รองรับตำแหน่ง',
      body: 'ยังค้นหามัสยิดบนแผนที่ได้ตามปกติ แต่จะไม่แสดงระยะทาง',
      primary: 'ตกลง'
    }
  };

  function showPrompt(kind, onPrimary, onSecondary) {
    var p = PROMPTS[kind];
    prompt.title.textContent = p.title;
    prompt.body.textContent = p.body;
    prompt.primary.textContent = p.primary;
    prompt.secondary.textContent = p.secondary || '';
    prompt.secondary.hidden = !p.secondary;
    prompt.onPrimary = onPrimary || null;
    prompt.onSecondary = onSecondary || null;
    prompt.returnFocus = document.activeElement;
    prompt.el.hidden = false;
    prompt.primary.focus();
  }
  function closePrompt(action) {
    if (prompt.el.hidden) return;
    prompt.el.hidden = true;
    var fn = action === 'primary' ? prompt.onPrimary : prompt.onSecondary;
    prompt.onPrimary = prompt.onSecondary = null;
    if (prompt.returnFocus && prompt.returnFocus.focus) prompt.returnFocus.focus();
    if (fn) fn();
  }
  prompt.primary.addEventListener('click', function () { closePrompt('primary'); });
  prompt.secondary.addEventListener('click', function () { closePrompt('secondary'); });
  prompt.el.addEventListener('click', function (e) { if (e.target === prompt.el) closePrompt('secondary'); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !prompt.el.hidden) closePrompt('secondary');
  });

  function permissionState() {
    if (!navigator.permissions || !navigator.permissions.query) return Promise.resolve('unknown');
    return navigator.permissions.query({ name: 'geolocation' })
      .then(function (s) { return s.state; }, function () { return 'unknown'; });
  }

  function setNote(text) { if (noteEl) noteEl.textContent = text; }

  // fromUser: the visitor tapped "ตำแหน่งฉัน" / "มัสยิดใกล้ฉัน" (vs. automatic on page load)
  function startLocation(fromUser) {
    if (!('geolocation' in navigator)) {
      setNote('เบราว์เซอร์นี้ไม่รองรับตำแหน่ง จึงไม่แสดงระยะทาง');
      if (fromUser) showPrompt('unsupported');
      return;
    }
    if (!window.isSecureContext) {
      setNote('ต้องเปิดผ่าน https จึงจะใช้ตำแหน่งและแสดงระยะทางได้');
      if (fromUser) showPrompt('insecure');
      return;
    }
    permissionState().then(function (state) {
      if (state === 'granted') return locate(fromUser);
      if (state === 'denied') {
        setNote('ไม่ได้รับสิทธิ์ตำแหน่งที่ตั้ง จึงไม่สามารถคำนวณระยะทางได้');
        if (fromUser) showPrompt('denied');
        return;
      }
      // 'prompt', or a browser that can't tell us: explain first, then let the browser ask.
      if (state === 'unknown' && readFlag('localStorage', CONSENT_KEY)) return locate(fromUser);
      if (!fromUser && readFlag('sessionStorage', DISMISSED_KEY)) return;
      showPrompt('ask', function () { locate(fromUser); }, function () {
        writeFlag('sessionStorage', DISMISSED_KEY);
        setNote('ยังไม่ได้ใช้ตำแหน่ง — กดปุ่ม "ตำแหน่งฉัน" บนแผนที่เพื่อดูระยะทาง');
      });
    });
  }

  function locate(fromUser) {
    setNote('กำลังหาตำแหน่งของคุณ…');
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        writeFlag('localStorage', CONSENT_KEY);
        userPos = [pos.coords.latitude, pos.coords.longitude];
        userAccuracy = pos.coords.accuracy;
        if (userMarker) {
          userMarker.setLatLng(userPos);
        } else {
          userMarker = L.circleMarker(userPos, { radius: 7, color: '#1B5E3A', fillOpacity: 0.9 })
            .addTo(map)
            .bindPopup('ตำแหน่งของคุณ');
        }
        enterNearMode();
      },
      function (err) {
        if (err.code === err.PERMISSION_DENIED) {
          setNote('ไม่ได้รับสิทธิ์ตำแหน่งที่ตั้ง จึงไม่สามารถคำนวณระยะทางได้');
          if (fromUser) showPrompt('denied');
        } else {
          setNote('หาตำแหน่งไม่สำเร็จ ลองกดปุ่ม "ตำแหน่งฉัน" อีกครั้ง');
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  }

  var LocateControl = L.Control.extend({
    options: { position: 'topright' },
    onAdd: function () {
      var btn = L.DomUtil.create('button', 'map-locate');
      btn.type = 'button';
      btn.setAttribute('aria-label', 'ตำแหน่งฉัน');
      // static markup only (no user data)
      btn.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
        '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg><span>ตำแหน่งฉัน</span>';
      L.DomEvent.disableClickPropagation(btn);
      L.DomEvent.on(btn, 'click', function () { startLocation(true); });
      return btn;
    }
  });
  new LocateControl().addTo(map);

  // ---------- search: filter loaded mosques + look up areas ----------
  var searchTimer = null;
  var geoCtrl = null;
  var suggestItems = [];   // [{ el, run }]
  var activeIndex = -1;

  function openSuggest() {
    // A debounced search/geocode result can arrive after the visitor closed the list
    // (Escape, tapped the map); only show it while they are still in the search box.
    if (document.activeElement !== searchInput) return;
    suggestEl.hidden = false;
    searchInput.setAttribute('aria-expanded', 'true');
  }
  function closeSuggest() {
    suggestEl.hidden = true;
    searchInput.setAttribute('aria-expanded', 'false');
    activeIndex = -1;
  }

  function addHead(text) {
    var h = document.createElement('div');
    h.className = 'suggest__head';
    h.textContent = text;
    suggestEl.appendChild(h);
  }
  function addNote(text) {
    var n = document.createElement('div');
    n.className = 'suggest__empty';
    n.textContent = text;
    suggestEl.appendChild(n);
  }
  function addItem(title, sub, meta, run) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'suggest__item';
    btn.setAttribute('role', 'option');
    var t = document.createElement('span');
    t.className = 'suggest__title';
    t.textContent = title;
    if (sub) {
      var s = document.createElement('span');
      s.className = 'suggest__sub';
      s.textContent = sub;
      t.appendChild(s);
    }
    btn.appendChild(t);
    if (meta) {
      var m = document.createElement('span');
      m.className = 'suggest__meta';
      m.textContent = meta;
      btn.appendChild(m);
    }
    btn.addEventListener('click', run);
    suggestEl.appendChild(btn);
    suggestItems.push({ el: btn, run: run });
  }

  function useNearMe() {
    searchInput.value = '';
    query = '';
    closeSuggest();
    searchInput.blur();   // otherwise closing the location popup refocuses the box and reopens this list
    startLocation(true);
  }

  // areas: null (not searched), 'loading', 'error', or an array of places
  function renderSuggest(areas) {
    suggestEl.textContent = '';
    suggestItems = [];
    activeIndex = -1;

    if (!query) {
      addItem('มัสยิดใกล้ฉัน', 'ใช้ตำแหน่งปัจจุบันของคุณ', '', useNearMe);
      openSuggest();
      return;
    }

    addHead('มัสยิด');
    var hits = mosques.filter(matches).slice(0, MAX_MOSQUE_SUGGESTIONS);
    if (!hits.length) addNote('ไม่พบมัสยิดชื่อนี้ในแผนที่ตอนนี้');
    hits.forEach(function (m) {
      addItem(m.name, '', m.dist == null ? '' : formatDist(m.dist), function () {
        closeSuggest();
        focusMosque(m.id);
      });
    });

    addHead('พื้นที่');
    if (areas === 'loading') addNote('กำลังค้นหาพื้นที่…');
    else if (areas === 'error') addNote('ค้นหาพื้นที่ไม่สำเร็จ ลองใหม่อีกครั้ง');
    else if (areas && !areas.length) addNote('ไม่พบพื้นที่');
    else if (!areas) addNote('พิมพ์อย่างน้อย 2 ตัวอักษรเพื่อค้นหาพื้นที่');
    (Array.isArray(areas) ? areas : []).forEach(function (place) {
      addItem(place.name, place.label !== place.name ? place.label : '', '', function () {
        searchInput.value = '';
        query = '';
        closeSuggest();
        enterBboxMode();
        map.setView([place.lat, place.lng], USER_ZOOM);   // moveend loads that area's mosques
      });
    });
    openSuggest();
  }

  function runSearch() {
    query = searchInput.value.trim();
    if (geoCtrl) { geoCtrl.abort(); geoCtrl = null; }
    if (query.length < 2) { renderSuggest(null); return; }

    renderSuggest('loading');
    var ctrl = new AbortController();
    geoCtrl = ctrl;
    var q = query;
    fetch('/api/geocode?q=' + encodeURIComponent(q), { signal: ctrl.signal, headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (places) {
        if (geoCtrl === ctrl && q === query) renderSuggest(places);
      })
      .catch(function () {
        if (geoCtrl === ctrl && !ctrl.signal.aborted) renderSuggest('error');
      });
  }

  function setActive(i) {
    if (!suggestItems.length) return;
    activeIndex = (i + suggestItems.length) % suggestItems.length;
    suggestItems.forEach(function (it, idx) { it.el.classList.toggle('is-active', idx === activeIndex); });
    suggestItems[activeIndex].el.scrollIntoView({ block: 'nearest' });
  }

  searchInput.addEventListener('input', function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, SEARCH_DEBOUNCE_MS);
  });
  searchInput.addEventListener('focus', function () {
    if (!searchInput.value.trim()) renderSuggest(null);
    else if (suggestEl.childNodes.length) openSuggest();
  });
  searchInput.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); openSuggest(); setActive(activeIndex + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(activeIndex - 1); }
    else if (e.key === 'Escape') { clearTimeout(searchTimer); closeSuggest(); searchInput.blur(); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      var pick = suggestItems[activeIndex >= 0 ? activeIndex : 0];
      if (pick && !suggestEl.hidden) pick.run();
    }
  });
  // pointerdown (not click) so starting to drag the map also closes the list
  document.addEventListener('pointerdown', function (e) {
    if (!searchWrap.contains(e.target)) closeSuggest();
  });

  window.MosqueFinder = {
    canCheckIn: canCheckIn,
    refreshCheckinStatus: refreshCheckinStatus,
    checkInRadiusM: CHECK_IN_RADIUS_M,
    getMosques: function () {
      return mosques.map(function (m) { return { id: m.id, name: m.name, lat: m.lat, lng: m.lng, dist: m.dist }; });
    },
    getUserPosition: function () {
      return userPos ? { lat: userPos[0], lng: userPos[1], accuracy: userAccuracy } : null;
    }
  };

  loadVisibleArea();
  startLocation(false);
})();
