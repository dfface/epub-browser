(function(root, factory) {
    var api = factory(root);
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.EpubBookmarks = api;
    if (root.document) {
        document.addEventListener('DOMContentLoaded', function() { setTimeout(api.init, 0); });
        root.addEventListener('epub-browser:bookmark-reader-ready', api.init);
    }
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
    'use strict';
    function samePosition(a, b) {
        return !!a && !!b && a.format === b.format && (a.format === 'pdf'
            ? a.page === b.page : a.chapter === b.chapter && a.element === b.element);
    }
    function chapterIndex(p, chapters) {
        if (p.format === 'pdf') return p.page > 0 && p.page <= chapters.length ? p.page - 1 : -1;
        return chapters.findIndex(function(c) { return c.path === p.chapter; });
    }
    function sort(rows, chapters) {
        return rows.slice().sort(function(a,b) {
            var x = chapterIndex(a.position, chapters), y = chapterIndex(b.position, chapters);
            if (x !== y) return (x < 0 ? Infinity : x) - (y < 0 ? Infinity : y);
            return (a.position.element || '').localeCompare(b.position.element || '', undefined, {numeric:true}) ||
                (a.position.offset || a.position.y || 0) - (b.position.offset || b.position.y || 0);
        });
    }
    function localStore(storage, book) {
        var key = 'epub-bookmarks-v1:' + book;
        function read() {
            var rows = JSON.parse(storage.getItem(key) || '[]');
            if (!Array.isArray(rows) || rows.some(function(r) { return !r.id || !r.position; })) throw Error('Invalid bookmarks');
            return rows;
        }
        function write(rows) { storage.setItem(key, JSON.stringify(rows)); }
        return {
            list: async function() { return read(); },
            add: async function(data) {
                var rows = read(), existing = rows.find(function(r) { return samePosition(r.position, data.position); });
                if (existing) return existing;
                var row = {id: root.crypto && root.crypto.randomUUID ? root.crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2),
                    name: data.name || '', position: data.position};
                rows.push(row); write(rows); return row;
            },
            rename: async function(id,name) { var rows=read(); rows.forEach(function(r) { if(r.id===id) r.name=name; }); write(rows); },
            remove: async function(id) { write(read().filter(function(r) { return r.id !== id; })); }
        };
    }
    var BLOCKS = 'div,section,figure,p,h1,h2,h3,h4,h5,h6,li,pre,blockquote,dt,dd,td,figcaption,img,svg';
    function blocks(section) {
        var result = Array.from(section.querySelectorAll(BLOCKS)).filter(function(el) {
            return !el.closest('[data-bookmark-marker],.chapter-separator,#scrollLoader') &&
                (el.matches('img,svg') || !el.querySelector('div,section,figure,p,h1,h2,h3,h4,h5,h6,li,pre,blockquote,dt,dd,td,figcaption'));
        });
        return result.length ? result : ((section.textContent || '').trim() ? [section] : []);
    }
    function text(el) {
        if (el.matches('img,svg')) return '@image:' + (el.getAttribute('src') || el.outerHTML).slice(0,1000);
        return (el.textContent || '').replace(/\s+/g,' ').trim().slice(0, 1024);
    }
    function elementKey(el, section) {
        // Order prefix also keeps ID-bearing elements in document order.
        return String(blocks(section).indexOf(el)).padStart(8,'0') + ':' + (el.id ? '#' + el.id : el.tagName.toLowerCase());
    }
    function textOffset(value, p) {
        if (!p.quote) return Math.min(p.offset, value.length);
        var start=p.offset-p.quote_offset;
        if (start>=0 && value.slice(start,start+p.quote.length)===p.quote) return p.offset;
        start=value.indexOf(p.quote);
        if (start<0 || value.indexOf(p.quote,start+1)!==-1) return -1;
        return start+p.quote_offset;
    }
    function resolveElement(section, p) {
        var candidates = blocks(section), index = Number(p.element.split(':')[0]);
        var direct = candidates[index];
        function matches(el) {
            return p.quote ? textOffset(el.textContent || '',p)>=0 : text(el)===p.text;
        }
        if (direct && elementKey(direct,section)===p.element && matches(direct)) return direct;
        var found = candidates.filter(matches);
        return found.length===1 ? found[0] : null;
    }
    function textPoint(el, offset) {
        var walker = document.createTreeWalker(el, 4), node;
        while ((node = walker.nextNode())) {
            if (offset <= node.length) return {node:node,offset:offset};
            offset -= node.length;
        }
        return null;
    }
    function caretOffset(el, x, y) {
        var point = document.caretPositionFromPoint ? document.caretPositionFromPoint(x,y) : null;
        var range = !point && document.caretRangeFromPoint ? document.caretRangeFromPoint(x,y) : null;
        var node = point ? point.offsetNode : range && range.startContainer;
        var offset = point ? point.offset : range && range.startOffset;
        if (!node || !el.contains(node)) return 0;
        var prefix = document.createRange(); prefix.selectNodeContents(el); prefix.setEnd(node, offset);
        return prefix.toString().length;
    }
    function init() {
        var configNode = document.getElementById('bookmarkConfig');
        if (!configNode || !root.EpubReaderBookmarkBridge || configNode.dataset.initialized) return;
        configNode.dataset.initialized='true';
        var config = JSON.parse(configNode.content.textContent), bridge = root.EpubReaderBookmarkBridge;
        var content = document.getElementById('eb-content'), list = document.getElementById('bookmarkList');
        var panel = document.getElementById('bookmarkPanel'), toc = document.getElementById('bookHomeTocList');
        var buttons = Array.from(document.querySelectorAll('[data-bookmark-toggle]'));
        var store = root.EpubBrowserAnonymous ? null : root.EpubBookmarkServerStore ? root.EpubBookmarkServerStore(config.book) : localStore({
            getItem:function(key){return root.localStorage.getItem(key);},
            setItem:function(key,value){root.localStorage.setItem(key,value);}
        }, config.book);
        var rows = [], loaded = false, busy = false, current = null;
        var status = document.getElementById('bookmarkStatus');
        var tab = document.getElementById('bookmarkTab'), tocTab = document.getElementById('bookmarkTocTab');
        var outlineTab=document.getElementById('chapterOutlineTab'), outline=document.getElementById('tocFloating');
        var selectedTab='contents';
        function tr(key, params) { return root.EpubBrowserI18n.t('bookmarks.' + key, params); }
        function message(key, action) {
            root.EpubBrowserNotification.show(tr(key),key==='error'?'error':'success',{
                messageKey:'bookmarks.'+key, duration:action?8000:3000, action:action,
                returnFocus:buttons.find(function(b){return b.getClientRects().length;}) || tab
            });
        }
        function contextMessage(key) {
            status.hidden=false;status.dataset.kind=key;
            var label=el('p',tr(key));label.setAttribute('data-i18n','bookmarks.'+key);
            status.replaceChildren(label);
        }
        function sectionFor(index) {
            return content.querySelector('.continuous-chapter[data-chapter-index="'+index+'"]') ||
                (Number(content.getAttribute('data-chapter-index')) === index ? content : null);
        }
        function reference() {
            var canvas = content.getBoundingClientRect();
            var y = document.body.classList.contains('pagination-mode')
                ? Math.max(0,document.querySelector('.eb-content-container').getBoundingClientRect().top) : 0;
            ['.reader-toolbar','.mobile-controls','.chapter-top-bar'].forEach(function(selector) {
                var el = document.querySelector(selector);
                if (!el || !el.getClientRects().length || ['fixed','sticky'].indexOf(root.getComputedStyle(el).position)<0) return;
                var r=el.getBoundingClientRect();
                if (r.top <= y + 4 && r.bottom > y && r.bottom < root.innerHeight / 2) y=r.bottom;
            });
            return {y:Math.min(root.innerHeight-1,y+8), left:Math.max(0,canvas.left),right:Math.min(root.innerWidth,canvas.right)};
        }
        function capture() {
            var ref=reference(), found=null;
            if (config.format === 'pdf') {
                Array.from(content.querySelectorAll('[data-pdf-page-number]')).some(function(el) {
                    var r=el.getBoundingClientRect();
                    if (r.bottom <= ref.y || r.top >= root.innerHeight || r.right <= ref.left || r.left >= ref.right) return false;
                    found={format:'pdf',page:Number(el.getAttribute('data-pdf-page-number')),y:Math.max(0,Math.min(1,(ref.y-r.top)/r.height))};
                    return true;
                });
                return found;
            }
            blocks(content).some(function(el) {
                if (!text(el)) return false;
                var rects=Array.from(el.getClientRects());
                var r=rects.find(function(r) { return r.bottom>ref.y && r.top<root.innerHeight && r.right>ref.left && r.left<ref.right; });
                if (!r) return false;
                var section=el.closest('.continuous-chapter') || content;
                var index=Number(section.getAttribute('data-chapter-index')), chapter=config.chapters[index];
                if (!chapter || !chapter.path) return false;
                var y=Math.max(r.top+2,ref.y), x=Math.max(ref.left+2,r.left+2);
                found={format:'epub',chapter:chapter.path,chapter_index:index,element:elementKey(el,section),text:text(el),offset:caretOffset(el,x,y)};
                if(!el.matches('img,svg')) {
                    var raw=el.textContent || '', start=Math.max(0,found.offset-32);
                    found.quote=raw.slice(start,found.offset+64);found.quote_offset=found.offset-start;
                }
                return true;
            });
            return found;
        }
        function defaultLabel(row) {
            var p=row.position, index=chapterIndex(p,config.chapters);
            if (p.format==='pdf') return tr('page',{page:p.page});
            if (index < 0) return tr('missingChapter');
            var section=sectionFor(index), el=section && resolveElement(section,p), heading=null;
            if (el) {
                Array.from(section.querySelectorAll('h1,h2,h3,h4,h5,h6')).some(function(h) {
                    if (h===el || (h.compareDocumentPosition(el)&4)) { heading=h; return false; }
                    return true;
                });
            }
            return row.position.label || (heading ? heading.textContent.trim() : config.chapters[index].title);
        }
        function el(tag, value) { var node=document.createElement(tag); if(value) node.textContent=value; return node; }
        function action(key, handler) {
            var button=el('button',tr(key)); button.type='button'; button.dataset.bookmarkLabel=key; button.setAttribute('data-i18n','bookmarks.'+key); button.addEventListener('click',handler); return button;
        }
        function useTab(value) {
            selectedTab=value===true?'bookmarks':value===false?'contents':value;
            panel.hidden=selectedTab!=='bookmarks';toc.hidden=selectedTab!=='contents';outline.hidden=selectedTab!=='outline';
            outline.setAttribute('aria-hidden',String(outline.hidden));
            var locator=document.getElementById('bookHomeLocateCurrent');
            locator.hidden=selectedTab==='bookmarks' || (selectedTab==='outline' && !outline.querySelector('.toc-item a'));
            var locateKey=selectedTab==='outline'?'reader.locateCurrentSection':'reader.locateCurrentChapter';
            locator.setAttribute('data-i18n-aria-label',locateKey);
            locator.setAttribute('aria-label',root.EpubBrowserI18n.t(locateKey));
            tab.setAttribute('aria-pressed',String(!panel.hidden));tocTab.setAttribute('aria-pressed',String(!toc.hidden));
            outlineTab.setAttribute('aria-pressed',String(!outline.hidden));
        }
        function outlineAvailability() {
            outlineTab.hidden=config.format==='pdf' || document.body.classList.contains('continuous-scroll-mode');
            if(outlineTab.hidden && selectedTab==='outline')useTab('contents');
        }
        outlineAvailability();
        root.addEventListener('epub:reader-outline-availability',outlineAvailability);
        root.addEventListener('epub:reader-outline-content',function(){useTab(selectedTab);});
        outlineTab.addEventListener('click',function(){useTab('outline');});
        tab.addEventListener('click',function(){useTab(true);refresh();});
        tocTab.addEventListener('click',function(){useTab(false);});
        if (root.EpubBrowserAnonymous) {
            tab.hidden = true;
            useTab('contents');
            return;
        }
        function render() {
            var expanded=list.querySelector('.bookmark-menu[open]');
            var expandedId=expanded && expanded.dataset.bookmarkId;
            var focus=document.activeElement, focusedId=focus && focus.dataset.bookmarkId, focusedAction=focus && focus.dataset.bookmarkAction;
            list.replaceChildren();
            if (loaded && !rows.length) {
                var empty=el('li');empty.className='bookmark-empty';
                var title=el('p',tr('empty')), help=el('p',tr('emptyHelp'));
                title.className='bookmark-empty-title';help.className='bookmark-empty-help';
                empty.append(title,help);list.appendChild(empty);
            }
            sort(rows,config.chapters).forEach(function(row) {
                var item=el('li'), label=defaultLabel(row);
                    var open=action('open',function(){openBookmark(row);});
                    open.removeAttribute('data-i18n');open.replaceChildren(el('span',row.name || label));
                    open.dataset.bookmarkId=row.id;open.dataset.bookmarkAction='open';
                    item.append(open);
                    var index=chapterIndex(row.position,config.chapters);
                    var locationLabel=row.position.format==='pdf' ? tr('page',{page:row.position.page}) :
                        (index<0 ? tr('missingChapter') : config.chapters[index].title);
                    if(row.name || label!==locationLabel) open.append(el('small',locationLabel));
                    var menu=el('details');menu.className='bookmark-menu';menu.dataset.bookmarkId=row.id;menu.open=expandedId===row.id;
                    var summary=el('summary');summary.setAttribute('aria-label',tr('more'));summary.setAttribute('data-i18n-aria-label','bookmarks.more');
                    summary.textContent='⋯';menu.appendChild(summary);
                    var menuBody=el('div');menuBody.className='bookmark-menu-body';
                    menu.appendChild(menuBody);item.appendChild(menu);
                    menu.addEventListener('keydown',function(event){if(event.key==='Escape'){event.stopPropagation();menu.open=false;summary.focus();}});
                    [['rename',function(){rename(row);}],['delete',function(){remove(row);}]].forEach(function(pair){
                        var b=action(pair[0],pair[1]);b.dataset.bookmarkId=row.id;b.dataset.bookmarkAction=pair[0];menuBody.appendChild(b);
                    });
                list.appendChild(item);
            });
            if (focusedId) {
                var next=list.querySelector('[data-bookmark-id="'+focusedId+'"][data-bookmark-action="'+focusedAction+'"]');
                if(next) next.focus(); else if (!panel.hidden) tab.focus();
            }
            update(); markers();
        }
        async function rename(row) {
            var menu=list.querySelector('.bookmark-menu[data-bookmark-id="'+row.id+'"]');
            if(menu)menu.open=false;
            function trigger(){return list.querySelector('.bookmark-menu[data-bookmark-id="'+row.id+'"] summary');}
            if(trigger())trigger().focus();
            var original=defaultLabel(row), initial=(row.name || original).slice(0,120);
            await root.EpubDialog.prompt({
                titleKey:'bookmarks.renameTitle',messageKey:'bookmarks.renameLocation',messageParams:{location:original},
                inputLabelKey:'bookmarks.name',inputHelpKey:'bookmarks.renameHelp',
                defaultValue:initial,maxLength:120,selectOnOpen:true,
                confirmTextKey:'bookmarks.save',cancelTextKey:'bookmarks.cancel',
                errorKey:'bookmarks.error',returnFocus:trigger,
                onSubmit:function(value){return operate(function(){
                    var name=value.trim();return store.rename(row.id,name===original || (!row.name && name===initial)?'':name);
                }).then(function(){message('saved');});}
            });
        }
        function matchesCurrent(row, p) {
            if(samePosition(row.position,p)) return true;
            if(!p || p.format!=='epub' || row.position.chapter!==p.chapter) return false;
            var section=sectionFor(chapterIndex(p,config.chapters));
            return !!section && resolveElement(section,row.position)===resolveElement(section,p);
        }
        function update() {
            current=capture();
            var saved=rows.some(function(r){return matchesCurrent(r,current);});
            buttons.forEach(function(b){b.disabled=!loaded || !current || busy; b.setAttribute('aria-pressed',String(saved));
                var key=saved?'remove':'add'; b.setAttribute('aria-label',tr(key)); b.title=tr(key);
                b.querySelector('i').className=(saved?'fas':'far')+' fa-bookmark';});
        }
        function markers() {
            content.querySelectorAll('[data-has-bookmark]').forEach(function(el){el.removeAttribute('data-has-bookmark');});
            rows.forEach(function(row){var p=row.position,index=chapterIndex(p,config.chapters),section=sectionFor(index);
                var target=p.format==='pdf' ? content.querySelector('[data-pdf-page-number="'+p.page+'"]') : section && resolveElement(section,p);
                if(target) target.setAttribute('data-has-bookmark','true');
            });
        }
        async function refresh() {
            try { rows=await store.list(); loaded=true;
                if(status.dataset.kind==='error'){status.hidden=true;status.replaceChildren();}
                render(); }
            catch(error){
                loaded=false;contextMessage('error');
                status.appendChild(action('retry',refresh));message('error');update();
            }
        }
        async function operate(operation) {
            if(busy) return;
            busy=true; update();
            try { await operation(); await refresh(); }
            catch(error){message('error');throw error;}
            finally {busy=false;update();}
        }
        function remove(row) {
            operate(function(){return store.remove(row.id);}).then(function(){
                message('removed', {labelKey:'bookmarks.undo', onClick:function(){
                    return operate(function(){return store.add(row);}).then(function(){message('saved');});
                }});
            }).catch(function(){});
        }
        buttons.forEach(function(b){b.addEventListener('click',function(event){
            event.stopPropagation(); var p=capture(); if(!p) return;
            var saved=rows.find(function(r){return matchesCurrent(r,p);});
            if(saved) remove(saved);
            else { p.label=defaultLabel({position:p}).slice(0,200); operate(function(){return store.add({position:p,name:''});}).then(function(){message('saved');}).catch(function(){}); }
        });});
        function fallback(row) {
            useTab(true);
            if(root.EpubReaderDrawers && document.getElementById('bookHomeFloating').getAttribute('aria-hidden')==='true') document.getElementById('bookHomeToggle').click();
            contextMessage('unresolved');
            var index=chapterIndex(row.position,config.chapters);
            if(index>=0) {
                var link=el('a',tr('openChapter'));link.setAttribute('data-i18n','bookmarks.openChapter');link.href='chapter_'+index+'.html';
                status.removeAttribute('data-i18n');status.append(' ',link);
            }
        }
        function openBookmark(row) {
            var index=chapterIndex(row.position,config.chapters);
            if(index<0) {fallback(row);return;}
            if(root.EpubReaderDrawers) root.EpubReaderDrawers.close(false);
            // A full chapter load gives all modes the same restore lifecycle and
            // prevents a stale continuous window from resolving a different chapter.
            root.location.assign('chapter_'+index+'.html'+(new URLSearchParams(root.location.search).get('full')==='1'?'?full=1':'')+'#bookmark='+encodeURIComponent(row.id));
        }
        function restore(row) {
            var p=row.position,index=chapterIndex(p,config.chapters),section=sectionFor(index);
            if (!section) return false;
            var target, rect;
            if(p.format==='pdf') {
                target=section.querySelector('[data-pdf-page-number="'+p.page+'"]');
                if(!target || target.getAttribute('data-pdf-rendered')!=='complete') return false;
                rect=target.getBoundingClientRect();
                rect={top:rect.top+rect.height*p.y,left:rect.left};
            } else {
                target=resolveElement(section,p);
                if(!target) return false;
                var point=textPoint(target,textOffset(target.textContent || '',p)),range;
                if(point){range=document.createRange();range.setStart(point.node,point.offset);range.collapse(true);}
                rect=range && range.getBoundingClientRect();
                if(!rect || (!rect.width && !rect.height)) rect=target.getBoundingClientRect();
            }
            bridge.reveal(target,rect,index,reference().y);
            // Focus the reading surface for keyboard continuity, not the paragraph.
            // The visible bookmark marker identifies the saved content.
            content.setAttribute('tabindex','-1');content.focus({preventScroll:true});
            return true;
        }
        var pendingId=new URLSearchParams(root.location.hash.slice(1)).get('bookmark');
        async function start() {
            await refresh();
            if(!pendingId || !loaded) return;
            var row=rows.find(function(r){return r.id===pendingId;});
            if(!row){useTab(true);contextMessage('unresolved');return;}
            var attempts=0;
            function attempt(){
                if(restore(row)) {markers();return;}
                if(++attempts<50) setTimeout(attempt,100);
                else fallback(row);
            }
            // Existing pagination initialization lays out columns asynchronously.
            setTimeout(attempt,600);
        }
        var frame=false;
        function schedule(){if(frame)return;frame=true;root.requestAnimationFrame(function(){frame=false;update();});}
        root.addEventListener('scroll',schedule,{passive:true});content.addEventListener('scroll',schedule,{passive:true});
        root.addEventListener('resize',schedule);
        content.addEventListener('load',schedule,true);
        if(document.fonts) document.fonts.ready.then(schedule);
        root.addEventListener('epub-browser:chapter-content-added',function(){setTimeout(function(){markers();schedule();},0);});
        root.addEventListener('epub-browser:annotation-content-ready',schedule);
        root.addEventListener('storage',refresh);
        root.addEventListener('focus',refresh);
        root.EpubBrowserI18n.onLocaleChange(function(){render();update();});
        start();
    }
    return {samePosition:samePosition,chapterIndex:chapterIndex,sort:sort,localStore:localStore,resolveElement:resolveElement,textOffset:textOffset,init:init};
});
