// อัลกุรอานประจำวัน: one ayah per day from api.alquran.cloud, picked with today's date as the
// seed so everyone opening the page on the same day sees the same ayah.
(function () {
  var root = document.getElementById('daily-quran');
  if (!root) return;

  var TOTAL_AYAHS = 6236;
  var BOM = '﻿'; // the API prefixes the first ayah of a surah with it
  var names = JSON.parse(root.dataset.names || '[]');

  var $ = function (id) { return document.getElementById(id); };
  var loading = $('daily-loading');
  var error = $('daily-error');
  var card = $('daily-card');

  // Local calendar date, so the ayah changes at the user's midnight.
  var now = new Date();
  var pad = function (n) { return (n < 10 ? '0' : '') + n; };
  var dateKey = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());

  // FNV-1a over the date string: neighbouring days land far apart in the mushaf.
  function ayahOfDay(key) {
    var h = 0x811c9dc5;
    for (var i = 0; i < key.length; i++) {
      h ^= key.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return (h % TOTAL_AYAHS) + 1;
  }

  $('daily-date').textContent = now.toLocaleDateString('th-TH', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  });

  function setState(state) {
    loading.hidden = state !== 'loading';
    error.hidden = state !== 'error';
    card.hidden = state !== 'ready';
  }

  function render(blocks) {
    var byEdition = {};
    blocks.forEach(function (b) { byEdition[(b.edition || {}).identifier] = b; });
    var editions = root.dataset.editions.split(',');
    var arabic = byEdition[editions[0]] || blocks[0];
    var thai = byEdition[editions[1]] || {};
    var surah = arabic.surah || {};
    var nameTh = names[surah.number - 1] || ('ซูเราะฮ์ที่ ' + surah.number);

    $('daily-surah-ar').textContent = surah.name || '';
    $('daily-surah-th').textContent = 'ซูเราะฮ์' + nameTh;
    $('daily-ref').textContent = 'ซูเราะฮ์ที่ ' + surah.number + ' · อายะฮ์ที่ ' + arabic.numberInSurah;
    $('daily-ar').textContent = (arabic.text || '').replace(BOM, '');
    $('daily-th').textContent = (thai.text || '').replace(BOM, '');
    $('daily-link').href = '/quran/' + surah.number;
    setState('ready');
  }

  function load() {
    setState('loading');
    var url = root.dataset.api + '/ayah/' + ayahOfDay(dateKey) + '/editions/' + root.dataset.editions;
    var controller = 'AbortController' in window ? new AbortController() : null;
    var timer = controller && setTimeout(function () { controller.abort(); }, 15000);

    fetch(url, controller ? { signal: controller.signal } : {})
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (payload) {
        var blocks = payload && payload.data;
        if (!Array.isArray(blocks) || !blocks.length || !blocks[0].text) throw new Error('bad payload');
        render(blocks);
      })
      .catch(function () { setState('error'); })
      .then(function () { if (timer) clearTimeout(timer); });
  }

  $('daily-retry').addEventListener('click', load);
  load();
})();
