// Green-bar view toggle (อุมมะฮ์: ชุมชน | ข่าวสาร, /admin: คำขอมัสยิด | รายงาน | สิทธิ์):
// swaps the views in place without a reload.
(function () {
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.switch__btn[data-view]'));
  if (!buttons.length) return;

  function show(view) {
    buttons.forEach(function (btn) {
      var on = btn.dataset.view === view;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
      var panel = document.getElementById(btn.getAttribute('aria-controls'));
      if (panel) panel.hidden = !on;
    });
  }

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      show(btn.dataset.view);
      // Keep ?view= in the address so reload / back from a post lands on the same view.
      var url = new URL(window.location.href);
      url.searchParams.set('view', btn.dataset.view);
      history.replaceState(null, '', url.pathname + url.search);
      window.scrollTo(0, 0);
    });
  });
})();
