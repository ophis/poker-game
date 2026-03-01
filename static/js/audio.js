/**
 * audio.js — Web Audio API sound effects for the poker game.
 *
 * All sounds are synthesized (no external files needed).
 * Lazy-initializes AudioContext on first user gesture.
 */
window.SoundManager = (() => {
  let _ctx = null;
  let _muted = false;

  function _getCtx() {
    if (!_ctx) {
      _ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return _ctx;
  }

  function resume() {
    if (_ctx && _ctx.state === 'suspended') {
      _ctx.resume();
    }
  }

  // Resume on first click anywhere (handles autoplay policy)
  document.addEventListener('click', () => {
    _getCtx();
    resume();
  }, { once: true });

  /**
   * Schedule an oscillator tone.
   * @param {number} freq   - frequency in Hz
   * @param {number} dur    - duration in seconds
   * @param {string} type   - oscillator type ('sine'|'square'|'sawtooth'|'triangle')
   * @param {number} gain   - peak gain (0–1)
   * @param {number} delay  - start delay in seconds from now
   */
  function _tone(freq, dur, type, gain, delay) {
    const ctx = _getCtx();
    const t = ctx.currentTime + (delay || 0);

    const osc = ctx.createOscillator();
    const env = ctx.createGain();

    osc.type = type || 'sine';
    osc.frequency.setValueAtTime(freq, t);

    env.gain.setValueAtTime(0, t);
    env.gain.linearRampToValueAtTime(gain, t + 0.005);
    env.gain.exponentialRampToValueAtTime(0.0001, t + dur);

    osc.connect(env);
    env.connect(ctx.destination);

    osc.start(t);
    osc.stop(t + dur + 0.01);
  }

  /**
   * Short white-noise burst through a bandpass filter.
   * @param {number} dur      - duration in seconds
   * @param {number} gain     - peak gain
   * @param {number} freq     - bandpass center frequency
   * @param {number} delay    - start delay in seconds from now
   */
  function _noise(dur, gain, freq, delay) {
    const ctx = _getCtx();
    const t = ctx.currentTime + (delay || 0);

    const bufferSize = Math.ceil(ctx.sampleRate * dur);
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = Math.random() * 2 - 1;
    }

    const src = ctx.createBufferSource();
    src.buffer = buffer;

    const filter = ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.value = freq || 2000;
    filter.Q.value = 0.8;

    const env = ctx.createGain();
    env.gain.setValueAtTime(gain, t);
    env.gain.exponentialRampToValueAtTime(0.0001, t + dur);

    src.connect(filter);
    filter.connect(env);
    env.connect(ctx.destination);

    src.start(t);
    src.stop(t + dur + 0.01);
  }

  // ---- Named sounds --------------------------------------------------------

  const _sounds = {
    /** Short filtered noise burst — card deal / swish */
    deal() {
      _noise(0.12, 0.25, 3000, 0);
      _noise(0.08, 0.15, 1500, 0.05);
    },

    /** Two-tone click — chip clink */
    chip() {
      _tone(900, 0.07, 'sine', 0.4, 0);
      _tone(1200, 0.05, 'sine', 0.25, 0.04);
    },

    /** Noise + low tone — card slide (fold) */
    fold() {
      _noise(0.15, 0.2, 800, 0);
      _tone(220, 0.12, 'triangle', 0.2, 0.02);
    },

    /** Short square-wave click — check */
    check() {
      _tone(440, 0.05, 'square', 0.15, 0);
    },

    /** Two-note ascending chime — your turn (C5 → E5) */
    yourTurn() {
      _tone(523.25, 0.18, 'sine', 0.35, 0);     // C5
      _tone(659.25, 0.22, 'sine', 0.35, 0.18);  // E5
    },

    /** Four-note ascending arpeggio — win */
    win() {
      _tone(523.25, 0.15, 'sine', 0.3, 0);      // C5
      _tone(659.25, 0.15, 'sine', 0.3, 0.15);   // E5
      _tone(783.99, 0.15, 'sine', 0.3, 0.30);   // G5
      _tone(1046.5, 0.3,  'sine', 0.35, 0.45);  // C6
    },

    /** Two-note descending tone — lose */
    lose() {
      _tone(392.0, 0.2, 'sine', 0.3, 0);   // G4
      _tone(261.63, 0.3, 'sine', 0.3, 0.2); // C4
    },
  };

  /**
   * Play a named sound. No-ops if muted or sound doesn't exist.
   * @param {string} name
   */
  function play(name) {
    if (_muted) return;
    if (_sounds[name]) {
      try {
        // Ensure context is running before each play
        const ctx = _getCtx();
        if (ctx.state === 'suspended') ctx.resume();
        _sounds[name]();
      } catch (e) {
        console.warn('SoundManager.play error:', e);
      }
    }
  }

  function toggleMute() {
    _muted = !_muted;
    return _muted;
  }

  function isMuted() {
    return _muted;
  }

  return { play, resume, toggleMute, isMuted };
})();
