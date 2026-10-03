// Pick a mosque's position (เพิ่มมัสยิด, and the admin's edit page) by tapping the map, dragging the pin, or
// "ใช้ตำแหน่งปัจจุบัน". The hidden lat/lng fields are the only way a position is sent.
(function () {
  var el = document.getElementById('pin-map');
  if (!el || !window.L) return;

  var latInput = document.getElementById('pin-lat');
  var lngInput = document.getElementById('pin-lng');
  var status = document.getElementById('pin-status');
  var locateBtn = document.getElementById('pin-locate');
  var form = el.closest('form');

  var THAILAND = [13.0, 101.0];
  var map = L.map(el).setView(THAILAND, 5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  var marker = null;

  function setStatus(text, isError) {
    status.textContent = text;
    status.classList.toggle('is-error', !!isError);
  }

  function place(latlng, zoom) {
    if (!marker) {
      marker = L.marker(latlng, { draggable: true }).addTo(map);
      marker.on('dragend', function () { save(marker.getLatLng()); });
    } else {
      marker.setLatLng(latlng);
    }
    save(marker.getLatLng());
    if (zoom) map.setView(latlng, zoom);
  }

  function save(latlng) {
    latInput.value = latlng.lat.toFixed(7);
    lngInput.value = latlng.lng.toFixed(7);
    setStatus('ปักหมุดแล้ว ✓ ลากหมุดเพื่อปรับให้ตรงได้');
  }

  // Coming back from a failed submit: keep the pin where it was.
  var lat0 = parseFloat(latInput.value), lng0 = parseFloat(lngInput.value);
  if (isFinite(lat0) && isFinite(lng0)) place(L.latLng(lat0, lng0), 17);

  map.on('click', function (e) { place(e.latlng, map.getZoom() < 15 ? 17 : null); });

  locateBtn.addEventListener('click', function () {
    if (!('geolocation' in navigator)) {
      setStatus('อุปกรณ์นี้ระบุตำแหน่งไม่ได้ แตะบนแผนที่แทน', true);
      return;
    }
    window.uiSetLoading && window.uiSetLoading(locateBtn, true);
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        window.uiSetLoading && window.uiSetLoading(locateBtn, false);
        place(L.latLng(pos.coords.latitude, pos.coords.longitude), 18);
      },
      function () {
        window.uiSetLoading && window.uiSetLoading(locateBtn, false);
        setStatus('ระบุตำแหน่งไม่ได้ (ไม่ได้อนุญาต หรือสัญญาณไม่ชัด) แตะบนแผนที่แทน', true);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  });

  form.addEventListener('submit', function (e) {
    if (!latInput.value || !lngInput.value) {
      e.preventDefault();
      setStatus('กรุณาปักหมุดตำแหน่งมัสยิดก่อนส่ง', true);
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  });
})();
