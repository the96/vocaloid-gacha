import { drawSongs } from './draw.js';

const oneButton = document.querySelector('#draw-one');
const tenButton = document.querySelector('#draw-ten');
const status = document.querySelector('#status');
const cards = document.querySelector('#cards');
const empty = document.querySelector('#empty');
const count = document.querySelector('#result-count');
const artCount = document.querySelector('#art-count');
const source = 'https://w.atwiki.jp/hmiku/tag/%E6%AE%BF%E5%A0%82%E5%85%A5%E3%82%8A';
const storageKey = 'vocaloid-gacha-last-song';
let songs = [];
let previousId = null;

try { previousId = localStorage.getItem(storageKey); } catch { /* storage may be disabled */ }

function link(label, url) {
  const anchor = document.createElement('a');
  anchor.textContent = `${label} ↗`;
  anchor.href = url;
  anchor.target = '_blank';
  anchor.rel = 'noopener noreferrer';
  return anchor;
}

function render(picks) {
  const items = picks.map((song, index) => {
    const item = document.createElement('li');
    item.className = 'card';
    item.style.animationDelay = `${Math.min(index * 35, 300)}ms`;

    const top = document.createElement('div');
    top.className = 'card-top';
    const number = document.createElement('span');
    number.className = 'card-number';
    number.textContent = `TRACK ${String(index + 1).padStart(2, '0')}`;
    const spark = document.createElement('span');
    spark.className = 'card-spark';
    spark.setAttribute('aria-hidden', 'true');
    spark.textContent = '✳';
    top.append(number, spark);

    const title = document.createElement('h3');
    title.textContent = song.title;
    const composer = document.createElement('p');
    composer.className = 'composer';
    composer.textContent = song.composer ? `作曲：${song.composer}` : '作曲者：未確認';

    const links = document.createElement('div');
    links.className = 'card-links';
    links.append(link(song.wikiUrl ? 'Wiki の曲ページ' : '出典の一覧', song.wikiUrl || source));
    if (song.originalUrl) links.append(link('原曲を聴く', song.originalUrl));
    item.append(top, title, composer, links);
    return item;
  });
  cards.replaceChildren(...items);
  cards.hidden = false;
  empty.hidden = true;
  count.textContent = `${picks.length} / ${songs.length}`;
  status.textContent = `${picks.length}曲を選びました。もう一度引けます。`;
}

function draw(amount) {
  const picks = drawSongs(songs, amount, previousId);
  if (!picks.length) return;
  previousId = picks[picks.length - 1].wikiUrl || picks[picks.length - 1].title;
  try { localStorage.setItem(storageKey, previousId); } catch { /* storage may be disabled */ }
  render(picks);
}

oneButton.addEventListener('click', () => draw(1));
tenButton.addEventListener('click', () => draw(10));

try {
  const response = await fetch(new URL('./data/songs.json', import.meta.url));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  songs = data.songs.filter(song => typeof song.title === 'string' && song.title && typeof song.wikiUrl === 'string');
  if (songs.length < 2) throw new Error('曲数が足りません');
  oneButton.disabled = false;
  tenButton.disabled = songs.length < 10;
  artCount.textContent = songs.length.toLocaleString('ja-JP');
  count.textContent = `0 / ${songs.length}`;
  status.textContent = `${songs.length}曲を収録 · データ更新日 ${data.updatedAt}`;
} catch (error) {
  status.textContent = `曲データを読み込めませんでした。ページを再読み込みしてください。 (${error.message})`;
}
