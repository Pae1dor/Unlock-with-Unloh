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

  // Back/forward cache restores the old page with the bar still running.
  window.addEventListener('pageshow', stop);
})();
