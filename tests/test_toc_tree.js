const test = require('node:test');
const assert = require('node:assert/strict');
const {initBookTocTree} = require('../epub_browser/assets/reader-layout.js');
function harness(saved, storage, levels = [0,1,2,1,0], translate, iconOnly) {
    const rows = levels.map((level,i) => {
        const attrs = {'data-toc-level':String(level)};
        const link = {focus(){focused=i;},getAttribute:()=>`chapter_${i}.html`};
        return {id:'',hidden:false,style:{},attrs,link,children:[],
            getAttribute:k=>attrs[k], setAttribute:(k,v)=>{attrs[k]=v;},
            querySelector:()=>link, insertBefore(button){this.button=button;}};
    });
    let focused, state, keydown;
    const doc = {createElement:()=>({attrs:{},style:{},click(){this.onclick();},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,fn){this[k]=fn;},focus(){focused='toggle';}})};
    const list = {attrs:{},setAttribute(k,v){this.attrs[k]=v;},ownerDocument:doc,querySelectorAll:()=>rows,addEventListener:(k,fn)=>{keydown=fn;}};
    const bulk = doc.createElement('button');
    const controller=initBookTocTree(list,{bulkToggle:bulk,translate,iconOnly,state:saved,bookId:storage ? 'demo' : null,storage,onChange:s=>{state=s;}});
    return {rows,bulk,list,controller,state:()=>state,key(event){list.onkeydown(event);},focused:()=>focused};
}
test('disclosure buttons collapse descendants without changing title destinations',()=>{
    const h=harness();h.rows[0].button.click();
    assert.deepEqual(h.rows.map(r=>r.hidden),[false,true,true,true,false]);
    assert.equal(h.rows[0].button.attrs['aria-expanded'],'false');
    assert.equal(h.rows[0].link.getAttribute('href'),'chapter_0.html');
});
test('saved branch state survives reinitialization; locating reveals all ancestors',()=>{
    const h=harness();h.rows[1].button.click();h.rows[0].button.click();
    const restored=harness(h.state());assert.equal(restored.rows[2].hidden,true);
    restored.controller.reveal(restored.rows[2]);
    assert.equal(restored.rows[2].hidden,false);
    assert.equal(restored.rows[0].button.attrs['aria-expanded'],'true');
    assert.equal(restored.rows[1].button.attrs['aria-expanded'],'true');
});
test('keyboard navigation skips collapsed descendants and opens parents',()=>{
    const h=harness();h.rows[0].button.click();
    const e={key:'ArrowDown',target:h.rows[0],preventDefault(){}};
    h.key(e);assert.equal(h.focused(),4);
    h.key({...e,key:'ArrowRight'});assert.equal(h.rows[1].hidden,false);
});

test('book page and reader instances share expansion state through book storage',()=>{
    const saved=new Map();
    const storage={getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v)};
    const book=harness(undefined,storage);book.rows[0].button.click();
    const reader=harness(undefined,storage);
    assert.equal(reader.rows[1].hidden,true);
    reader.controller.reveal(reader.rows[2]);
    const reopened=harness(undefined,storage);
    assert.equal(reopened.rows[2].hidden,false);
});

test('bulk action collapses and expands every depth and follows individual changes',()=>{
    const h=harness();
    assert.equal(h.bulk.textContent,'Collapse all');
    h.bulk.onclick();
    assert.deepEqual(h.rows.map(r=>r.hidden),[false,true,true,true,false]);
    assert.equal(h.rows[1].button.attrs['aria-expanded'],'false');
    assert.equal(h.bulk.attrs['data-i18n'],'reader.expandAll');
    h.bulk.onclick();
    assert.deepEqual(h.rows.map(r=>r.hidden),[false,false,false,false,false]);
    h.rows[1].button.click();
    assert.equal(h.bulk.textContent,'Expand all');
    h.rows[1].button.click();
    assert.equal(h.bulk.textContent,'Collapse all');
});

test('bulk toggle stays hidden without branches and locating reopens all ancestors',()=>{
    assert.equal(harness(undefined,undefined,[0,0]).bulk.hidden,true);
    assert.equal(harness(undefined,undefined,[]).bulk.hidden,true);
    const h=harness();h.bulk.onclick();
    h.controller.reveal(h.rows[2]);
    assert.equal(h.rows[2].hidden,false);
    assert.equal(h.bulk.textContent,'Collapse all');
});

test('bulk action uses the current locale after state changes',()=>{
    let locale='en';
    const h=harness(undefined,undefined,undefined,key=>locale+':'+key);
    assert.equal(h.bulk.textContent,'en:reader.collapseAll');
    locale='zh-CN';
    h.bulk.onclick();
    assert.equal(h.bulk.textContent,'zh-CN:reader.expandAll');
    assert.equal(h.bulk.attrs['data-i18n'],'reader.expandAll');
});

test('icon action keeps its artwork and updates accessible labels and tooltip',()=>{
    const h=harness(undefined,undefined,undefined,key=>'localized:'+key,true);
    assert.equal(h.bulk.attrs['aria-label'],'localized:reader.collapseAll');
    assert.equal(h.bulk.attrs.title,'localized:reader.collapseAll');
    assert.equal(h.bulk.textContent,undefined);
    h.bulk.click();
    assert.equal(h.bulk.attrs['data-toc-action'],'expand');
    assert.equal(h.bulk.attrs['data-i18n-aria-label'],'reader.expandAll');
    assert.equal(h.bulk.attrs['data-i18n-title'],'reader.expandAll');
    assert.equal(h.bulk.attrs['aria-label'],'localized:reader.expandAll');
    assert.equal(h.bulk.textContent,undefined);
});

test('only a TOC with branches reserves a disclosure column',()=>{
    const flat=harness(undefined,undefined,[0,0,0]);
    assert.equal(flat.list.attrs['data-toc-collapsible'],'false');
    assert.equal(flat.bulk.hidden,true);
    assert.equal(harness().list.attrs['data-toc-collapsible'],'true');
});
