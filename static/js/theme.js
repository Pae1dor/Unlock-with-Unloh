// Theme picker on /profile: switches the theme at once (html[data-theme]) and keeps the choice
// in the "theme" cookie, which the server reads to draw every page in it from the first paint.
(function () {
  var buttons = Array.prototype.slice.call(document.querySelectorAll('[data-theme-pick]'));
  if (!buttons.length) return;

  // The browser's address-bar colour per theme; keep in step with THEME_COLORS in app/templating.py.
  var BAR = { green: '#1B5E3A', gold: '#9c762b', dark: '#143b28' };

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    buttons.forEach(function (btn) {
      btn.setAttribute('aria-checked', btn.getAttribute('data-theme-pick') === theme ? 'true' : 'false');
    });
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta && BAR[theme]) meta.setAttribute('content', BAR[theme]);
  }

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var theme = btn.getAttribute('data-theme-pick');
      if (!BAR[theme]) return;
      apply(theme);
      try {
        document.cookie = 'theme=' + theme + '; path=/; max-age=31536000; SameSite=Lax' +
          (window.location.protocol === 'https:' ? '; Secure' : '');
      } catch (e) { /* cookies blocked: the choice lasts until the page is closed */ }
    });
  });
})();
