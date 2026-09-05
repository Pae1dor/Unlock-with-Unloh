// Persist the "แจ้งเตือนละหมาด" flag on the user record.
(function () {
  var toggle = document.getElementById('prayer-toggle');
  var status = document.getElementById('toggle-status');
  if (!toggle || toggle.disabled) return;

  toggle.addEventListener('change', function () {
    var enabled = toggle.checked;
    fetch('/api/prayer-notifications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: enabled })
    })
      .then(function (res) {
        if (!res.ok) throw new Error('save failed');
        return res.json();
      })
      .then(function (data) {
        toggle.checked = data.enabled;
        if (status) status.textContent = data.enabled ? 'เปิดการแจ้งเตือนแล้ว' : 'ปิดการแจ้งเตือนแล้ว';
      })
      .catch(function () {
        toggle.checked = !enabled;
        if (status) status.textContent = 'บันทึกไม่สำเร็จ กรุณาลองใหม่';
      });
  });
})();
