// fade out and remove all flash‐message alerts
(function(){
  function fadeAlerts() {
    const alerts = document.querySelectorAll('.alert');
    if (!alerts.length) return;
    setTimeout(() => {
      alerts.forEach(alert => {
        alert.classList.add('slide-out');
        setTimeout(() => {
          if (alert.parentNode) alert.parentNode.removeChild(alert);
        }, 500);
      });
    }, 900);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fadeAlerts);
  } else {
    fadeAlerts();
  }
})();

window.initFilter = function(searchSelector, listSelector) {
  const input = document.querySelector(searchSelector);
  const list  = document.querySelectorAll(listSelector + ' li');
  if (!input || !list.length) return;

  input.addEventListener('input', e => {
    const q = e.target.value.toLowerCase();
    list.forEach(li => {
      li.style.display = li.innerText.toLowerCase().includes(q)
        ? '' : 'none';
    });
  });
};

function fadeToggle(elem, show) {
  if (show) {
    elem.classList.remove('fade-exit-active', 'fade-exit');
    elem.classList.add('fade-enter');
    requestAnimationFrame(() => {
      elem.classList.add('fade-enter-active');
      elem.classList.remove('fade-enter');
    });
    elem.style.display = '';
  } else {
    elem.classList.add('fade-exit');
    requestAnimationFrame(() => {
      elem.classList.add('fade-exit-active');
      elem.classList.remove('fade-exit');
    });
    elem.addEventListener('transitionend', () => {
      elem.style.display = 'none';
    }, { once: true });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Remove per-playlist quality and download icon JS. Only keep global quality sync if needed.

  document.querySelectorAll('.playlist-card').forEach(card => {
    const checkbox = card.querySelector('input[type="checkbox"]');
    if (!checkbox) return;
    // Card click toggles selection
    card.addEventListener('click', function(e) {
      if (e.target.tagName === 'INPUT') return;
      checkbox.checked = !checkbox.checked;
      card.classList.toggle('selected', checkbox.checked);
    });
    // Checkbox change updates card
    checkbox.addEventListener('change', function() {
      card.classList.toggle('selected', checkbox.checked);
    });
  });

  // Selection logic for liked songs (download.html)
  document.querySelectorAll('.list-group-item input[type="checkbox"]').forEach(cb => {
    const li = cb.closest('.list-group-item');
    // Hide checkbox visually, but keep accessible
    cb.style.opacity = 0;
    cb.style.position = 'absolute';
    cb.style.right = '1.2rem';
    cb.style.top = '50%';
    cb.style.transform = 'translateY(-50%) scale(1.2)';
    cb.style.pointerEvents = 'none';
    // Click on row toggles selection
    li.addEventListener('click', function(e) {
      if (e.target === cb) return;
      cb.checked = !cb.checked;
      li.classList.toggle('selected', cb.checked);
    });
    // Checkbox change updates row
    cb.addEventListener('change', function() {
      li.classList.toggle('selected', cb.checked);
    });
    // Initial state
    li.classList.toggle('selected', cb.checked);
  });

  // --- Disable download button if nothing selected (playlists) ---
  const playlistDownloadBtn = document.querySelector('#multi-actions button[type="submit"]');
  const playlistCheckboxes = document.querySelectorAll('.playlist-select-input');
  function updatePlaylistDownloadBtn() {
    if (!playlistDownloadBtn || !playlistCheckboxes.length) return;
    const anyChecked = Array.from(playlistCheckboxes).some(cb => cb.checked);
    playlistDownloadBtn.disabled = !anyChecked;
    playlistDownloadBtn.classList.toggle('disabled', !anyChecked);
  }
  playlistCheckboxes.forEach(cb => {
    cb.addEventListener('change', updatePlaylistDownloadBtn);
    // Also update on click for custom wrappers
    cb.closest('.playlist-card-wrapper')?.addEventListener('click', () => {
      setTimeout(updatePlaylistDownloadBtn, 0);
    });
  });
  updatePlaylistDownloadBtn();

  // --- Disable download button if nothing selected (liked songs) ---
  const likedDownloadBtn = document.querySelector('#multi-actions button[type="submit"]');
  const likedCheckboxes = document.querySelectorAll('.list-group-item input[type="checkbox"]');
  function updateLikedDownloadBtn() {
    if (!likedDownloadBtn || !likedCheckboxes.length) return;
    const anyChecked = Array.from(likedCheckboxes).some(cb => cb.checked);
    likedDownloadBtn.disabled = !anyChecked;
    likedDownloadBtn.classList.toggle('disabled', !anyChecked);
  }
  likedCheckboxes.forEach(cb => {
    cb.addEventListener('change', updateLikedDownloadBtn);
    cb.closest('.list-group-item')?.addEventListener('click', () => {
      setTimeout(updateLikedDownloadBtn, 0);
    });
  });
  updateLikedDownloadBtn();

  // --- Show alert if download attempted with nothing selected ---
  function showNoSelectionAlert() {
    const existing = document.querySelector('.alert.no-selection');
    if (existing) return;
    const alert = document.createElement('div');
    alert.className = 'alert no-selection';
    alert.textContent = 'Please select at least one item to download.';
    document.querySelector('.container')?.prepend(alert);
    setTimeout(() => {
      alert.classList.add('slide-out');
      setTimeout(() => alert.remove(), 500);
    }, 1200);
  }

  if (playlistDownloadBtn) {
    playlistDownloadBtn.addEventListener('click', function(e) {
      if (playlistDownloadBtn.disabled) {
        e.preventDefault();
        showNoSelectionAlert();
      }
    });
  }
  if (likedDownloadBtn) {
    likedDownloadBtn.addEventListener('click', function(e) {
      if (likedDownloadBtn.disabled) {
        e.preventDefault();
        showNoSelectionAlert();
      }
    });
  }
});