/**
 * websocket.js — WS lifecycle, message dispatch.
 *
 * Reads game_id and player_id from page meta tags.
 * Dispatches incoming events to GameState and Renderer.
 */
window.PokerWS = (() => {
  let _ws = null;
  let _reconnectTimer = null;
  let _gameId = null;
  let _playerId = null;

  function init(gameId, playerId) {
    _gameId   = gameId;
    _playerId = playerId;
    window.GameState.update({ gameId, playerId });
    _connect();
  }

  function _connect() {
    window.Renderer.setConnectionStatus('connecting');
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url   = `${proto}://${location.host}/ws/${_gameId}/${_playerId}`;
    _ws = new WebSocket(url);

    _ws.onopen = () => {
      window.Renderer.setConnectionStatus('connected');
      clearTimeout(_reconnectTimer);
    };

    _ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      _dispatch(msg.type, msg.payload || {});
    };

    _ws.onclose = () => {
      window.Renderer.setConnectionStatus('disconnected');
      _reconnectTimer = setTimeout(_connect, 3000);
    };

    _ws.onerror = () => {
      _ws.close();
    };
  }

  function _dispatch(type, payload) {
    switch (type) {
      case 'game_state':
        window.GameState.applyGameState(payload);
        window.Renderer.render();
        window.Renderer.hideActions();
        break;

      case 'hand_starting':
        window.GameState.addAction({ type: 'separator' });
        window.GameState.applyGameState(payload);
        window.GameState.update({ lastWinners: null, myTurn: false, validActions: null });
        window.Renderer.clearActionLabels();
        window.Renderer.render();
        window.Renderer.hideActions();
        window.Renderer.showHandName('');
        break;

      case 'community_card': {
        const phase = (payload.phase || '').toUpperCase().replace(/_/g, ' ');
        if (phase) {
          window.GameState.addAction({ type: 'phase', text: phase });
        }
        window.GameState.applyGameState(payload);
        window.Renderer.render();
        break;
      }

      case 'your_turn':
        if (payload.player_id === _playerId) {
          window.GameState.update({
            myTurn: true,
            validActions: payload.valid_actions,
          });
          window.Renderer.showActions(payload.valid_actions);
        }
        break;

      case 'action_taken':
        // Update pot immediately
        window.GameState.update({ pot: payload.pot });
        window.GameState.addAction({
          type: 'action',
          name: payload.name,
          action: payload.action,
          amount: payload.amount,
        });
        window.Renderer.render();
        window.Renderer.showPlayerAction(payload.player_id, payload.action, payload.amount);
        if (payload.player_id === _playerId) {
          window.Renderer.hideActions();
          window.GameState.update({ myTurn: false });
        }
        break;

      case 'pot_update':
        window.GameState.update({ pot: payload.pot });
        window.Renderer.render();
        break;

      case 'winner': {
        const winners = payload.winners || [];
        winners.forEach(w => {
          const wName = _getPlayerName(w.player_id);
          window.GameState.addAction({
            type: 'winner',
            text: `${wName} wins $${w.amount}`,
          });
        });
        window.GameState.update({ lastWinners: payload });
        // Reveal all players' hole cards in the seats for the showdown.
        // The server sends all_hands explicitly here — this is the only place
        // opponent cards are revealed, keeping game_state snapshots private.
        if (payload.all_hands) {
          const s = window.GameState.get();
          s.players.forEach(p => {
            const hand = payload.all_hands[p.player_id];
            if (hand && hand.hole_cards) {
              p.hole_cards = hand.hole_cards;
            }
          });
          window.Renderer.render();
        }
        window.Renderer.hideActions();
        window.GameState.update({ myTurn: false });
        window.Renderer.showWinner(payload);
        break;
      }

      case 'hand_over':
        window.GameState.applyGameState(payload);
        window.Renderer.render();
        window.Renderer.hideActions();
        break;

      case 'chat':
        {
          const name = _getPlayerName(payload.player_id) || payload.player_id;
          window.Renderer.addChatMessage(name, payload.message);
          // Show badge if chat is collapsed
          const panel = document.getElementById('chat-panel');
          if (panel && panel.classList.contains('collapsed')) {
            const badge = document.getElementById('chat-badge');
            if (badge) badge.style.display = 'inline';
          }
        }
        break;

      case 'game_over':
        window.Renderer.hideActions();
        window.GameState.update({ myTurn: false });
        window.Renderer.showGameOver(payload.winner_name, payload.winner_chips);
        break;

      case 'error':
        console.warn('Server error:', payload.message);
        break;

      case 'pong':
        break;

      default:
        console.log('Unknown event:', type, payload);
    }
  }

  function _getPlayerName(playerId) {
    const s = window.GameState.get();
    const p = s.players.find(p => p.player_id === playerId);
    return p ? p.name : playerId;
  }

  function sendAction(action, amount) {
    _send({ type: 'action', payload: { action, amount } });
  }

  function sendChat(message) {
    _send({ type: 'chat', payload: { message } });
  }

  function _send(obj) {
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify(obj));
    }
  }

  // ---- Bootstrap -----------------------------------------------------------
  // Auto-init from meta tags on page load
  document.addEventListener('DOMContentLoaded', () => {
    const gameId   = document.querySelector('meta[name="game-id"]')?.content;
    const playerId = sessionStorage.getItem('player_id');

    if (!gameId || !playerId) {
      // Redirect to lobby if missing
      window.location.href = '/';
      return;
    }

    const playerName = sessionStorage.getItem('player_name') || 'You';
    window.GameState.update({ playerName });

    // Init controls first
    window.Controls.init();

    // Connect WS
    init(gameId, playerId);
  });

  return { init, sendAction, sendChat };
})();
