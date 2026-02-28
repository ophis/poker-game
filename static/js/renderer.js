/**
 * renderer.js — Reads GameState, updates DOM idempotently.
 *
 * All DOM mutation goes through here. Never reads the DOM to
 * determine state — only reads window.GameState.get().
 */
window.Renderer = (() => {

  // ---- Suit helpers --------------------------------------------------------
  const SUIT_SYMBOLS = { s: '♠', h: '♥', d: '♦', c: '♣' };
  const RED_SUITS    = new Set(['h', 'd']);

  function suitOf(cardStr) {
    return cardStr ? cardStr.slice(-1) : '';
  }
  function rankOf(cardStr) {
    return cardStr ? cardStr.slice(0, -1) : '';
  }
  function isRed(cardStr) {
    return RED_SUITS.has(suitOf(cardStr));
  }

  // ---- Card element --------------------------------------------------------
  function makeCardEl(cardStr, small = false, animate = false, winner = false) {
    const el = document.createElement('div');
    const hidden = !cardStr || cardStr === '??';
    el.className = [
      'card',
      hidden   ? 'hidden'      : (isRed(cardStr) ? 'red' : 'black'),
      small    ? 'small'       : '',
      animate  ? 'deal-anim'   : '',
      winner   ? 'winner-card' : '',
    ].filter(Boolean).join(' ');

    if (!hidden) {
      const rank = rankOf(cardStr);
      const suit = SUIT_SYMBOLS[suitOf(cardStr)] || suitOf(cardStr);

      el.innerHTML = `
        <div class="card-corner top">
          <span class="card-rank">${rank}</span>
          <span class="card-suit-small">${suit}</span>
        </div>
        <div class="card-center">${suit}</div>
        <div class="card-corner bottom">
          <span class="card-rank">${rank}</span>
          <span class="card-suit-small">${suit}</span>
        </div>`;
    }
    return el;
  }

  // ---- Seat positions (% of viewport) for up to 9 players -----------------
  // Seats go around the oval table, starting at bottom-center and going CW.
  const SEAT_POSITIONS = [
    { left: '50%', top: '85%' },   // 0 — bottom center (self)
    { left: '20%', top: '75%' },   // 1 — bottom left
    { left: '8%',  top: '55%' },   // 2 — left
    { left: '12%', top: '30%' },   // 3 — upper left
    { left: '35%', top: '18%' },   // 4 — top left
    { left: '65%', top: '18%' },   // 5 — top right
    { left: '88%', top: '30%' },   // 6 — upper right
    { left: '92%', top: '55%' },   // 7 — right
    { left: '80%', top: '75%' },   // 8 — bottom right
  ];

  // ---- Public render -------------------------------------------------------
  function render() {
    const s = window.GameState.get();
    _renderSeats(s);
    _renderCommunity(s);
    _renderPot(s);
    _renderPhase(s);
    _renderHoleCards(s);
    _renderActionHistory(s);
  }

  function _renderSeats(s) {
    const container = document.getElementById('seats-container');
    if (!container) return;

    const players = s.players;
    const n = players.length;

    // Rotate seats so the current player is always at the bottom-center (index 0)
    const myIndex = players.findIndex(p => p.player_id === s.playerId);
    const offset = myIndex >= 0 ? myIndex : 0;

    // Reuse or create seat elements
    container.querySelectorAll('.player-seat[data-removing]').forEach(el => el.remove());

    for (let i = 0; i < n; i++) {
      const p = players[i];
      const seatIndex = (i - offset + n) % n;
      const pos = SEAT_POSITIONS[seatIndex % SEAT_POSITIONS.length];

      let seat = container.querySelector(`.player-seat[data-pid="${p.player_id}"]`);
      if (!seat) {
        seat = document.createElement('div');
        seat.className = 'player-seat';
        seat.dataset.pid = p.player_id;
        container.appendChild(seat);
      }

      seat.style.left = pos.left;
      seat.style.top  = pos.top;

      const isDealer  = (i === s.dealerIndex);
      const isActive  = (i === s.currentPlayerIndex);
      const isSelf    = (p.player_id === s.playerId);

      const actionLabel = _actionLabels[p.player_id];
      const actionHtml = actionLabel
        ? `<div class="${_esc(actionLabel.cssClass)}">${_esc(actionLabel.text)}</div>`
        : '';

      seat.innerHTML = `
        ${actionHtml}
        <div class="player-box${p.is_folded ? ' folded' : ''}${isActive ? ' active' : ''}${p.is_all_in ? ' is-all-in' : ''}">
          ${isDealer ? '<div class="dealer-chip">D</div>' : ''}
          <div class="player-name">${_esc(p.name)}${isSelf ? ' ★' : ''}</div>
          <div class="player-chips">$${p.chips.toLocaleString()}</div>
          <div class="player-bet">${p.bet > 0 ? '$' + p.bet : ''}</div>
          <div class="player-cards">
            ${(p.hole_cards || []).map(c => makeCardEl(c, true).outerHTML).join('')}
          </div>
        </div>`;
    }

    // Remove seats for departed players
    container.querySelectorAll('.player-seat').forEach(el => {
      const pid = el.dataset.pid;
      if (!players.find(p => p.player_id === pid)) {
        el.remove();
      }
    });
  }

  function _renderCommunity(s) {
    const el = document.getElementById('community-cards');
    if (!el) return;
    // Only re-render if card count changed (avoid flicker)
    const current = el.querySelectorAll('.card').length;
    const incoming = s.communityCards.length;
    if (current !== incoming) {
      el.innerHTML = '';
      s.communityCards.forEach((c, idx) => {
        const animate = idx >= current;
        el.appendChild(makeCardEl(c, false, animate));
      });
    }
  }

  function _renderPot(s) {
    const el = document.getElementById('pot-amount');
    if (el) el.textContent = '$' + s.pot.toLocaleString();
  }

  function _renderPhase(s) {
    const el = document.getElementById('phase-display');
    if (el) el.textContent = s.phase.replace(/_/g, ' ');
  }

  function _renderHoleCards(s) {
    const el = document.getElementById('hole-cards');
    if (!el) return;
    const cards = s.myHoleCards;
    const key = cards.join(',');
    if (el.dataset.cards !== key) {
      el.dataset.cards = key;
      el.innerHTML = '';
      cards.forEach(c => el.appendChild(makeCardEl(c, false, true)));
    }
  }

  // ---- Action history panel -------------------------------------------------
  function _actionColorClass(action) {
    const map = { fold: 'hist-fold', check: 'hist-check', call: 'hist-call',
                  raise: 'hist-raise', bet: 'hist-raise', all_in: 'hist-allin', 'all-in': 'hist-allin' };
    return map[action] || '';
  }

  function _renderActionHistory(s) {
    const container = document.getElementById('history-messages');
    if (!container) return;
    const history = s.actionHistory || [];
    const childCount = container.children.length;

    // History was cleared — reset DOM
    if (history.length < childCount) {
      container.innerHTML = '';
    }

    // Append only new entries
    for (let i = container.children.length; i < history.length; i++) {
      const entry = history[i];
      const div = document.createElement('div');

      if (entry.type === 'phase') {
        div.className = 'hist-phase';
        div.textContent = `\u2014 ${entry.text} \u2014`;
      } else if (entry.type === 'winner') {
        div.className = 'hist-winner';
        div.textContent = entry.text;
      } else {
        div.className = 'hist-entry';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'hist-name';
        nameSpan.textContent = entry.name + ': ';
        const actionSpan = document.createElement('span');
        actionSpan.className = _actionColorClass(entry.action);
        let actionText = entry.action.toUpperCase().replace('_', ' ');
        if (['raise', 'bet', 'call', 'all_in', 'all-in'].includes(entry.action) && entry.amount > 0) {
          actionText += ' $' + entry.amount.toLocaleString();
        }
        actionSpan.textContent = actionText;
        div.appendChild(nameSpan);
        div.appendChild(actionSpan);
      }

      container.appendChild(div);
    }

    if (history.length > childCount) {
      container.scrollTop = container.scrollHeight;
    }
  }

  // ---- Winner overlay ------------------------------------------------------
  function _playerName(w) {
    if (w.name) return w.name;
    const s = window.GameState.get();
    const p = (s.players || []).find(p => p.player_id === w.player_id);
    return p ? p.name : w.player_id;
  }

  function showWinner(winnersPayload) {
    const overlay = document.getElementById('winner-overlay');
    const title   = document.getElementById('winner-title');
    const details = document.getElementById('winner-details');
    if (!overlay) return;

    const winners = winnersPayload.winners || [];
    const allHands = winnersPayload.all_hands || {};
    const isShowdown = Object.keys(allHands).length > 0;

    // Aggregate winnings per player (a player can win multiple side pots)
    const winByPlayer = {};
    winners.forEach(w => {
      winByPlayer[w.player_id] = (winByPlayer[w.player_id] || 0) + w.amount;
    });
    const uniqueWinnerIds = Object.keys(winByPlayer);

    // Title line: who won and how much
    if (uniqueWinnerIds.length === 1) {
      const w = winners[0];
      title.textContent = `${_playerName(w)} wins $${winByPlayer[w.player_id]}!`;
    } else {
      title.textContent = 'Split Pot!';
    }

    // Details: show all hands at showdown, or just the winner's hand
    details.innerHTML = '';
    if (isShowdown) {
      // Show the board cards
      const s = window.GameState.get();
      const board = s.communityCards || [];
      if (board.length > 0) {
        const boardRow = document.createElement('div');
        boardRow.className = 'showdown-board';
        const label = document.createElement('span');
        label.className = 'showdown-board-label';
        label.textContent = 'Board';
        boardRow.appendChild(label);
        const boardCards = document.createElement('span');
        boardCards.className = 'showdown-cards';
        board.forEach(c => boardCards.appendChild(makeCardEl(c, true)));
        boardRow.appendChild(boardCards);
        details.appendChild(boardRow);
      }

      // Build a list of all hands sorted by score (best first)
      const hands = Object.entries(allHands)
        .map(([pid, h]) => ({ pid, ...h }))
        .sort((a, b) => a.score - b.score);

      const winnerIds = new Set(winners.map(w => w.player_id));

      hands.forEach(h => {
        const name = h.name || h.pid;
        const isWinner = winnerIds.has(h.pid);
        const line = document.createElement('div');
        line.className = 'showdown-hand' + (isWinner ? ' showdown-winner' : '');

        const nameSpan = document.createElement('span');
        nameSpan.className = 'showdown-name';
        nameSpan.textContent = name;
        line.appendChild(nameSpan);

        const cardsSpan = document.createElement('span');
        cardsSpan.className = 'showdown-cards';
        (h.hole_cards || []).forEach(c => {
          cardsSpan.appendChild(makeCardEl(c, true, false, isWinner));
        });
        line.appendChild(cardsSpan);

        const handSpan = document.createElement('span');
        handSpan.className = 'showdown-hand-name';
        handSpan.textContent = h.hand_name;
        line.appendChild(handSpan);

        details.appendChild(line);
      });
    } else {
      // No showdown (everyone else folded)
      if (winners.length === 1) {
        details.textContent = winners[0].hand || '';
      } else {
        details.textContent = winners.map(w => `${_playerName(w)}: $${w.amount}`).join('  •  ');
      }
    }

    overlay.style.display = 'flex';

    // Add close button
    const content = overlay.querySelector('.winner-content');
    let closeBtn = content.querySelector('.winner-close');
    if (!closeBtn) {
      closeBtn = document.createElement('button');
      closeBtn.className = 'winner-close';
      closeBtn.textContent = '\u00D7';
      closeBtn.addEventListener('click', () => { overlay.style.display = 'none'; });
      content.appendChild(closeBtn);
    }
  }

  // ---- Player action labels ------------------------------------------------
  // Store labels as data so they survive seat re-renders
  const _actionLabels = {};  // playerId -> { text, cssClass, timer }

  function _actionText(action, amount) {
    if (action === 'all_in' || action === 'all-in') {
      return 'ALL IN' + (amount > 0 ? ' $' + amount.toLocaleString() : '');
    }
    let text = action.toUpperCase();
    if ((action === 'raise' || action === 'bet' || action === 'call') && amount > 0) {
      text += ' $' + amount.toLocaleString();
    }
    return text;
  }

  function showPlayerAction(playerId, action, amount) {
    // Clear any existing timer for this player
    if (_actionLabels[playerId]?.timer) {
      clearTimeout(_actionLabels[playerId].timer);
    }

    const text = _actionText(action, amount);
    const cssClass = `action-label action-${action.replace('_', '-')}`;

    _actionLabels[playerId] = {
      text,
      cssClass,
      timer: setTimeout(() => { delete _actionLabels[playerId]; render(); }, 1500),
    };

    // Re-render seats to show the label
    render();
  }

  function clearActionLabels() {
    for (const pid of Object.keys(_actionLabels)) {
      if (_actionLabels[pid]?.timer) clearTimeout(_actionLabels[pid].timer);
      delete _actionLabels[pid];
    }
  }

  // ---- Action controls visibility -----------------------------------------
  function showActions(validActions) {
    const controls = document.getElementById('action-controls');
    if (!controls) return;
    controls.style.display = 'flex';

    const btnCheck = document.getElementById('btn-check');
    const btnCall  = document.getElementById('btn-call');
    const callAmt  = document.getElementById('call-amount');
    const raiseGrp = document.getElementById('raise-group');
    const slider   = document.getElementById('raise-slider');
    const raiseIn  = document.getElementById('raise-input');

    if (validActions.can_check) {
      btnCheck.style.display = 'block';
      btnCall.style.display  = 'none';
    } else {
      btnCheck.style.display = 'none';
      btnCall.style.display  = 'block';
      callAmt.textContent    = '$' + validActions.call_amount;
    }

    if (validActions.can_raise) {
      raiseGrp.style.display = 'flex';
      slider.min   = validActions.min_raise;
      slider.max   = validActions.max_raise;
      slider.value = validActions.min_raise;
      raiseIn.min  = validActions.min_raise;
      raiseIn.max  = validActions.max_raise;
      raiseIn.value = validActions.min_raise;
    } else {
      raiseGrp.style.display = 'none';
    }
  }

  function hideActions() {
    const controls = document.getElementById('action-controls');
    if (controls) controls.style.display = 'none';
  }

  function showHandName(name) {
    const el = document.getElementById('hand-name-display');
    if (el) el.textContent = name || '';
  }

  function addChatMessage(playerName, message) {
    const msgs = document.getElementById('chat-messages');
    if (!msgs) return;
    const div = document.createElement('div');
    div.className = 'chat-msg';
    div.innerHTML = `<span class="chat-name">${_esc(playerName)}:</span> ${_esc(message)}`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function setConnectionStatus(status) {
    const banner = document.getElementById('connection-banner');
    if (!banner) return;
    banner.className = `connection-banner ${status}`;
    const labels = { connecting: 'Connecting...', connected: 'Connected', disconnected: 'Disconnected — reload to reconnect' };
    banner.textContent = labels[status] || status;
  }

  function _esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return {
    render,
    showWinner,
    showActions,
    hideActions,
    showHandName,
    showPlayerAction,
    clearActionLabels,
    addChatMessage,
    setConnectionStatus,
    makeCardEl,
  };
})();
