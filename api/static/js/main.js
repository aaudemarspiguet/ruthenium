// fade out and remove all flash‐message alerts
(function(){
  function fadeAlerts() {
    const alerts = document.querySelectorAll('.alert');
    if (!alerts.length) return;
    setTimeout(() => {
      alerts.forEach(alert => {
        alert.style.opacity = '0';
        setTimeout(() => {
          if (alert.parentNode) alert.parentNode.removeChild(alert);
        }, 500);
      });
    }, 2000);
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