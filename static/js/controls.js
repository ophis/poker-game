/**
 * controls.js — Button/slider event handlers.
 *
 * Reads GameState for context, sends actions via PokerWS.sendAction().
 * Never touches DOM directly (delegates to Renderer).
 */
window.Controls = (() => {

  function init() {
    _bindActionButtons();
    _bindRaiseSlider();
    _bindBetShortcuts();
    _bindChat();
    _bindChatToggle();
    _bindHistoryToggle();
    _bindHistoryResize();
  }

  function _bindActionButtons() {
    document.getElementById('btn-fold')?.addEventListener('click', () => {
      window.PokerWS.sendAction('fold', 0);
      window.Renderer.hideActions();
    });

    document.getElementById('btn-check')?.addEventListener('click', () => {
      window.PokerWS.sendAction('check', 0);
      window.Renderer.hideActions();
    });

    document.getElementById('btn-call')?.addEventListener('click', () => {
      const s = window.GameState.get();
      const amount = s.validActions?.call_amount || 0;
      window.PokerWS.sendAction('call', amount);
      window.Renderer.hideActions();
    });

    document.getElementById('btn-raise')?.addEventListener('click', () => {
      const input = document.getElementById('raise-input');
      const amount = parseInt(input?.value || '0', 10);
      window.PokerWS.sendAction('raise', amount);
      window.Renderer.hideActions();
    });
  }

  function _bindRaiseSlider() {
    const slider = document.getElementById('raise-slider');
    const input  = document.getElementById('raise-input');
    if (!slider || !input) return;

    slider.addEventListener('input', () => {
      input.value = slider.value;
    });

    input.addEventListener('input', () => {
      const s = window.GameState.get();
      const va = s.validActions;
      if (!va) return;
      let v = parseInt(input.value, 10) || va.min_raise;
      v = Math.max(va.min_raise, Math.min(va.max_raise, v));
      slider.value = v;
    });
  }

  function _bindBetShortcuts() {
    document.querySelectorAll('.bet-shortcut').forEach(btn => {
      btn.addEventListener('click', () => {
        const s  = window.GameState.get();
        const va = s.validActions;
        if (!va) return;

        let amount;
        if (btn.dataset.allin === 'true') {
          amount = va.max_raise;
          window.PokerWS.sendAction('all_in', amount);
          window.Renderer.hideActions();
          return;
        }

        const fraction = parseFloat(btn.dataset.fraction);
        amount = Math.round(va.call_amount + s.pot * fraction);
        amount = Math.max(va.min_raise, Math.min(va.max_raise, amount));

        const slider = document.getElementById('raise-slider');
        const input  = document.getElementById('raise-input');
        if (slider) slider.value = amount;
        if (input)  input.value  = amount;
      });
    });
  }

  function _bindChat() {
    const sendBtn = document.getElementById('chat-send');
    const input   = document.getElementById('chat-input');
    if (!sendBtn || !input) return;

    function doSend() {
      const msg = input.value.trim();
      if (!msg) return;
      window.PokerWS.sendChat(msg);
      input.value = '';
    }

    sendBtn.addEventListener('click', doSend);
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') doSend();
    });
  }

  function _bindChatToggle() {
    document.getElementById('chat-toggle')?.addEventListener('click', () => {
      const panel = document.getElementById('chat-panel');
      if (!panel) return;
      panel.classList.toggle('collapsed');
      // Hide unread badge
      const badge = document.getElementById('chat-badge');
      if (badge) badge.style.display = 'none';
    });
  }

  function _bindHistoryToggle() {
    document.getElementById('history-toggle')?.addEventListener('click', () => {
      const panel = document.getElementById('action-history');
      if (!panel) return;
      panel.classList.toggle('collapsed');
    });
  }

  function _bindHistoryResize() {
    const handle = document.getElementById('history-resize');
    const panel  = document.getElementById('action-history');
    if (!handle || !panel) return;

    const MIN_H = 80;
    let dragging = false;
    let startY = 0;
    let startH = 0;

    handle.addEventListener('mousedown', function(e) {
      if (e.button !== 0) return;
      dragging = true;
      startY   = e.clientY;
      startH   = panel.offsetHeight;
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    // Permanent document listeners — never added/removed, never missed
    document.addEventListener('mousemove', function(e) {
      if (!dragging) return;
      const maxH = Math.floor(window.innerHeight * 0.88);
      const newH = Math.max(MIN_H, Math.min(maxH, startH + startY - e.clientY));
      panel.style.height = newH + 'px';
    });

    document.addEventListener('mouseup', function() {
      if (!dragging) return;
      dragging = false;
      document.body.style.userSelect = '';
    });
  }

  return { init };
})();
