import { drawSongs, filterSongs } from './draw.js';
import { createSequence } from './sequence.js';

const oneButton = document.querySelector('#draw-one');
const tenButton = document.querySelector('#draw-ten');
const status = document.querySelector('#status');
const cards = document.querySelector('#cards');
const empty = document.querySelector('#empty');
const count = document.querySelector('#result-count');
const artCount = document.querySelector('#art-count');
const source = 'https://w.atwiki.jp/hmiku/tag/%E6%AE%BF%E5%A0%82%E5%85%A5%E3%82%8A';
const storageKey = 'vocaloid-gacha-last-song';
const stage = document.querySelector('#stage');
const stageCard = document.querySelector('#stage-card');
const stageProgress = document.querySelector('#stage-progress');
const skipButton = document.querySelector('#skip');
const shell = document.querySelector('.shell');
const resultsHeading = document.querySelector('#results-heading');
const yearFilter = document.querySelector('#year-filter');
const viewFilter = document.querySelector('#view-filter');
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let songs = [];
let eligibleSongs = [];
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

function songCard(song, index, tag = 'li') {
  const item = document.createElement(tag);
  item.className = 'card';
  const views = Number(song.viewCountFloor) || 100000;
  const rarity = views >= 5000000 ? 'ssr-plus' : views >= 1000000 ? 'ssr' : views >= 500000 ? 'sr' : 'normal';
  item.dataset.rarity = rarity;
  item.style.animationDelay = `${Math.min(index * 35, 300)}ms`;

  const top = document.createElement('div');
  top.className = 'card-top';
  const number = document.createElement('span');
  number.className = 'card-number';
  number.textContent = `TRACK ${String(index + 1).padStart(2, '0')}`;
  const spark = document.createElement('span');
  spark.className = 'card-spark';
  spark.setAttribute('aria-hidden', 'true');
  spark.textContent = rarity === 'ssr-plus' ? 'SSR+' : rarity === 'ssr' ? 'SSR' : rarity === 'sr' ? 'SR' : '✳';
  top.append(number, spark);

  const title = document.createElement('h3');
  title.textContent = song.title;
  const composer = document.createElement('p');
  composer.className = 'composer';
  composer.textContent = song.composer ? `作曲：${song.composer}` : '作曲者：未確認';
  const facts = document.createElement('p');
  facts.className = 'card-facts';
  const year = song.releaseYear ? `${song.releaseYear}年` : '年不明';
  const milestone = Number.isInteger(song.niconicoViewCount)
    ? `ニコニコ ${Math.floor(song.niconicoViewCount / 10000).toLocaleString('ja-JP')}万再生`
    : views >= 10000000 ? '1000万再生以上' : views >= 1000000 ? '100万再生以上' : '殿堂入り';
  facts.textContent = `${year} · ${milestone}`;

  const links = document.createElement('div');
  links.className = 'card-links';
  links.append(link(song.wikiUrl ? 'Wiki の曲ページ' : '出典の一覧', song.wikiUrl || source));
  if (song.originalUrl) links.append(link('原曲を聴く', song.originalUrl));
  const record = document.createElement('div');
  record.className = 'mini-record';
  record.setAttribute('aria-hidden', 'true');
  const sleeve = document.createElement('div');
  sleeve.className = 'card-copy';
  sleeve.append(top, title, composer, facts, links);
  item.append(record, sleeve);
  return item;
}

function render(picks) {
  const items = picks.map((song, index) => songCard(song, index));
  cards.replaceChildren(...items);
  cards.hidden = false;
  empty.hidden = true;
  count.textContent = `${picks.length} / ${eligibleSongs.length}`;
  status.textContent = `${picks.length}曲を選びました。もう一度引けます。`;
}

const sequence = createSequence({
  onPhase(phase, song, index, total) {
    stage.dataset.phase = phase;
    stageProgress.textContent = phase === 'spin' ? `${total}曲を抽選中…` : `${index + 1} / ${total}`;
    if (phase === 'reveal') stageCard.replaceChildren(songCard(song, index, 'article'));
    else stageCard.replaceChildren();
  },
  onFinish(picks) {
    stage.hidden = true;
    stageCard.replaceChildren();
    shell.inert = false;
    document.body.classList.remove('drawing');
    oneButton.disabled = false;
    tenButton.disabled = eligibleSongs.length < 10;
    render(picks);
    resultsHeading.focus({ preventScroll: true });
    resultsHeading.scrollIntoView({ behavior: 'instant', block: 'start' });
  },
});

function draw(amount) {
  if (sequence.active || !eligibleSongs.length) return;
  const picks = drawSongs(eligibleSongs, amount, previousId);
  if (!picks.length) return;
  previousId = picks[picks.length - 1].wikiUrl || picks[picks.length - 1].title;
  try { localStorage.setItem(storageKey, previousId); } catch { /* storage may be disabled */ }
  oneButton.disabled = true;
  tenButton.disabled = true;
  stage.hidden = false;
  stage.classList.toggle('reduced', motionPreference.matches);
  document.body.classList.add('drawing');
  shell.inert = true;
  skipButton.focus({ preventScroll: true });
  sequence.start(picks, motionPreference.matches);
}

skipButton.addEventListener('click', () => sequence.skip());
stage.addEventListener('keydown', event => {
  if (event.key === 'Escape') sequence.skip();
  // Keep keyboard focus inside the full-screen presentation.
  if (event.key === 'Tab') {
    const controls = [...stage.querySelectorAll('button, a[href]')].filter(el => el.getClientRects().length);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
motionPreference.addEventListener('change', () => {
  if (sequence.active && motionPreference.matches) sequence.skip();
});

oneButton.addEventListener('click', () => draw(1));
tenButton.addEventListener('click', () => draw(10));

function applyFilters() {
  eligibleSongs = filterSongs(songs, yearFilter.value, viewFilter.value);
  const total = eligibleSongs.length;
  oneButton.disabled = total < 1;
  tenButton.disabled = total < 10;
  count.textContent = `0 / ${total}`;
  status.textContent = total ? `${total.toLocaleString('ja-JP')}曲が抽選対象です。` : '条件に合う曲がありません。';
  cards.hidden = true;
  empty.hidden = false;
}

yearFilter.addEventListener('change', applyFilters);
viewFilter.addEventListener('change', applyFilters);

try {
  const response = await fetch(new URL('./data/songs.json', import.meta.url));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  songs = data.songs.filter(song => typeof song.title === 'string' && song.title && typeof song.wikiUrl === 'string');
  if (songs.length < 2) throw new Error('曲数が足りません');
  const years = [...new Set(songs.map(song => song.releaseYear).filter(Number.isInteger))].sort((a, b) => b - a);
  yearFilter.append(...years.map(year => Object.assign(document.createElement('option'), { value: String(year), textContent: `${year}年` })));
  artCount.textContent = songs.length.toLocaleString('ja-JP');
  applyFilters();
  status.textContent = `${songs.length.toLocaleString('ja-JP')}曲を収録 · データ更新日 ${data.updatedAt}`;
} catch (error) {
  status.textContent = `曲データを読み込めませんでした。ページを再読み込みしてください。 (${error.message})`;
}
