import test from 'node:test';
import assert from 'node:assert/strict';
import { drawSongs, filterSongs } from '../draw.js';

const songs = Array.from({ length: 12 }, (_, i) => ({ title: `Song ${i}`, wikiUrl: `https://example.test/${i}` }));
const alwaysZero = { getRandomValues(array) { array[0] = 0; return array; } };

test('a single draw excludes the previous song', () => {
  const first = drawSongs(songs, 1, null, alwaysZero)[0];
  const second = drawSongs(songs, 1, first.wikiUrl, alwaysZero)[0];
  assert.notEqual(first.wikiUrl, second.wikiUrl);
});

test('ten draws contain ten distinct songs and exclude previous final pick', () => {
  const picks = drawSongs(songs, 10, songs[0].wikiUrl, alwaysZero);
  assert.equal(picks.length, 10);
  assert.equal(new Set(picks.map(song => song.wikiUrl)).size, 10);
  assert.ok(picks.every(song => song.wikiUrl !== songs[0].wikiUrl));
});

test('year and confirmed view floor filters combine', () => {
  const sample = [
    { releaseYear: 2020, viewCountFloor: 100000 },
    { releaseYear: 2020, viewCountFloor: 1000000 },
    { releaseYear: 2021, viewCountFloor: 10000000 },
  ];
  assert.deepEqual(filterSongs(sample, '2020', '500000'), [sample[1]]);
  assert.deepEqual(filterSongs(sample, '', '5000000'), [sample[2]]);
});
