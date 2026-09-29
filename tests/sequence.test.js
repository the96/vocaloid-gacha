import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSequence } from '../sequence.js';

function setup() {
  const queued = [];
  const phases = [];
  const results = [];
  const sequence = createSequence({
    schedule: fn => { queued.push(fn); return queued.length; },
    // Deliberately do not remove cancelled callbacks to simulate an event that
    // was already queued when skip was pressed.
    cancel: () => {},
    onPhase: (phase, song, index) => phases.push({ phase, song, index }),
    onFinish: picks => results.push(picks),
  });
  return { sequence, phases, results, tick: () => queued.shift()?.(), flush: () => { while (queued.length) queued.shift()(); } };
}

test('one draw progresses spin → flash → reveal → results', () => {
  const s = setup();
  assert.equal(s.sequence.start(['A']), true);
  s.flush();
  assert.deepEqual(s.phases.map(p => p.phase), ['spin', 'flash', 'reveal']);
  assert.deepEqual(s.results, [['A']]);
  assert.equal(s.sequence.active, false);
});

test('ten songs are revealed in order before a single finish', () => {
  const s = setup();
  const picks = Array.from({ length: 10 }, (_, i) => i);
  s.sequence.start(picks);
  s.flush();
  assert.deepEqual(s.phases.filter(p => p.phase === 'reveal').map(p => p.song), picks);
  assert.deepEqual(s.results, [picks]);
});

test('rapid clicks cannot replace picks; skip cancels all stale work', () => {
  const s = setup();
  s.sequence.start(['A']);
  assert.equal(s.sequence.start(['B']), false);
  s.sequence.skip();
  assert.equal(s.sequence.skip(), false);
  s.sequence.start(['C']);
  s.flush();
  assert.deepEqual(s.results, [['A'], ['C']]);
  assert.deepEqual(s.phases.filter(p => p.phase === 'reveal').map(p => p.song), ['C']);
});

test('skip works during every phase and preserves all ten results', () => {
  for (let elapsed = 0; elapsed < 20; elapsed++) {
    const s = setup();
    const picks = Array.from({ length: 10 }, (_, i) => i);
    s.sequence.start(picks);
    for (let i = 0; i < elapsed; i++) s.tick();
    s.sequence.skip();
    const before = s.phases.length;
    s.flush();
    assert.equal(s.phases.length, before);
    assert.deepEqual(s.results, [picks]);
  }
});

test('reduced motion reveals sequentially without spinning or flashes', () => {
  const s = setup();
  s.sequence.start(['A', 'B'], true);
  s.flush();
  assert.deepEqual(s.phases.map(p => p.phase), ['reveal', 'reveal']);
  assert.deepEqual(s.results, [['A', 'B']]);
});
