// A cryptographically uniform integer avoids dependence on Math.random implementations.
export function randomIndex(length, randomValues = globalThis.crypto) {
  if (!Number.isSafeInteger(length) || length < 1 || length > 0x100000000) throw new RangeError('Invalid collection length');
  const range = 0x100000000;
  const limit = range - (range % length);
  const value = new Uint32Array(1);
  do { randomValues.getRandomValues(value); } while (value[0] >= limit);
  return value[0] % length;
}

export function drawSongs(songs, amount, previousId, randomValues = globalThis.crypto) {
  if (!Array.isArray(songs) || !Number.isSafeInteger(amount) || amount < 1) return [];
  const id = song => song.wikiUrl || song.title;
  // Exclude the previous final pick so the visible boundary never repeats.
  const pool = songs.filter(song => id(song) !== previousId);
  const result = [];
  const count = Math.min(amount, pool.length);
  for (let i = 0; i < count; i++) {
    const index = randomIndex(pool.length, randomValues);
    result.push(pool[index]);
    pool[index] = pool[pool.length - 1];
    pool.pop();
  }
  return result;
}

export function filterSongs(songs, releaseYearFrom = '', releaseYearTo = '', minimumViews = 0) {
  const hasYearRange = releaseYearFrom !== '' || releaseYearTo !== '';
  const from = releaseYearFrom === '' ? -Infinity : Number(releaseYearFrom);
  const to = releaseYearTo === '' ? Infinity : Number(releaseYearTo);
  const floor = Number(minimumViews) || 0;
  return songs.filter(song =>
    (!hasYearRange || (Number.isInteger(song.releaseYear) && song.releaseYear >= from && song.releaseYear <= to)) &&
    (Number(song.viewCountFloor) || 100000) >= floor
  );
}
