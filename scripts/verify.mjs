import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const html = readFileSync('index.html', 'utf8');
const data = JSON.parse(readFileSync('data/songs.json', 'utf8'));
assert.match(html, /\.\/styles\.css/);
assert.match(html, /\.\/app\.js/);
assert.match(html, /初音ミク Wiki/);
assert.ok(data.songs.length >= 10, 'At least 10 songs are required');

const ids = new Set();
for (const song of data.songs) {
  assert.ok(typeof song.title === 'string' && song.title.trim(), 'Song title is required');
  assert.ok(typeof song.composer === 'string' || song.composer === null, 'Composer must be a name or null');
  assert.ok(typeof song.wikiUrl === 'string', 'Wiki URL must be a string');
  assert.ok(song.originalUrl === null || /^https:\/\/(www\.nicovideo\.jp|www\.youtube\.com)\//.test(song.originalUrl), 'Original URL must be an approved video link');
  if (song.wikiUrl) assert.match(song.wikiUrl, /^https:\/\/w\.atwiki\.jp\/hmiku\/pages\/\d+\.html$/);
  const id = song.wikiUrl || song.title;
  assert.ok(!ids.has(id), `Duplicate song: ${id}`);
  ids.add(id);
}
console.log(`Static build verified: ${data.songs.length} songs. No bundling required.`);
