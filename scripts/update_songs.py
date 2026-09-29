#!/usr/bin/env python3
"""Refresh factual song metadata from the Hatsune Miku Wiki tag pages.

No page text, lyrics, artwork, or audio is stored. Run deliberately and slowly;
the published app never contacts the Wiki.
"""

import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SOURCE = "https://w.atwiki.jp/hmiku/tag/%E6%AE%BF%E5%A0%82%E5%85%A5%E3%82%8A"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "songs.json"
PAGE_RE = re.compile(r"^/hmiku/pages/(\d+)\.html$")
VIDEO_RE = re.compile(r"(?:https?:)?//(?:ext\.)?nicovideo\.jp/(?:thumb/|watch/)([a-z]{2}\d+)", re.I)
YOUTUBE_RE = re.compile(r"(?:https?:)?//(?:www\.)?youtube(?:-nocookie)?\.com/embed/([\w-]{11})", re.I)


class WikiHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.parts = []
        self.embeds = []
        self._anchor = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        if self._skip:
            return
        if tag == "a":
            self._anchor = [attrs.get("href", ""), []]
        if tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3"):
            self.parts.append("\n")
        if tag in ("iframe", "embed") and attrs.get("src"):
            self.embeds.append(attrs["src"])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        if tag == "a" and self._anchor:
            href, parts = self._anchor
            self.anchors.append((href, "".join(parts).strip()))
            self._anchor = None

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)
            if self._anchor:
                self._anchor[1].append(data)


def tag_songs(document):
    parsed = WikiHTML()
    parsed.feed(document)
    anchors = parsed.anchors
    # The tag index has a pagination bar before and after the 50 song links.
    pagers = [i for i, (href, _) in enumerate(anchors) if re.search(r"[?&]p=\d+", href)]
    if len(pagers) < 2:
        raise ValueError("Tag pagination was not found; inspect the Wiki markup before updating")
    start = pagers[0]
    # The first pagination bar contains many numbered links. Its end is the
    # first song page link that follows it.
    while start < len(anchors) and not PAGE_RE.match(urlparse(urljoin(SOURCE, anchors[start][0])).path):
        start += 1
    result = []
    seen = set()
    for href, title in anchors[start:]:
        if re.search(r"[?&]p=\d+", href):
            break
        url = urljoin(SOURCE, href)
        match = PAGE_RE.match(urlparse(url).path)
        if match and title and url not in seen:
            seen.add(url)
            result.append({"title": title, "composer": None, "wikiUrl": f"https://w.atwiki.jp/hmiku/pages/{match[1]}.html", "originalUrl": None})
    if not 1 <= len(result) <= 50:
        raise ValueError(f"Unexpected number of songs ({len(result)}); inspect the Wiki markup")
    return result, max(int(n) for n in re.findall(r"[?&]p=(\d+)", document))


def song_details(document):
    parsed = WikiHTML()
    parsed.feed(document)
    plain = html.unescape("".join(parsed.parts))
    composer_match = re.search(r"(?:^|\n)\s*作曲\s*[：:]\s*([^\n]+)", plain)
    composer = re.sub(r"\s+", " ", composer_match[1]).strip() if composer_match else None
    if composer and len(composer) > 100:
        composer = None
    original = None
    for embed in parsed.embeds:
        nico = VIDEO_RE.search(embed)
        youtube = YOUTUBE_RE.search(embed)
        if nico:
            original = f"https://www.nicovideo.jp/watch/{nico[1]}"
            break
        if youtube:
            original = f"https://www.youtube.com/watch?v={youtube[1]}"
            break
    return composer, original


def fetch(url):
    request = Request(url, headers={"User-Agent": "vocaloid-gacha-data-updater/1.0 (personal, low-rate metadata fetch)"})
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def update(page_limit, delay):
    current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    by_url = {song["wikiUrl"]: song for song in current["songs"] if song["wikiUrl"]}
    by_title = {song["title"]: song for song in current["songs"]}
    gathered = []
    page = 1
    while page <= page_limit:
        url = SOURCE if page == 1 else f"{SOURCE}?p={page}"
        batch, last_page = tag_songs(fetch(url))
        gathered.extend(batch)
        print(f"Tag page {page}/{min(page_limit, last_page)}: {len(batch)} songs", file=sys.stderr)
        if page >= last_page:
            break
        page += 1
        time.sleep(delay)

    unique = {}
    for song in gathered:
        unique[song["wikiUrl"]] = song
    if not unique:
        raise ValueError("No song data retrieved; existing JSON was left intact")
    for index, song in enumerate(unique.values(), 1):
        previous = by_url.get(song["wikiUrl"]) or by_title.get(song["title"], {})
        song["composer"] = previous.get("composer")
        song["originalUrl"] = previous.get("originalUrl")
        try:
            composer, original = song_details(fetch(song["wikiUrl"]))
            song["composer"] = composer or song["composer"]
            song["originalUrl"] = original or song["originalUrl"]
        except (HTTPError, URLError, TimeoutError) as error:
            print(f"Detail {index}/{len(unique)} unavailable: {song['wikiUrl']} ({error})", file=sys.stderr)
        time.sleep(delay)

    # Keep manually verified older entries outside the selected tag pages.
    merged = list(unique.values())
    known_urls = set(unique)
    known_titles = {song["title"] for song in merged}
    for song in current["songs"]:
        if song["wikiUrl"] not in known_urls and song["title"] not in known_titles:
            merged.append(song)
    payload = {"updatedAt": date.today().isoformat(), "source": SOURCE, "songs": merged}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(merged)} songs to {OUTPUT}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=2, help="Tag pages to collect (50 songs per page, default: 2)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default: 1)")
    args = parser.parse_args()
    if args.pages < 1 or args.delay < 0.5:
        parser.error("--pages must be positive and --delay must be at least 0.5 seconds")
    update(args.pages, args.delay)


if __name__ == "__main__":
    main()
