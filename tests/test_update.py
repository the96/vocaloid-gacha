import unittest
from scripts.update_songs import song_details, tag_songs


class UpdateParserTest(unittest.TestCase):
    def test_tag_page_only_extracts_songs_between_pagers(self):
        html = '''<a href="/hmiku/pages/1.html">menu</a>
        <a href="?p=2">2</a><a href="?p=3">3</a>
        <a href="/hmiku/pages/12.html">恋スルVOC@LOID</a>
        <a href="/hmiku/pages/20.html">みくみくにしてあげる♪</a>
        <a href="?p=2">2</a><a href="/hmiku/pages/99.html">footer</a>'''
        songs, pages = tag_songs(html)
        self.assertEqual([song['title'] for song in songs], ['恋スルVOC@LOID', 'みくみくにしてあげる♪'])
        self.assertEqual(pages, 3)

    def test_composer_and_original_video(self):
        html = '''<script>作曲：wrong</script><p>作曲：<a href="/author">山本</a></p>
        <iframe src="//ext.nicovideo.jp/thumb/sm123456"></iframe>'''
        self.assertEqual(song_details(html), ('山本', 'https://www.nicovideo.jp/watch/sm123456'))


if __name__ == '__main__':
    unittest.main()
