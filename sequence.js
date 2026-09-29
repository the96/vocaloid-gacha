// A single cancellable timer owns the sequence. Stale callbacks cannot reveal
// cards or finish a later draw after a skip.
export function createSequence({ onPhase, onFinish, schedule = setTimeout, cancel = clearTimeout }) {
  let timer;
  let generation = 0;
  let active = false;
  let picks = [];
  const finish = () => {
    if (!active) return false;
    active = false;
    generation++;
    cancel(timer);
    onFinish(picks);
    return true;
  };
  return {
    get active() { return active; },
    start(nextPicks, reduced = false) {
      if (active || !nextPicks.length) return false;
      active = true;
      picks = [...nextPicks];
      const token = ++generation;
      let index = 0;
      const later = (fn, ms) => {
        timer = schedule(() => { if (active && token === generation) fn(); }, ms);
      };
      const reveal = () => {
        onPhase('reveal', picks[index], index, picks.length);
        later(() => {
          index++;
          if (index === picks.length) finish();
          else if (reduced) reveal();
          else flash();
        }, reduced ? 1000 : 1400);
      };
      const flash = () => {
        onPhase('flash', picks[index], index, picks.length);
        later(reveal, 240);
      };
      if (reduced) {
        // Let reveal own its hold timer in both modes.
        reveal();
      } else {
        onPhase('spin', picks[0], 0, picks.length);
        later(flash, 2600);
      }
      return true;
    },
    skip: finish,
  };
}
