#!/usr/bin/env python3
"""Collect factual metadata for tag pages 1–148, with metadata-only checkpoints.

HTML is parsed in memory and discarded. No lyrics, article text, media or images
are saved. Never bypass a challenge: stop and preserve the checkpoint instead.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://w.atwiki.jp/hmiku/tag/%E6%AE%BF%E5%A0%82%E5%85%A5%E3%82%8A'
OUTPUT = ROOT / 'data/songs.json'
PAGE_RE = re.compile(r'^/hmiku/pages/(\d+)\.html$')
PARSER_VERSION = 4


class Blocked(RuntimeError):
    pass


class Node:
    def __init__(self, tag='', attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs or []), parent
        self.children = []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        if self.tag in ('script', 'style'):
            return ''
        if self.tag == 'br':
            return '\n'
        text = ''.join(c.text() if isinstance(c, Node) else c for c in self.children)
        return text + ('\n' if self.tag in ('div', 'p', 'li', 'tr', 'h2', 'h3') else '')


class WikiHTML(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'wbr'}

    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.current = self.root
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def wiki_url(href):
    url = urlparse(urljoin(SOURCE, href))
    match = PAGE_RE.fullmatch(url.path)
    if url.hostname == 'w.atwiki.jp' and match:
        return f'https://w.atwiki.jp/hmiku/pages/{match[1]}.html'
    return None


def tag_songs(document):
    anchors = [n for n in WikiHTML(document).root.walk() if n.tag == 'a']
    pager = lambda n: unquote(urlparse(urljoin(SOURCE, n.attrs.get('href', ''))).path) == unquote(urlparse(SOURCE).path) and bool(re.search(r'[?&]p=\d+', n.attrs.get('href', '')))
    positions = [i for i, node in enumerate(anchors) if pager(node)]
    if len(positions) < 2:
        raise ValueError('Tag pagination not found; real HTML must be inspected')
    start = positions[0]
    while start < len(anchors) and not wiki_url(anchors[start].attrs.get('href', '')):
        start += 1
    result = []
    end_found = False
    for node in anchors[start:]:
        if pager(node):
            end_found = True
            break
        url = wiki_url(node.attrs.get('href', ''))
        title = node.text().strip()
        if url and title:
            result.append({'title': title, 'wikiUrl': url, 'composer': None, 'originalUrl': None})
    if not end_found or not 1 <= len(result) <= 50:
        raise ValueError(f'Unexpected tag structure or song count: {len(result)}')
    if len({s['wikiUrl'] for s in result}) != len(result):
        raise ValueError('Duplicate song links within a tag page')
    return result, max(int(parse_qs(urlparse(n.attrs['href']).query)['p'][0]) for n in anchors if pager(n))


def video_url(raw):
    url = urlparse(urljoin('https://w.atwiki.jp', raw))
    host = url.hostname or ''
    if host in ('www.nicovideo.jp', 'nicovideo.jp', 'ext.nicovideo.jp'):
        match = re.fullmatch(r'/(?:watch|thumb)/(sm\d+|nm\d+|so\d+)', url.path)
        if match:
            return f'https://www.nicovideo.jp/watch/{match[1]}'
    if host in ('www.youtube.com', 'youtube.com', 'www.youtube-nocookie.com'):
        vid = url.path.removeprefix('/embed/') if url.path.startswith('/embed/') else parse_qs(url.query).get('v', [''])[0] if url.path == '/watch' else ''
    elif host == 'youtu.be':
        vid = url.path.lstrip('/')
    else:
        vid = ''
    return f'https://www.youtube.com/watch?v={vid}' if re.fullmatch(r'[\w-]{11}', vid) else None


def song_details(document):
    root = WikiHTML(document).root
    # Scope attribution to the article, never navigation, comments or ads.
    bodies = [n for n in root.walk() if n.attrs.get('id') in ('wikibody', 'atwiki-content')]
    if not bodies:
        raise ValueError('Article container not found; inspect actual HTML before updating')
    body = next((n for n in bodies if n.attrs.get('id') == 'wikibody'), bodies[0])
    # Real pages put a generated table of contents (including the word 歌詞)
    # before the credit block. Inspect only direct children before the first
    # article section instead of truncating the flattened body at that word.
    front_matter = []
    for child in body.children:
        if not isinstance(child, Node):
            continue
        if child.tag in ('h3', 'h4'):
            break
        front_matter.append(child)
    def metadata_text(value):
        if isinstance(value, str):
            return value
        if value.tag in ('script', 'style'):
            return ''
        if value.tag == 'br':
            return '\n'
        # Some pages contain a corrupt/repeated visible producer name, while
        # the Wiki link title still carries the canonical page name plus age.
        # This is an explicit credit attribute, not a guess from tags/title.
        if value.tag == 'a' and value.attrs.get('title'):
            title = re.sub(r'\s+\(\d+d\)$', '', value.attrs['title']).strip()
            if title:
                return title
        return ''.join(metadata_text(child) for child in value.children)

    text = '\n'.join(metadata_text(node) for node in front_matter)
    # Accept combined labels such as 作詞・作曲・編曲・動画, but require the
    # literal 作曲 field in front matter. Labels such as 制作/聴覚 stay unknown.
    credit_pattern = re.compile(r'(?:^|\n)\s*(?:[^：:\n]*作曲[^：:\n]*)\s*[：:]\s*([^\n]+)')
    matches = credit_pattern.findall(text)
    names = sorted({re.sub(r'\s+', ' ', s).strip() for s in matches})
    # Stop at another credit on the same line rather than swallowing its author.
    names = [re.split(r'\s+(?:編曲|作詞|唄|歌|調声|動画|イラスト)\s*[：:]', s)[0].strip() for s in names]
    names = sorted(set(names))
    issues = []
    composer = names[0] if len(names) == 1 and 0 < len(names[0]) <= 100 else None
    if not composer:
        issues.append('composer_conflict' if len(names) > 1 else 'composer_unconfirmed')
    candidates = []
    # On actual article pages the canonical post is in a dedicated media block
    # immediately before the credit block. Later embeds belong to descriptions,
    # related videos or comments and must never displace this primary link.
    credit_index = next((i for i, node in enumerate(front_matter) if credit_pattern.search(metadata_text(node))), None)
    primary_url = None
    if credit_index is not None:
        for node in reversed(front_matter[:credit_index]):
            urls = []
            for nested in node.walk():
                raw = nested.attrs.get('src') if nested.tag in ('iframe', 'embed') else nested.attrs.get('href') if nested.tag == 'a' else None
                url = video_url(raw) if raw else None
                if url and url not in urls:
                    urls.append(url)
            if urls:
                primary_url = urls[0]
                break
    for node in body.walk():
        raw = node.attrs.get('src') if node.tag in ('iframe', 'embed') else node.attrs.get('href') if node.tag == 'a' else None
        url = video_url(raw) if raw else None
        if not url:
            continue
        context = node.parent
        while context.parent and context != body and context.tag not in ('td', 'p', 'li'):
            context = context.parent
        label = context.text()
        cover = bool(re.search(r'カバー|cover|歌ってみた|アレンジ|リミックス|remix', label, re.I))
        reason = 'primary_article_media' if url == primary_url else 'cover_context' if cover else 'original_label_requires_review' if re.search(r'原曲|オリジナル', label) else 'unclassified_embed_or_link'
        candidate = {'url': url, 'reason': reason}
        if candidate not in candidates:
            candidates.append(candidate)
    if not primary_url:
        issues.append('original_unconfirmed')
    return {'composer': composer, 'originalUrl': primary_url, 'videoCandidates': candidates, 'issues': issues}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def stamp():
    return datetime.now(timezone.utc).isoformat()


class Fetcher:
    def __init__(self, delay=1.5):
        self.delay = delay
        self.last = None

    def __call__(self, url):
        for attempt in range(3):
            if self.last is not None:
                time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
            try:
                self.last = time.monotonic()
                request = Request(url, headers={'User-Agent': 'vocaloid-gacha-metadata/2.0 (+https://github.com/the96/vocaloid-gacha)', 'Accept': 'text/html'})
                with urlopen(request, timeout=30) as response:
                    text = response.read().decode('utf-8')
                    if response.headers.get('cf-mitigated') == 'challenge' or 'cf-chl-' in text:
                        raise Blocked('Site security challenge; stopped without bypassing')
                    return text
            except HTTPError as error:
                if error.code in (401, 403, 429):
                    raise Blocked(f'HTTP {error.code}; stopped. Checkpoint retained.') from error
                if error.code not in (408, 500, 502, 503, 504) or attempt == 2:
                    raise
            except (URLError, TimeoutError, ConnectionError):
                if attempt == 2:
                    raise
            time.sleep(self.delay * (2 ** (attempt + 1)))


def collect(pages=148, delay=1.5, cache=None, output=OUTPUT, report=None, fetcher=None, overrides=None, index_only=False):
    cache = Path(cache or ROOT / '.cache/song-metadata.json')
    report = Path(report or ROOT / 'data/collection-report.json')
    state = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {'version': PARSER_VERSION, 'source': SOURCE, 'pages': {}, 'details': {}}
    if state.get('source') != SOURCE or state.get('version') not in (2, 3, PARSER_VERSION):
        raise ValueError('Incompatible checkpoint: use a new --cache path')
    if state.get('version') == 2:
        # Version 2 split the flattened body at the table-of-contents word 歌詞,
        # so its detail results are not trustworthy. Preserve costly index work,
        # but re-fetch detail pages with the real-HTML-tested parser.
        state['version'] = PARSER_VERSION
        state['details'] = {}
        atomic_json(cache, state)
    elif state.get('version') == 3:
        # Version 4 improves only unresolved composer credits. Keep every
        # confirmed detail and retry the small unknown subset from real HTML.
        state['version'] = PARSER_VERSION
        state['details'] = {url: detail for url, detail in state['details'].items() if detail.get('composer') is not None}
        atomic_json(cache, state)
    fetcher = fetcher or Fetcher(delay)
    errors = {}
    halt = None
    reviewed = json.loads(Path(overrides).read_text(encoding='utf-8')) if overrides else {}
    for url, fields in reviewed.items():
        if wiki_url(url) != url or not fields.get('checkedAt') or not fields.get('reason'):
            raise ValueError('Reviewed entries require canonical wikiUrl, checkedAt and reason')
        if fields.get('originalUrl') and video_url(fields['originalUrl']) != fields['originalUrl']:
            raise ValueError(f'Invalid reviewed video URL for {url}')
        if fields.get('composer') is not None and (not isinstance(fields['composer'], str) or not fields['composer'].strip()):
            raise ValueError(f'Invalid reviewed composer for {url}')

    def save():
        atomic_json(cache, state)

    for page in range(1, pages + 1):
        key = str(page)
        if key in state['pages']:
            continue
        url = SOURCE if page == 1 else f'{SOURCE}?p={page}'
        try:
            songs, last_page = tag_songs(fetcher(url))
            # Redirects to the first/last page are not successful pagination.
            signature = [s['wikiUrl'] for s in songs]
            if any(signature == [s['wikiUrl'] for s in p['songs']] for p in state['pages'].values()):
                raise ValueError('Repeated tag page: possible redirect or pagination failure')
            state['pages'][key] = {'songs': songs, 'lastPageAdvertised': last_page, 'checkedAt': stamp()}
            save()
            print(f'Tag {page}/{pages}: {len(songs)}', file=sys.stderr, flush=True)
        except (Blocked, OSError, ValueError) as error:
            errors[f'page:{page}'] = str(error)
            halt = str(error)
            break  # Do not hammer the remaining pages when access/markup fails.

    gathered = {}
    occurrences = defaultdict(list)
    for key, page in sorted(state['pages'].items(), key=lambda item: int(item[0])):
        if int(key) > pages:
            continue
        for song in page['songs']:
            occurrences[song['wikiUrl']].append(int(key))
            gathered.setdefault(song['wikiUrl'], dict(song))
    duplicate_urls = {url: ps for url, ps in occurrences.items() if len(ps) > 1}
    if not halt and not index_only:
        for index, url in enumerate(gathered, 1):
            if url in state['details']:
                continue
            try:
                state['details'][url] = {**song_details(fetcher(url)), 'checkedAt': stamp()}
                save()
                print(f'Detail {index}/{len(gathered)}', file=sys.stderr, flush=True)
            except Blocked as error:
                halt = str(error)
                errors[url] = halt
                break
            except (OSError, ValueError) as error:
                errors[url] = str(error)
                # Missing details remain absent and are retried on the next run.

    songs = []
    for url, song in gathered.items():
        detail = state['details'].get(url, {})
        song.update(composer=detail.get('composer'), originalUrl=detail.get('originalUrl'))
        for field in ('composer', 'originalUrl'):
            if field in reviewed.get(url, {}):
                song[field] = reviewed[url][field]
        songs.append(song)
    missing_pages = [p for p in range(1, pages + 1) if str(p) not in state['pages']]
    missing_details = [url for url in gathered if url not in state['details']]
    title_counts = Counter(s['title'] for s in songs)
    original_occurrences = defaultdict(list)
    for song in songs:
        if song['originalUrl']:
            original_occurrences[song['originalUrl']].append(song['wikiUrl'])
    duplicate_original_urls = {url: urls for url, urls in original_occurrences.items() if len(urls) > 1}
    page_counts = {p: len(state['pages'][str(p)]['songs']) for p in range(1, pages + 1) if str(p) in state['pages']}
    short_pages = [p for p, count in page_counts.items() if p < pages and count != 50]
    complete_index = not missing_pages and not duplicate_urls and not short_pages
    publish = complete_index and not halt
    result = {
        'checkedAt': stamp(), 'source': SOURCE, 'requestedPages': list(range(1, pages + 1)),
        'status': 'blocked' if halt else 'index_incomplete' if not complete_index else 'details_incomplete' if missing_details else 'complete',
        'published': publish, 'pagesFetched': pages - len(missing_pages), 'missingPages': missing_pages,
        'pageCounts': page_counts, 'unexpectedPageSizes': short_pages,
        'uniqueSongs': len(songs), 'missingSongCount': None if missing_pages else 0,
        'detailsFetched': len(songs) - len(missing_details), 'missingDetails': missing_details,
        'composerUnconfirmed': sum(s['composer'] is None for s in songs),
        'originalUnconfirmed': sum(s['originalUrl'] is None for s in songs),
        'duplicateWikiUrls': duplicate_urls,
        'duplicateOriginalUrls': duplicate_original_urls,
        'duplicateTitles': [t for t, n in title_counts.items() if n > 1],
        'reviewRequired': {
            u: {'issues': d['issues'], 'videoCandidates': d['videoCandidates']}
            for u, d in state['details'].items()
            if u in gathered and (
                d['issues'] or any(candidate['reason'] != 'primary_article_media' for candidate in d['videoCandidates'])
            )
        },
        'errors': errors,
    }
    if publish:
        atomic_json(Path(output), {'updatedAt': stamp()[:10], 'source': SOURCE, 'coverage': {'pages': list(range(1, pages + 1)), 'detailsFetched': result['detailsFetched']}, 'songs': songs})
    atomic_json(report, result)
    print(json.dumps({k: result[k] for k in ('status', 'published', 'pagesFetched', 'uniqueSongs', 'detailsFetched', 'composerUnconfirmed', 'originalUnconfirmed')}, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', type=int, default=148)
    parser.add_argument('--delay', type=float, default=1.5)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--overrides', type=Path, help='Reviewed metadata keyed by canonical Wiki URL')
    parser.add_argument('--index-only', action='store_true', help='Collect all titles/URLs; details can be resumed later')
    args = parser.parse_args()
    if args.pages < 1 or args.delay < 0.5:
        parser.error('--pages must be positive; --delay must be at least 0.5')
    result = collect(**vars(args))
    return 0 if result['status'] == 'complete' else 2


if __name__ == '__main__':
    sys.exit(main())
