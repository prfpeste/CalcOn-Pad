const codeTextarea = document.getElementById('code-textarea');
const fileInput = document.getElementById('file-input');

// --- Icons: fetch SVG files and embed them INLINE (not as <img>), so
// that stroke="currentColor" follows the button's text color (hover,
// "active" state, a future dark mode -- all via CSS, without having to
// maintain a second icon file per state).
function loadIcons() {
  document.querySelectorAll('[data-icon]').forEach(function (el) {
    const name = el.getAttribute('data-icon');
    fetch('/static/icons/' + name + '.svg')
      .then(function (res) { return res.ok ? res.text() : Promise.reject(res.status); })
      .then(function (svg) { el.innerHTML = svg; })
      .catch(function () { /* icon missing -- button stays empty, not a hard error */ });
  });
}

// --- Dropdowns ---
function closeAllDropdowns(except) {
  document.querySelectorAll('[data-dropdown]').forEach(function (dd) {
    if (dd !== except) dd.removeAttribute('data-open');
  });
}

function positionDropdown(dd) {
  const panel = dd.querySelector('[data-panel]');
  if (!panel) return;

  // On narrow windows, CSS (media query) takes over full bottom-sheet
  // positioning -- don't interfere with that here.
  if (window.matchMedia('(max-width: 760px)').matches) return;

  panel.style.left = '';
  panel.style.right = '';

  requestAnimationFrame(function () {
    const rect = panel.getBoundingClientRect();
    const col = dd.closest('.col');
    const boundary = col ? col.getBoundingClientRect().right : window.innerWidth;
    if (rect.right > boundary - 8) {
      panel.style.left = 'auto';
      panel.style.right = '0';
    }
  });
}

function initDropdowns() {
  document.querySelectorAll('[data-dropdown]').forEach(function (dd) {
    const trigger = dd.querySelector('[data-trigger]');
    if (!trigger) return;

    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      const isOpen = dd.hasAttribute('data-open');
      closeAllDropdowns(dd);
      if (isOpen) {
        dd.removeAttribute('data-open');
      } else {
        dd.setAttribute('data-open', '');
        positionDropdown(dd);
      }
    });

    // Clicks INSIDE the panel (labels, input fields, text, ...) must not
    // bubble up to the global document click listener below -- otherwise
    // the panel would close itself the instant you click into it (e.g.
    // when focusing the rounding-precision text field). Buttons that
    // should deliberately close the panel (e.g. inserting a symbol)
    // still call closeAllDropdowns() explicitly themselves, which is
    // unaffected by this.
    const panel = dd.querySelector('[data-panel]');
    if (panel) {
      panel.addEventListener('click', function (e) {
        e.stopPropagation();
      });
    }
  });

  document.addEventListener('click', function () {
    closeAllDropdowns(null);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAllDropdowns(null);
  });
}

// --- Open file ---
fileInput.addEventListener('change', function () {
  const file = fileInput.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function (e) {
    codeTextarea.value = e.target.result;
  };
  reader.readAsText(file, 'utf-8');
});

// --- Save file ---
function saveFile() {
  const text = codeTextarea.value || '';
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });

  let filename = prompt('enter filename:', 'CalcOnPad.txt');
  if (!filename) {
    return;
  }

  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(link.href);
}

// --- Insert snippet (symbols, functions, ...) ---
function insertSymbol(sym) {
  insertSnippet(sym, 0);
}

function insertSnippet(snippet, cursorOffsetFromEnd) {
  codeTextarea.focus();

  const start = codeTextarea.selectionStart;
  const end = codeTextarea.selectionEnd;
  const text = codeTextarea.value;

  const before = text.slice(0, start);
  const after = text.slice(end);

  codeTextarea.value = before + snippet + after;

  const newEndPos = start + snippet.length;
  const cursorPos = newEndPos - (cursorOffsetFromEnd || 0);

  codeTextarea.selectionStart = codeTextarea.selectionEnd = cursorPos;
  closeAllDropdowns(null);
}

loadIcons();
initDropdowns();
