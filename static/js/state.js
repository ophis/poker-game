/**
 * state.js — Client-side state store (plain object, never touches DOM).
 *
 * Import: window.GameState
 */
window.GameState = (() => {
  const _state = {
    gameId: null,
    playerId: null,
    playerName: null,
    phase: 'waiting',
    variant: 'no_limit',
    players: [],
    communityCards: [],
    pot: 0,
    handNumber: 0,
    dealerIndex: 0,
    currentPlayerIndex: -1,
    smallBlind: 0,
    bigBlind: 0,
    myTurn: false,
    validActions: null,     // { can_check, call_amount, min_raise, max_raise, can_raise }
    myHoleCards: [],
    lastWinners: null,
    chatMessages: [],
    actionHistory: [],
  };

  function update(patch) {
    Object.assign(_state, patch);
  }

  function addAction(entry) {
    _state.actionHistory.push(entry);
  }

  function clearActions() {
    _state.actionHistory = [];
  }

  function applyGameState(payload) {
    _state.phase             = payload.phase;
    _state.variant           = payload.variant;
    _state.players           = payload.players || [];
    _state.communityCards    = payload.community_cards || [];
    _state.pot               = payload.pot || 0;
    _state.handNumber        = payload.hand_number || 0;
    _state.dealerIndex       = payload.dealer_index ?? 0;
    _state.currentPlayerIndex = payload.current_player_index ?? -1;
    _state.smallBlind        = payload.small_blind || 0;
    _state.bigBlind          = payload.big_blind || 0;

    // Update my own hole cards
    const me = _state.players.find(p => p.player_id === _state.playerId);
    if (me && me.hole_cards) {
      _state.myHoleCards = me.hole_cards;
    }
  }

  function getMe() {
    return _state.players.find(p => p.player_id === _state.playerId) || null;
  }

  function get() {
    return _state;
  }

  return { update, applyGameState, getMe, get, addAction, clearActions };
})();
