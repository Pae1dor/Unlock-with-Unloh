// Forum post detail: AJAX like toggle + add comment without a page reload.
(function () {
  var likeBtn = document.getElementById('like-btn');
  var likeCount = document.getElementById('like-count');

  if (likeBtn) {
    likeBtn.addEventListener('click', function () {
      if (likeBtn.dataset.loggedIn !== 'yes') {
        window.location.href = '/login?next=/community/' + likeBtn.dataset.postId;
        return;
      }
      likeBtn.disabled = true;
      fetch('/api/community/' + likeBtn.dataset.postId + '/like', { method: 'POST' })
        .then(function (res) {
          if (!res.ok) throw new Error('like failed');
          return res.json();
        })
        .then(function (data) {
          likeBtn.classList.toggle('is-liked', data.liked);
          if (likeCount) likeCount.textContent = data.like_count;
        })
        .catch(function () { /* leave the button as it was */ })
        .then(function () { likeBtn.disabled = false; });
    });
  }

  var form = document.getElementById('comment-form');
  if (!form) return;

  var input = document.getElementById('comment-input');
  var list = document.getElementById('comment-list');
  var counter = document.getElementById('comment-count');
  var errorEl = document.getElementById('comment-error');

  function escapeHtml(value) {
    var div = document.createElement('div');
    div.textContent = value;
    return div.innerHTML;
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var content = (input.value || '').trim();
    if (!content) return;

    if (errorEl) errorEl.hidden = true;

    fetch('/api/community/' + form.dataset.postId + '/comments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content })
    })
      .then(function (res) {
        if (!res.ok) throw new Error('comment failed');
        return res.json();
      })
      .then(function (data) {
        var placeholder = document.getElementById('no-comments');
        if (placeholder) placeholder.remove();

        var node = document.createElement('div');
        node.className = 'comment';
        node.innerHTML =
          '<span class="avatar">' + escapeHtml(data.author_initial) + '</span>' +
          '<div><div class="comment__name">' + escapeHtml(data.author_name) + '</div>' +
          '<div class="comment__meta">' + escapeHtml(data.created_at) + '</div>' +
          '<div class="comment__text">' + escapeHtml(data.content) + '</div></div>';
        list.appendChild(node);

        input.value = '';
        if (counter) counter.textContent = String(Number(counter.textContent || '0') + 1);
      })
      .catch(function () {
        if (errorEl) {
          errorEl.textContent = 'ส่งความคิดเห็นไม่สำเร็จ กรุณาลองใหม่';
          errorEl.hidden = false;
        }
      });
  });
})();
