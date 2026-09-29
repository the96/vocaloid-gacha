import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from scripts.update_songs import Blocked, collect, song_details, tag_songs, SOURCE


def tag(ids, pages=148):
    return '<a href="/hmiku/pages/999.html">menu</a><a href="?p=2">2</a>' + ''.join(f'<a href="/hmiku/pages/{i}.html">Song {i}</a>' for i in ids) + f'<a href="?p={pages}">{pages}</a><a href="/hmiku/pages/999.html">footer</a>'


def detail(name='山本'):
    return f'<div id="wikibody"><p>作曲：<a href="/author">{name}</a></p></div>'


class UpdateParserTest(unittest.TestCase):
    def test_tag_page_only_extracts_songs_between_pagers(self):
        songs, pages = tag_songs(tag([12, 20]))
        self.assertEqual([s['wikiUrl'].split('/')[-1] for s in songs], ['12.html', '20.html'])
        self.assertEqual(pages, 148)

    def test_decoded_tag_pagination(self):
        songs, _ = tag_songs(tag([12]).replace('?p=', '/hmiku/tag/殿堂入り?p='))
        self.assertEqual(len(songs), 1)

    def test_duplicate_and_missing_pagers_fail_closed(self):
        for html in [tag([12, 12]), '<a href="/hmiku/pages/12.html">song</a>']:
            with self.assertRaises(ValueError):
                tag_songs(html)

    def test_composer_scoped_to_article_and_before_lyrics(self):
        html = '<p>作曲：wrong</p><div id="wikibody"><script>作曲：wrong</script><p>作曲：<a>A</a>・<a>B</a><br>編曲：C</p><h3>歌詞</h3><p>作曲：wrong</p></div>'
        self.assertEqual(song_details(html)['composer'], 'A・B')

    def test_conflicting_composers_are_not_guessed(self):
        html = '<div id="wikibody"><p>作曲：A</p><p>作曲：B</p></div>'
        self.assertIsNone(song_details(html)['composer'])
        self.assertIn('composer_conflict', song_details(html)['issues'])

    def test_combined_credits(self):
        self.assertEqual(song_details(detail().replace('作曲：', '作詞・作曲：'))['composer'], '山本')

    def test_no_article_container_rejected(self):
        with self.assertRaises(ValueError):
            song_details('<p>作曲：wrong</p>')

    def test_first_embed_cover_not_original(self):
        html = '<div id="wikibody"><p>カバー <iframe src="//ext.nicovideo.jp/thumb/sm123456"></iframe></p><p>原曲 <iframe src="https://www.youtube.com/embed/abcdefghijk"></iframe></p></div>'
        result = song_details(html)
        self.assertIsNone(result['originalUrl'])
        self.assertEqual(result['videoCandidates'], [
            {'url': 'https://www.nicovideo.jp/watch/sm123456', 'reason': 'cover_context'},
            {'url': 'https://www.youtube.com/watch?v=abcdefghijk', 'reason': 'original_label_requires_review'},
        ])

    def test_real_article_front_matter_normal_song(self):
        # Minimal metadata-only excerpt of page 12, checked 2026-09-30.
        html = '''<div id="wikibody"><h2>恋スルVOC@LOID</h2>
        <table class="atwiki_plugin_region"><tr><td>目次 曲紹介 歌詞 関連動画</td></tr></table>
        <table><tr><td><a href="http://www.nicovideo.jp/watch/sm1050729"></a></td></tr></table>
        <div>作詞：OSTER project<br>作曲：OSTER project<br>編曲：OSTER project</div>
        <h3>曲紹介</h3></div>'''
        result = song_details(html)
        self.assertEqual(result['composer'], 'OSTER project')
        self.assertEqual(result['originalUrl'], 'https://www.nicovideo.jp/watch/sm1050729')

    def test_real_article_front_matter_collaboration(self):
        # Minimal metadata-only excerpt of page 14707, checked 2026-09-30.
        html = '''<div id="wikibody"><h2>Mr.Music</h2>
        <table><a href="http://www.nicovideo.jp/watch/sm13774194"></a></table>
        <div>作詞：れるりり・ロンチーノ=ペペ・かごめP<br>
        作曲：れるりり・ロンチーノ=ペペ<br>編曲：れるりり</div><h3>曲紹介</h3></div>'''
        result = song_details(html)
        self.assertEqual(result['composer'], 'れるりり・ロンチーノ=ペペ')
        self.assertEqual(result['originalUrl'], 'https://www.nicovideo.jp/watch/sm13774194')

    def test_combined_composer_label_and_canonical_link_title(self):
        html = '''<div id="wikibody"><table><a href="https://www.nicovideo.jp/watch/sm123"></a></table>
        <div>作詞・作曲・編曲・動画：<a title="ぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬ (29d)">ぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬ</a><br>
        MIX・マスタリング：別の人</div><h3>曲紹介</h3></div>'''
        result = song_details(html)
        self.assertEqual(result['composer'], 'ぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬぬ')
        self.assertEqual(result['originalUrl'], 'https://www.nicovideo.jp/watch/sm123')

    def test_real_article_primary_video_precedes_later_cover(self):
        # Metadata-only structure based on page 1827, checked 2026-09-30.
        html = '''<div id="wikibody"><h2>メルト Rin Len Rap Remix</h2>
        <table><a href="http://www.nicovideo.jp/watch/sm2398386"></a></table>
        <div>作詞：ryo、ill.bell<br>作曲：ryo<br>編曲：斜め上P</div>
        <h3>曲紹介</h3><p>カバー <a href="http://www.nicovideo.jp/watch/sm2010762"></a></p></div>'''
        result = song_details(html)
        self.assertEqual(result['composer'], 'ryo')
        self.assertEqual(result['originalUrl'], 'https://www.nicovideo.jp/watch/sm2398386')
        self.assertIn({'url': 'https://www.nicovideo.jp/watch/sm2010762', 'reason': 'cover_context'}, result['videoCandidates'])


class ResumeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.args = dict(pages=2, cache=self.root/'cache.json', report=self.root/'report.json', output=self.root/'songs.json')
        self.args['output'].write_text('previous dataset')

    def run_collect(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return collect(**self.args, **kwargs)

    def test_resume_omits_successful_pages_and_never_overwrites_on_gap(self):
        calls = []
        def first(url):
            calls.append(url)
            if '?p=2' in url:
                raise Blocked('challenge')
            return tag(range(1, 51))
        result = self.run_collect(fetcher=first)
        self.assertEqual(result['missingPages'], [2])
        self.assertEqual(self.args['output'].read_text(), 'previous dataset')
        calls.clear()
        def second(url):
            calls.append(url)
            return tag([51]) if '?p=2' in url else detail()
        result = self.run_collect(fetcher=second)
        self.assertNotIn(SOURCE, calls)
        self.assertEqual(result['uniqueSongs'], 51)
        self.assertTrue(result['published'])
        calls.clear()
        self.run_collect(fetcher=second)
        self.assertEqual(calls, [])

    def test_short_nonfinal_page_blocks_publication(self):
        result = self.run_collect(fetcher=lambda u: tag([1]) if u == SOURCE else tag([2]) if '?p=2' in u else detail())
        self.assertFalse(result['published'])
        self.assertEqual(result['unexpectedPageSizes'], [1])

    def test_repeated_page_not_marked_as_fetched(self):
        result = self.run_collect(fetcher=lambda _: tag([1]))
        self.assertFalse(result['published'])
        self.assertEqual(result['missingPages'], [2])

    def test_cross_page_duplicates_block_publication(self):
        result = self.run_collect(fetcher=lambda url: tag([1, 2]) if url == SOURCE else tag([2, 3]) if '?p=2' in url else detail())
        self.assertFalse(result['published'])
        self.assertEqual(result['duplicateWikiUrls']['https://w.atwiki.jp/hmiku/pages/2.html'], [1, 2])

    def test_failed_details_resume_and_do_not_reuse_old_names(self):
        def first(url):
            if url == SOURCE: return tag(range(1, 51))
            if '?p=2' in url: return tag([51])
            if url.endswith('/51.html'): raise TimeoutError('timeout')
            return detail('A')
        result = self.run_collect(fetcher=first)
        songs = json.loads(self.args['output'].read_text())['songs']
        self.assertEqual(result['detailsFetched'], 50)
        self.assertIsNone(songs[50]['composer'])
        calls = []
        def second(url):
            calls.append(url)
            return detail('B')
        self.run_collect(fetcher=second)
        self.assertEqual(calls, ['https://w.atwiki.jp/hmiku/pages/51.html'])

    def test_cover_candidate_is_kept_for_review_even_with_primary_video(self):
        primary = '<table><a href="https://www.nicovideo.jp/watch/sm100"></a></table><div>作曲：A</div>'
        cover = '<h3>関連動画</h3><p>カバー <a href="https://www.nicovideo.jp/watch/sm200"></a></p>'
        result = self.run_collect(fetcher=lambda u: tag(range(1, 51)) if u == SOURCE else tag([51]) if '?p=2' in u else f'<div id="wikibody">{primary}{cover}</div>')
        report = json.loads(self.args['report'].read_text())
        self.assertEqual(result['originalUnconfirmed'], 0)
        self.assertEqual(len(report['reviewRequired']), 51)
        self.assertEqual(len(report['duplicateOriginalUrls']), 1)
        self.assertTrue(all(any(c['reason'] == 'cover_context' for c in item['videoCandidates']) for item in report['reviewRequired'].values()))

    def test_reviewed_original_requires_evidence(self):
        review = self.root/'review.json'
        review.write_text(json.dumps({'https://w.atwiki.jp/hmiku/pages/1.html': {'originalUrl': 'https://www.nicovideo.jp/watch/sm123', 'reason': 'Wiki explicitly labels original', 'checkedAt': '2026-09-29'}}))
        result = self.run_collect(fetcher=lambda u: tag(range(1, 51)) if u == SOURCE else tag([51]) if '?p=2' in u else detail(), overrides=review)
        self.assertEqual(result['originalUnconfirmed'], 50)
        songs = json.loads(self.args['output'].read_text())['songs']
        self.assertEqual(songs[0]['originalUrl'], 'https://www.nicovideo.jp/watch/sm123')


if __name__ == '__main__':
    unittest.main()
