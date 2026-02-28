/**
 * lobby.js — Lobby page logic.
 *
 * Handles create-game form submission and join game flow.
 */
document.addEventListener('DOMContentLoaded', () => {

  // ---- Create game ---------------------------------------------------------
  document.getElementById('create-game-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const errEl = document.getElementById('create-error');
    errEl.style.display = 'none';

    const playerName = document.getElementById('player-name').value.trim();
    if (!playerName) {
      showError(errEl, 'Please enter your name.');
      return;
    }

    const buyIn = parseInt(document.getElementById('buy-in').value, 10);

    // 1. Create the game
    let gameData;
    try {
      const res = await fetch('/api/games', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variant:        document.getElementById('variant').value,
          small_blind:    parseInt(document.getElementById('small-blind').value, 10),
          big_blind:      parseInt(document.getElementById('big-blind').value, 10),
          max_players:    parseInt(document.getElementById('max-players').value, 10),
          num_bots:       parseInt(document.getElementById('num-bots').value, 10),
          bot_difficulty: document.getElementById('bot-difficulty').value,
          bot_stack:      buyIn,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        showError(errEl, err.detail || 'Could not create game.');
        return;
      }
      gameData = await res.json();
    } catch (err) {
      showError(errEl, 'Network error: ' + err.message);
      return;
    }

    // 2. Join the game
    let joinData;
    try {
      const res = await fetch(`/api/games/${gameData.game_id}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: playerName, buy_in: buyIn }),
      });
      if (!res.ok) {
        const err = await res.json();
        showError(errEl, err.detail || 'Could not join game.');
        return;
      }
      joinData = await res.json();
    } catch (err) {
      showError(errEl, 'Network error: ' + err.message);
      return;
    }

    // 3. Store player info and navigate
    sessionStorage.setItem('player_id',   joinData.player_id);
    sessionStorage.setItem('player_name', playerName);
    window.location.href = `/game/${gameData.game_id}`;
  });

  // ---- Join existing game --------------------------------------------------
  document.querySelectorAll('.join-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const gameId = btn.dataset.gameId;
      document.getElementById('join-game-id').value = gameId;
      document.getElementById('join-modal').style.display = 'flex';
    });
  });

  document.getElementById('join-cancel')?.addEventListener('click', () => {
    document.getElementById('join-modal').style.display = 'none';
  });

  document.getElementById('join-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl  = document.getElementById('join-error');
    errEl.style.display = 'none';

    const gameId     = document.getElementById('join-game-id').value;
    const playerName = document.getElementById('join-name').value.trim();
    const buyIn      = parseInt(document.getElementById('join-buyin').value, 10);

    if (!playerName) {
      showError(errEl, 'Please enter your name.');
      return;
    }

    try {
      const res = await fetch(`/api/games/${gameId}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: playerName, buy_in: buyIn }),
      });
      if (!res.ok) {
        const err = await res.json();
        showError(errEl, err.detail || 'Could not join game.');
        return;
      }
      const data = await res.json();
      sessionStorage.setItem('player_id',   data.player_id);
      sessionStorage.setItem('player_name', playerName);
      window.location.href = `/game/${gameId}`;
    } catch (err) {
      showError(errEl, 'Network error: ' + err.message);
    }
  });

  // ---- Refresh -------------------------------------------------------------
  document.getElementById('refresh-btn')?.addEventListener('click', async () => {
    try {
      const res  = await fetch('/api/games');
      const data = await res.json();
      _updateGamesList(data.games || []);
    } catch { /* ignore */ }
  });

  function showError(el, msg) {
    el.textContent    = msg;
    el.style.display  = 'block';
  }

  function _updateGamesList(games) {
    const list = document.getElementById('games-list');
    if (!list) return;
    if (!games.length) {
      list.innerHTML = '<p class="no-games">No open games. Create one!</p>';
      return;
    }
    list.innerHTML = games.map(g => `
      <div class="game-entry" data-game-id="${g.game_id}">
        <div class="game-info">
          <strong>${g.variant.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</strong>
          <span class="blinds">${g.small_blind}/${g.big_blind}</span>
          <span class="players">${g.players}/${g.max_players} players</span>
          <span class="phase badge">${g.phase}</span>
        </div>
        <button class="btn btn-secondary join-btn" data-game-id="${g.game_id}">Join</button>
      </div>
    `).join('');

    // Re-bind join buttons
    list.querySelectorAll('.join-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.getElementById('join-game-id').value = btn.dataset.gameId;
        document.getElementById('join-modal').style.display = 'flex';
      });
    });
  }
});
