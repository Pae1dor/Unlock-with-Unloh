// Mosque finder: Leaflet map + haversine distance from the visitor's location.
(function () {
  var mapEl = document.getElementById('map');
  if (!mapEl || typeof L === 'undefined') return;

  var BANGKOK = [13.7563, 100.5018];
  var map = L.map('map').setView(BANGKOK, 11);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  var listEl = document.getElementById('mosque-list');
  var noteEl = document.getElementById('geo-note');

  fetch('/api/mosques')
    .then(function (res) { return res.json(); })
    .then(function (mosques) {
      if (!mosques.length) return;

      var bounds = [];
      mosques.forEach(function (m) {
        L.marker([m.lat, m.lng])
          .addTo(map)
          .bindPopup('<strong>' + m.name + '</strong><br>' + m.address);
        bounds.push([m.lat, m.lng]);
      });
      map.fitBounds(bounds, { padding: [26, 26] });

      requestDistances();
    })
    .catch(function () {
      if (noteEl) noteEl.textContent = 'ไม่สามารถโหลดข้อมูลมัสยิดได้';
    });

  function haversineKm(lat1, lon1, lat2, lon2) {
    var toRad = function (d) { return (d * Math.PI) / 180; };
    var R = 6371;
    var dLat = toRad(lat2 - lat1);
    var dLon = toRad(lon2 - lon1);
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function requestDistances() {
    if (!navigator.geolocation || !listEl) return;

    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = pos.coords.latitude;
        var lng = pos.coords.longitude;

        L.circleMarker([lat, lng], { radius: 7, color: '#1B5E3A', fillOpacity: 0.9 })
          .addTo(map)
          .bindPopup('ตำแหน่งของคุณ');

        var rows = Array.prototype.slice.call(listEl.querySelectorAll('[data-lat]'));
        rows.forEach(function (row) {
          var km = haversineKm(lat, lng, parseFloat(row.dataset.lat), parseFloat(row.dataset.lng));
          row.dataset.km = km;
          var badge = row.querySelector('[data-dist]');
          if (badge) badge.textContent = km.toFixed(1) + ' กม.';
        });

        rows
          .sort(function (a, b) { return parseFloat(a.dataset.km) - parseFloat(b.dataset.km); })
          .forEach(function (row) { listEl.appendChild(row); });

        if (noteEl) noteEl.textContent = 'เรียงตามระยะทางจากตำแหน่งของคุณ';
      },
      function () {
        if (noteEl) noteEl.textContent = 'ไม่ได้รับสิทธิ์ตำแหน่งที่ตั้ง จึงไม่สามารถคำนวณระยะทางได้';
      },
      { timeout: 8000 }
    );
  }
})();
