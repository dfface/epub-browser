"""Regression EPUB: duplicate basenames, encoded paths and footnote returns."""
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from lxml import html
from epub_browser.asset_publisher import AssetPublisher
from epub_browser.processor import EPUBProcessor
from epub_browser.server_pages import ServerPageRenderer


def write_link_epub(path, website=False, root_layout=False):
    paths = ['Text/one.xhtml', 'Notes/one.xhtml', 'Text/space name.xhtml', 'Text/resources/space name.xhtml']
    bodies = [
        '<h1 id="start">Start</h1><a href="#local">Local</a><p id="local">Local target</p>'
        '<a href="../Notes/one.xhtml#note">Note</a>'
        '<a href="space%20name.xhtml#%E6%B3%A8">Encoded</a>'
        '<a href="https://example.org/one.xhtml#external">External</a>'
        '<a href="resources/space%20name.xhtml#nested">Nested resource chapter</a>'
        '<a href="./resources/../resources/space%20name.xhtml#nested">Normalized path</a>',
        '<p id="note">Note</p><a href="../Text/one.xhtml#start">Return</a>',
        '<p id="注">Encoded target</p>',
        '<p id="nested">Nested target</p><a href="../one.xhtml#start">Return</a>',
    ]
    if root_layout:
        paths = ['065.html', '069.html', '070.html', 'resources/071.html']
        bodies = [
            '<h1>Contents</h1><a href="069.html#a168">Part I</a><a href="070.html#a169">1</a>',
            '<h1 id="a168">Part I</h1><a href="065.html#body-target">Contents</a>',
            '<h1 id="a169">Chapter 1</h1>',
            '<p>Additional chapter</p>',
        ]
    if website:
        bodies[0] += '<a href="/guide/notes/#note">Website note</a><a href="/unrelated/">Unrelated</a>'
        bodies[0] += '<a href="https://docs.example/guide/notes/">Original external</a>'
        sources = ['/guide/start/', '/guide/notes/', '/guide/encoded/', '/guide/nested/']
        bodies = ['<blockquote>原文：<a href="https://docs.example' + source + '">https://docs.example' + source + '</a></blockquote>' + body for source, body in zip(sources, bodies)]
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        manifest = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>' + ''.join(f'<item id="c{i}" href="{p}" media-type="application/xhtml+xml"/>' for i,p in enumerate(paths))
        spine = ''.join(f'<itemref idref="c{i}"/>' for i in range(4))
        z.writestr('OEBPS/content.opf', f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Link regression</dc:title><dc:identifier id="uid">urn:issue80:links</dc:identifier><dc:language>en</dc:language></metadata><manifest>{manifest}</manifest><spine>{spine}</spine></package>')
        nav_start = '065.html#body-target' if root_layout else 'Text/one.xhtml#start'
        nav_other = '070.html#a169' if root_layout else 'Text/space%20name.xhtml#%E6%B3%A8'
        z.writestr('OEBPS/nav.xhtml', f'<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="{nav_start}">Start</a></li><li><a href="{nav_other}">Other</a></li></ol></nav></body></html>')
        for p, body in zip(paths, bodies):
            z.writestr('OEBPS/'+p, '<html><head><title>Links</title></head><body id="body-target">'+body+'</body></html>')


class EPUBLinkTests(unittest.TestCase):
    def test_spine_links_and_ids_survive_ssg_and_server_conversion(self):
        for mode in ('ssg', 'server'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp, 'links.epub')
                write_link_epub(source)
                p = EPUBProcessor(source, tmp, deployment_mode=mode)
                result = p.convert()
                renderer = None
                if mode == 'server':
                    public = Path(tmp, 'public')
                    target = public / 'book' / result.book_id
                    target.parent.mkdir(parents=True)
                    shutil.copytree(result.output_dir, target)
                    AssetPublisher(Path('epub_browser/assets'), public).publish()
                    renderer = ServerPageRenderer(public, result.book_id)
                    self.assertIn('chapter_0.html', renderer.render_index())
                    self.assertFalse((target / 'chapter_0.html').exists())
                toc = json.loads((result.output_dir / ('toc.json' if mode == 'ssg' else 'content/toc.json')).read_text())
                self.assertTrue(any(item.get('anchor') == '%E6%B3%A8' and item.get('chapter_index') == 2 for item in toc))
                pages = []
                for i in range(4):
                    file = result.output_dir / (f'chapter_{i}.html' if mode == 'ssg' else f'content/chapter_{i}.json')
                    text = file.read_text()
                    if mode == 'server':
                        text = renderer.render_chapter(i)
                    pages.append(html.fromstring(text))
                links = pages[0].xpath('//a/@href')
                self.assertIn('#local', links)
                self.assertTrue(pages[0].xpath('//*[@id="body-target"]'))
                self.assertIn('chapter_1.html#note', links)
                self.assertIn('chapter_2.html#%E6%B3%A8', links)
                nested_links = pages[0].xpath('//a[text()="Nested resource chapter" or text()="Normalized path"]/@href')
                self.assertEqual(nested_links, ['chapter_3.html#nested', 'chapter_3.html#nested'])
                self.assertIn('chapter_0.html#start', pages[3].xpath('//a/@href'))
                self.assertIn('https://example.org/one.xhtml#external', links)
                self.assertIn('chapter_0.html#start', pages[1].xpath('//a/@href'))
                for page, target in zip(pages, ['local', 'note', '注', 'nested']):
                    self.assertTrue(page.xpath('//*[@id=$target]', target=target))

    def test_source_attribution_does_not_rewrite_website_urls(self):
        for mode in ('ssg', 'server'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp, 'website.epub')
                write_link_epub(source, website=True)
                result = EPUBProcessor(source, tmp, deployment_mode=mode).convert()
                if mode == 'server':
                    markup = json.loads((result.output_dir / 'content/chapter_0.json').read_text())['content']
                else:
                    markup = (result.output_dir / 'chapter_0.html').read_text()
                links = html.fromstring(markup).xpath('//a/@href')
                self.assertEqual(html.fromstring(markup).xpath('//a[text()="Website note"]/@href'), ['/guide/notes/#note'])
                self.assertIn('/unrelated/', links)
                self.assertIn('https://docs.example/guide/notes/', links)

    def test_contents_links_to_numeric_sibling_files_and_back(self):
        for mode in ('ssg', 'server'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp, 'numeric.epub')
                write_link_epub(source, root_layout=True)
                result = EPUBProcessor(source, tmp, deployment_mode=mode).convert()

                def page(index):
                    if mode == 'server':
                        markup = json.loads((result.output_dir / f'content/chapter_{index}.json').read_text())['content']
                    else:
                        markup = (result.output_dir / f'chapter_{index}.html').read_text()
                    return html.fromstring(markup)

                contents = page(0)
                self.assertEqual(contents.xpath('//a[text()="Part I"]/@href'), ['chapter_1.html#a168'])
                self.assertEqual(contents.xpath('//a[text()="1"]/@href'), ['chapter_2.html#a169'])
                self.assertTrue(page(1).xpath('//*[@id="a168"]'))
                self.assertTrue(page(2).xpath('//*[@id="a169"]'))
                self.assertEqual(page(1).xpath('//a[text()="Contents"]/@href'), ['chapter_0.html#body-target'])
