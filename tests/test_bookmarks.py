"""Bookmarks through the session API: ownership, visibility, migration and validation."""
import tempfile
import unittest
from pathlib import Path
from starlette.testclient import TestClient
from epub_browser.auth import AuthConfig, AuthService, BootstrapCredentials, hash_password
from epub_browser.server import create_app
from epub_browser.state import StateStore


class BookmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = StateStore(root / 'state.db')
        self.owner = self.store.initialize(BootstrapCredentials('owner', 'secret'))
        self.member = self.store.create_user('reader', hash_password('secret'))
        self.store.resolve_book(root / 'a.epub', None, 'fingerprint', {}, preferred_book_id='book')
        self.store.set_book_visibility('book', 'restricted')
        self.auth = AuthService(self.store, AuthConfig.from_values([]))
        self.app = create_app(root, state_store=self.store, auth_service=self.auth)
        self.client = self.client_for(self.owner)
        self.payload = {'name': '', 'position': {'format': 'epub', 'chapter': 'OPS/ch1.xhtml',
            'chapter_index': 0, 'element': 'p:0', 'text': 'A stable paragraph', 'offset': 0}}

    def client_for(self, principal):
        client = TestClient(self.app)
        token, _ = self.auth.create_session(principal)
        # Use the configured cookie name rather than depending on UI login.
        from epub_browser.auth import SESSION_COOKIE
        client.cookies.set(SESSION_COOKIE, token)
        session = client.get('/api/session')
        client.headers['X-CSRF-Token'] = session.json()['csrf_token']
        self.addCleanup(client.close)
        return client

    def test_save_rename_delete_and_reopen_database(self):
        saved = self.client.post('/api/bookmarks/book', json=self.payload)
        self.assertEqual(saved.status_code, 201, saved.text)
        row = saved.json()['data']
        self.store.initialize()
        rows = self.client.get('/api/bookmarks/book').json()['data']
        self.assertEqual(rows, [row])
        duplicate = self.client.post('/api/bookmarks/book', json=self.payload)
        self.assertEqual(duplicate.json()['data']['id'], row['id'])
        url = '/api/bookmarks/book/' + row['id']
        renamed = self.client.patch(url, json={'name': 'Return here'})
        self.assertEqual(renamed.json()['data']['name'], 'Return here')
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.get('/api/bookmarks/book').json()['data'], [])

    def test_auth_visibility_and_user_isolation(self):
        anonymous = TestClient(self.app)
        self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.get('/api/bookmarks/book').status_code, 401)
        saved = self.client.post('/api/bookmarks/book', json=self.payload)
        self.assertEqual(saved.status_code, 201, saved.text)
        other = self.client_for(self.member)
        self.assertEqual(other.get('/api/bookmarks/book').status_code, 403)
        self.store.grant_book_access('book', self.member.user_id)
        self.assertEqual(other.get('/api/bookmarks/book').json()['data'], [])
        url = '/api/bookmarks/book/' + saved.json()['data']['id']
        self.assertEqual(other.patch(url, json={'name': 'stolen'}).status_code, 404)
        self.assertEqual(other.delete(url).status_code, 404)
        self.assertEqual(len(self.client.get('/api/bookmarks/book').json()['data']), 1)
        other.headers.pop('X-CSRF-Token')
        self.assertEqual(other.post('/api/bookmarks/book', json=self.payload).status_code, 403)

    def test_invalid_locations_and_names_are_rejected(self):
        for position in ({}, {'format': 'pdf', 'page': 0, 'y': .5},
                         {'format': 'pdf', 'page': 2, 'y': 2},
                         dict(self.payload['position'], chapter_index=-1)):
            result = self.client.post('/api/bookmarks/book', json={'name': '', 'position': position})
            self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual(self.client.post('/api/bookmarks/book', json=dict(self.payload, name='x' * 121)).status_code, 400)
        pdf = self.client.post('/api/bookmarks/book', json={'position': {'format': 'pdf', 'page': 2, 'y': .42}})
        self.assertEqual(pdf.status_code, 201, pdf.text)

    def test_upgrade_and_user_deletion_preserve_storage_boundaries(self):
        import sqlite3
        with sqlite3.connect(self.store.database_path) as db:
            db.execute('DROP TABLE bookmarks')
            db.execute('PRAGMA user_version = 34')
        self.store.initialize()
        self.store.grant_book_access('book', self.member.user_id)
        other = self.client_for(self.member)
        created = other.post('/api/bookmarks/book', json=self.payload)
        self.assertEqual(created.status_code, 201, created.text)
        impact = self.store.user_deletion_impact(self.member.user_id)
        self.assertTrue(impact['requires_typed_confirmation'])
        self.store.delete_user(self.member.user_id,replacement_user_id=self.owner.user_id,confirmation='reader')
        self.assertEqual(self.store.list_bookmarks('book', self.member.user_id), [])
        self.assertEqual(self.client.get('/api/bookmarks/book').json()['data'], [])

    def test_ssg_does_not_publish_the_server_bookmark_adapter(self):
        from epub_browser.asset_publisher import AssetPublisher, SERVER_ONLY_ASSET_PATHS
        with tempfile.TemporaryDirectory() as folder:
            assets = AssetPublisher(Path('epub_browser/assets'),folder,
                excluded_paths=SERVER_ONLY_ASSET_PATHS).publish()
            self.assertNotIn('bookmarks-server.js',assets.assets)
            shared = Path(folder,assets.url_for('bookmarks.js').lstrip('/')).read_text()
            self.assertNotIn('/api/bookmarks',shared)



class BookmarkBrowserTests(unittest.TestCase):
    def test_restore_and_toggle_across_reader_modes(self):
        """Exercise real DOM geometry after relayout, including a scanned PDF page."""
        import functools
        import re
        import json
        import shutil
        import subprocess
        import threading
        import time
        from urllib.request import urlopen
        try:
            from websockets.sync.client import connect
        except ImportError:
            self.skipTest('websockets sync client needed for Chromium checks')
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from epub_browser.asset_publisher import AssetPublisher
        from epub_browser.models import BookMetadata
        from epub_browser.reader_pages import ReaderPageRenderer
        from epub_browser.pdf_processor import PDFMetadata, PDFPageMetadata
        from pypdf import PdfWriter
        chrome = shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        if not Path(chrome).exists():
            self.skipTest('Chromium needed for reader geometry')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = AssetPublisher(Path('epub_browser/assets'), root).publish()
            folder = root / 'book' / 'fixture'
            folder.mkdir(parents=True)
            writer = PdfWriter()
            writer.add_blank_page(width=600, height=1800)
            writer.write(folder / 'document.pdf')
            chapters = [{'path':'OPS/one.xhtml','title':'One'},{'path':'OPS/two.xhtml','title':'Two'}]
            epub = ReaderPageRenderer(book_id='fixture', metadata=BookMetadata(title='Test', authors=(), tags=(), cover=None, language='en', epub_identifier=None),
                chapters=chapters, toc=[], description='', asset_manifest=assets, deployment_mode='ssg')
            pdf = ReaderPageRenderer.from_pdf_metadata(book_id='fixture', metadata=PDFMetadata(title='Test',authors=(),tags=(),language='en',
                pages=(PDFPageMetadata(1,600,1800),),encrypted=False,has_extractable_text=False,cover=None),
                cover_path=None,asset_manifest=assets,urls=epub.urls,deployment_mode='ssg')
            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self,*args): pass
            http = ThreadingHTTPServer(('127.0.0.1',0), functools.partial(QuietHandler,directory=root))
            thread = threading.Thread(target=http.serve_forever,daemon=True)
            thread.start()
            try:
                for fmt in ('epub','pdf'):
                    for mode in (('scroll','pages','continuous','cross-chapter','relocated','unresolved','no-lightbox','outline-jump','outline-jump-pages') if fmt=='epub' else ('scroll','pages','continuous')):
                        with self.subTest(format=fmt,mode=mode):
                            paragraphs = ''.join('<p id="p%d">%s</p>' % (i, ('Paragraph %d content. ' % i)*30) for i in range(25))
                            if mode.startswith('outline-jump'): paragraphs=paragraphs.replace('<p id="p15">','<div style="position:relative"><h2 id="section-target">Section target</h2><p id="p15">')+'</div>'
                            markup = epub.create_chapter_template(paragraphs,'',0,'One') if fmt=='epub' else pdf.create_pdf_chapter_template(0,'document.pdf')
                            position = {'format':'epub','chapter':'OPS/one.xhtml','chapter_index':0,'element':'00000015:#p15','text':('Paragraph 15 content. '*30).strip(),'offset':10} if fmt=='epub' else {'format':'pdf','page':1,'y':.6}
                            if mode=='relocated': position['element']='00000014:#p15'
                            if mode=='unresolved': position['text']='This paragraph was removed.'
                            setup = """<script>
                                window.__errors=[];window.addEventListener('error',e=>window.__errors.push(e.message+' '+e.filename+':'+e.lineno));
                                localStorage.clear();localStorage.setItem('turning',(MODE==='pages'||MODE==='outline-jump-pages')?'true':'false');
                                localStorage.setItem('continuousScroll',(MODE==='continuous'||MODE==='cross-chapter')?'true':'false');
                                localStorage.setItem('font_size','24');
                                localStorage.setItem('epub-bookmarks-v1:fixture',JSON.stringify([{id:'saved',name:'Here',position:POSITION}]));
                            </script>""".replace('MODE',json.dumps(mode)).replace('POSITION',json.dumps(position))
                            check = """<script>
                                window.addEventListener('epub-browser:bookmark-reader-ready', function(){setTimeout(async function(){
                                  try {
                                    if(window.__errors.length)throw Error(window.__errors.join(';'));
                                    if(MODE==='unresolved') {
                                        if(!document.querySelector('#bookmarkStatus a') || !document.getElementById('bookmarkStatus').textContent.includes('could not be found'))throw Error('missing explicit chapter fallback');
                                        window.__bookmarkResult='BOOKMARK_PASS';return;
                                    }
                                    var target=document.querySelector(FORMAT==='pdf'?'[data-pdf-page-number]':'#p15');
                                    var rect=target.getBoundingClientRect();
                                    if(FORMAT==='epub' && !(rect.bottom>0 && rect.top<innerHeight && rect.right>0 && rect.left<innerWidth))throw Error('target outside viewport '+JSON.stringify(rect.toJSON())+' scroll='+document.getElementById('eb-content').scrollLeft);
                                    if(FORMAT==='pdf' && rect.top+rect.height*.6>innerHeight)throw Error('PDF relative point outside viewport '+JSON.stringify(rect.toJSON())+' state='+target.getAttribute('data-pdf-rendered'));
                                    var b=document.querySelector('[data-bookmark-toggle]');
                                    if(b.disabled)throw Error('bookmark button disabled');
                                    document.getElementById('bookHomeToggle').click();
                                    document.getElementById('bookmarkTab').click();
                                    await new Promise(r=>setTimeout(r,100));
                                    var outlineTab=document.getElementById('chapterOutlineTab');
                                    if(outlineTab.hidden!==(FORMAT==='pdf'||MODE==='continuous'||MODE==='cross-chapter'))throw Error('wrong outline availability');
                                    if(!outlineTab.hidden){
                                        outlineTab.click();
                                        if(document.getElementById('tocFloating').hidden || !document.getElementById('bookHomeFloating').contains(document.getElementById('tocFloating')))throw Error('outline not in shared navigation');
                                        if(MODE.startsWith('outline-jump')) {
                                            document.querySelector('#tocList a').click();
                                            await new Promise(r=>setTimeout(r,250));
                                            var headingTop=document.getElementById('section-target').getBoundingClientRect().top;
                                            if(MODE==='outline-jump' && (headingTop<0 || headingTop>100))throw Error('outline heading not aligned at top: '+headingTop);
                                            var headingRect=document.getElementById('section-target').getBoundingClientRect();
                                            if(MODE==='outline-jump-pages' && (headingRect.right<=0 || headingRect.left>=innerWidth))throw Error('outline heading outside pagination viewport');
                                            document.getElementById('bookHomeToggle').click();
                                        } else if(!document.querySelector('[data-i18n="bookmarks.outlineEmpty"]') || !document.getElementById('bookHomeLocateCurrent').hidden)throw Error('outline empty state or locator wrong');
                                        document.getElementById('bookmarkTab').click();await new Promise(r=>setTimeout(r,100));
                                    }
                                    var rename=document.querySelector('[data-bookmark-action="rename"]');rename.click();
                                    var input=document.querySelector('#appDialogInput');if(!input.labels.length||!input.value)throw Error('rename lacks context');input.value='Renamed';
                                    document.querySelector('.app-dialog-confirm').click();await new Promise(r=>setTimeout(r,100));
                                    if(JSON.parse(localStorage.getItem('epub-bookmarks-v1:fixture'))[0].name!=='Renamed')throw Error('rename failed');
                                    document.querySelector('[data-bookmark-action="delete"]').click();await new Promise(r=>setTimeout(r,100));
                                    if(JSON.parse(localStorage.getItem('epub-bookmarks-v1:fixture')).length)throw Error('delete failed');
                                    document.querySelector('[data-epub-browser-notification] .notification-action').click();await new Promise(r=>setTimeout(r,100));
                                    if(JSON.parse(localStorage.getItem('epub-bookmarks-v1:fixture')).length!==1)throw Error('undo failed');
                                    document.querySelector('[data-bookmark-action="delete"]').click();await new Promise(r=>setTimeout(r,100));
                                    window.EpubReaderDrawers.close(false);
                                    if(MODE==='cross-chapter') {
                                        document.querySelector('.continuous-chapter[data-chapter-index="1"] p').scrollIntoView();
                                        await new Promise(r=>setTimeout(r,150));
                                    }
                                    b.click();await new Promise(r=>setTimeout(r,100));
                                    if(MODE==='cross-chapter' && JSON.parse(localStorage.getItem('epub-bookmarks-v1:fixture'))[0].position.chapter!=='OPS/two.xhtml')throw Error('wrong chapter at continuous reference line');
                                    if(JSON.parse(localStorage.getItem('epub-bookmarks-v1:fixture')).length!==1)throw Error('first toggle did not save current position');
                                    b.click();await new Promise(r=>setTimeout(r,100));
                                    if(JSON.parse(localStorage.getItem('epub-bookmarks-v1:fixture')).length)throw Error('toggle did not remove current bookmark');
                                    b.click();await new Promise(r=>setTimeout(r,100));
                                    var added=JSON.parse(localStorage.getItem('epub-bookmarks-v1:fixture'));
                                    if(added.length!==1 || (FORMAT==='epub' && !added[0].position.quote))throw Error('capture/add failed');
                                    await window.EpubBrowserI18n.loadLocale('zh-CN');
                                    window.EpubBrowserI18n.setLocale('zh-CN');
                                    await new Promise(r=>setTimeout(r,300));
                                    if(document.querySelector('[data-bookmark-action="rename"]').textContent!=='重命名')throw Error('open list did not translate');
                                    var emptyOutline=document.querySelector('[data-i18n="bookmarks.outlineEmpty"]');
                                    if(emptyOutline && emptyOutline.textContent!=='本章没有小节目录')throw Error('outline empty state did not translate');
                                    var preference=document.getElementById('notificationPosition');
                                    for(var placement of ['top','bottom','top-left','top-right','bottom-left','bottom-right','auto']) {
                                        preference.value=placement;preference.dispatchEvent(new Event('change'));
                                        var toast=window.EpubBrowserNotification.show('Position test','info');
                                        if(window.EpubBrowserNotification.getPosition()!==placement)throw Error('notification preference not saved');
                                        var bounds=toast.getBoundingClientRect();
                                        if(placement==='top'&&bounds.top>100)throw Error('top placement wrong');
                                        if(placement==='bottom'&&bounds.bottom>innerHeight)throw Error('bottom placement outside viewport');
                                    }
                                    document.getElementById('notificationPreview').click();
                                    if(!document.querySelector('[data-epub-browser-notification] [data-i18n="bookmarks.notificationPreviewMessage"]'))throw Error('notification preview failed');
                                    if(document.activeElement.matches('[data-has-bookmark]') && document.activeElement.id!=='eb-content')throw Error('paragraph received focus');
                                    window.__bookmarkResult='BOOKMARK_PASS';
                                  }catch(e){window.__bookmarkResult='BOOKMARK_FAIL: '+e.message;}
                                },MODE==='unresolved'?6500:2000);});
                            </script>""".replace('FORMAT',json.dumps(fmt)).replace('MODE',json.dumps(mode))
                            markup=re.sub(r'<script src="([^"]+)"[^>]*></script>',
                                lambda m: '<script>'+ (root/m.group(1).lstrip('/')).read_text().replace('</script', '<\\/script')+'</script>', markup)
                            if mode=='no-lightbox': check='<script>delete window.Fancybox;</script>'+check
                            markup=markup.replace('<head>','<head>'+setup).replace('</body>',check+'</body>')
                            (folder/'chapter_0.html').write_text(markup)
                            if fmt=='epub': (folder/'chapter_1.html').write_text(epub.create_chapter_template('<p>'+('Second chapter content. '*200)+'</p>','',1,'Two'))
                            profile=root/('profile-'+fmt+'-'+mode)
                            process=subprocess.Popen([chrome,'--headless','--no-sandbox','--disable-gpu',
                                '--no-proxy-server','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                            try:
                                port_file=profile/'DevToolsActivePort'
                                for _ in range(100):
                                    if port_file.exists(): break
                                    time.sleep(.05)
                                port=port_file.read_text().splitlines()[0]
                                with urlopen('http://127.0.0.1:'+port+'/json/list') as response:
                                    target=json.load(response)[0]
                                with connect(target['webSocketDebuggerUrl'],max_size=5_000_000) as socket:
                                    seq=0
                                    def command(method,params):
                                        nonlocal seq
                                        seq+=1
                                        socket.send(json.dumps({'id':seq,'method':method,'params':params}))
                                        while True:
                                            result=json.loads(socket.recv(timeout=20))
                                            if result.get('id')==seq:return result
                                    command('Page.enable',{})
                                    command('Page.navigate',{'url':'http://127.0.0.1:%d/book/fixture/chapter_0.html#bookmark=saved'%http.server_port})
                                    while True:
                                        event=json.loads(socket.recv(timeout=20))
                                        if event.get('method')=='Page.loadEventFired':break
                                    outcome=command('Runtime.evaluate',{'expression':
                                        "new Promise(resolve=>{let n=0;let id=setInterval(()=>{if(window.__bookmarkResult||++n>150){clearInterval(id);resolve(window.__bookmarkResult||'TIMEOUT '+JSON.stringify(window.__errors));}},100);})",
                                        'awaitPromise':True,'returnByValue':True})
                                    self.assertEqual(outcome['result']['result'].get('value'),'BOOKMARK_PASS',str(outcome))
                            finally:
                                process.terminate()
                                process.wait(timeout=10)

            finally:
                http.shutdown();http.server_close();thread.join()
