// Client-side filter over the 114-surah list.
(function () {
  var input = document.getElementById('surah-search');
  var list = document.getElementById('surah-list');
  if (!input || !list) return;

  var rows = Array.prototype.slice.call(list.querySelectorAll('a.row'));
  var empty = document.getElementById('no-results');

  input.addEventListener('input', function () {
    var q = input.value.trim().toLowerCase();
    var visible = 0;

    rows.forEach(function (row) {
      var haystack = (row.getAttribute('data-search') || '').toLowerCase();
      var match = q === '' || haystack.indexOf(q) !== -1;
      row.hidden = !match;
      if (match) visible++;
    });

    if (empty) empty.hidden = visible !== 0;
  });
})();
