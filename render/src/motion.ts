// Three layers of density, and a deck instead of a die.
//
// The lesson from the previous project: a reel dies of stillness long before it
// dies of ugliness. So something moves at every scale — the background always
// drifts, a small thing answers most words, and a large thing happens every
// couple of seconds. And effects are dealt from a shuffled deck rather than
// picked at random: uniform randomness produces three identical choices in a
// row often enough to read as a bug.

export type Density = {
  drift: number;   // 0..1, the always-on background movement
  pulse: number;   // 0..1, the micro answer to a word
  event: number;   // 0..1, the every-few-seconds accent
};

// Deterministic hash — the same beat always looks the same, which is what
// makes a re-render reproducible and a preview honest.
export const seeded = (seed: number) => {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
};

/** Deal `count` items from `options`, never repeating until the deck runs out. */
export const deal = <T,>(options: T[], count: number, seed: number): T[] => {
  const random = seeded(seed);
  const out: T[] = [];
  let deck: T[] = [];
  for (let i = 0; i < count; i++) {
    if (!deck.length) {
      deck = [...options];
      // Fisher-Yates on the seeded stream, so the shuffle is reproducible.
      for (let j = deck.length - 1; j > 0; j--) {
        const k = Math.floor(random() * (j + 1));
        [deck[j], deck[k]] = [deck[k], deck[j]];
      }
    }
    out.push(deck.pop() as T);
  }
  return out;
};

/** Where the three layers stand at this moment of the beat. */
export const density = (now: number, beatStart: number, wordStarts: number[]): Density => {
  const t = now - beatStart;

  // The background never stops; a slow sine is enough to keep the frame alive.
  const drift = (Math.sin(t * 0.7) + 1) / 2;

  // Every other word gets a pulse — answering every one turns into flicker.
  let pulse = 0;
  wordStarts.forEach((start, index) => {
    if (index % 2 !== 0) return;
    const since = now - start;
    if (since >= 0 && since < 0.32) pulse = Math.max(pulse, 1 - since / 0.32);
  });

  // And a bigger accent lands roughly every two and a half seconds.
  const beatPhase = t % 2.5;
  const event = beatPhase < 0.5 ? 1 - beatPhase / 0.5 : 0;

  return {drift, pulse, event};
};

/** Ease that overshoots slightly — things arrive rather than slide into place. */
export const overshoot = (t: number) => {
  const clamped = Math.max(0, Math.min(1, t));
  const c = 1.7;
  return 1 + (c + 1) * Math.pow(clamped - 1, 3) + c * Math.pow(clamped - 1, 2);
};
