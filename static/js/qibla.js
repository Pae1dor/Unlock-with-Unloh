// Qibla direction dial: bearing to the Kaaba from the visitor's location,
// rotated live against device compass heading where the browser exposes one.
(function () {
  var needle = document.getElementById('qibla-needle');
  var label = document.getElementById('qibla-label');
  if (!needle || !label) return;

  var KAABA_LAT = 21.4225;
  var KAABA_LNG = 39.8262;

  var qiblaBearing = null; // degrees from true north, at the visitor's location
  var deviceHeading = 0;   // degrees from true north the top of the phone currently faces

  function toRad(d) { return (d * Math.PI) / 180; }
  function toDeg(r) { return (r * 180) / Math.PI; }

  function bearingTo(lat1, lon1, lat2, lon2) {
    var phi1 = toRad(lat1);
    var phi2 = toRad(lat2);
    var dLon = toRad(lon2 - lon1);
    var y = Math.sin(dLon) * Math.cos(phi2);
    var x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLon);
    return (toDeg(Math.atan2(y, x)) + 360) % 360;
  }

  function paint() {
    if (qiblaBearing === null) return;
    var rotation = qiblaBearing - deviceHeading;
    needle.style.transform = 'rotate(' + rotation + 'deg)';
  }

  function onOrientation(event) {
    var heading = typeof event.webkitCompassHeading === 'number'
      ? event.webkitCompassHeading
      : (event.absolute && typeof event.alpha === 'number' ? 360 - event.alpha : null);
    if (heading === null) return;
    deviceHeading = heading;
    label.textContent = 'หมุนอุปกรณ์ให้เข็มสีเขียวชี้ขึ้น เพื่อหันไปทางกิบลัต';
    paint();
  }

  function startCompass() {
    var Evt = window.DeviceOrientationEvent;
    if (!Evt) return;
    if (typeof Evt.requestPermission === 'function') {
      Evt.requestPermission().then(function (state) {
        if (state === 'granted') window.addEventListener('deviceorientation', onOrientation);
      }).catch(function () {});
    } else {
      window.addEventListener('deviceorientationabsolute', onOrientation);
      window.addEventListener('deviceorientation', onOrientation);
    }
  }

  if (!navigator.geolocation) {
    label.textContent = 'อุปกรณ์นี้ไม่รองรับการระบุตำแหน่ง';
    return;
  }

  navigator.geolocation.getCurrentPosition(
    function (pos) {
      qiblaBearing = bearingTo(pos.coords.latitude, pos.coords.longitude, KAABA_LAT, KAABA_LNG);
      label.textContent = 'กิบลัตอยู่ทาง ' + Math.round(qiblaBearing) + '° จากทิศเหนือ (แตะเพื่อเปิดเข็มทิศ)';
      paint();
    },
    function () {
      label.textContent = 'ไม่ได้รับสิทธิ์ตำแหน่งที่ตั้ง จึงระบุทิศกิบลัตไม่ได้';
    },
    { timeout: 8000 }
  );

  // iOS requires a user gesture before it will grant orientation access.
  document.querySelector('.qibla').addEventListener('click', startCompass);
})();
