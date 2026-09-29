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

const report = JSON.parse(readFileSync('data/collection-report.json', 'utf8'));
if (process.argv.includes('--complete')) {
  assert.equal(report.published, true, 'Full collection is incomplete; see data/collection-report.json');
  assert.equal(report.pagesFetched, 148, 'All requested 148 pages must be fetched');
  assert.deepEqual(report.missingPages, []);
  assert.equal(Object.keys(report.duplicateWikiUrls).length, 0);
  assert.ok(report.duplicateOriginalUrls && typeof report.duplicateOriginalUrls === 'object');
  assert.deepEqual(data.coverage?.pages, Array.from({ length: 148 }, (_, i) => i + 1));
  assert.equal(report.uniqueSongs, data.songs.length);
  assert.deepEqual(report.unexpectedPageSizes, []);
  for (let page = 1; page < 148; page++) assert.equal(report.pageCounts[page], 50);
  assert.ok(report.pageCounts[148] >= 1 && report.pageCounts[148] <= 50);
  assert.equal(report.detailsFetched, data.songs.length, 'Detail pages remain unfetched');
  assert.ok(data.songs.every(song => song.wikiUrl), 'Every collected song needs a Wiki page URL');
  const duplicateOriginalCount = Object.keys(report.duplicateOriginalUrls).length;
  if (duplicateOriginalCount) console.warn(`${duplicateOriginalCount} original video URL(s) are shared by multiple Wiki pages; review report.`);
  console.log('148-page collection verified. Unknown metadata remains explicitly null.');
} else if (!report.published) {
  console.warn('Data expansion INCOMPLETE. Build success does not certify 148-page collection.');
}
