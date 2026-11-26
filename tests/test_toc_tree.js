const test = require('node:test');
const assert = require('node:assert/strict');
const {initBookTocTree} = require('../epub_browser/assets/reader-layout.js');
function harness(saved, storage) {
    const rows = [0,1,2,1,0].map((level,i) => {
        const attrs = {'data-toc-level':String(level)};
        const link = {focus(){focused=i;},getAttribute:()=>`chapter_${i}.html`};
        return {id:'',hidden:false,attrs,link,children:[],
            getAttribute:k=>attrs[k], setAttribute:(k,v)=>{attrs[k]=v;},
            querySelector:()=>link, insertBefore(button){this.button=button;}};
    });
    let focused, state, keydown;
    const doc = {createElement:()=>({attrs:{},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,fn){this[k]=fn;},focus(){focused='toggle';}})};
    const list = {ownerDocument:doc,querySelectorAll:()=>rows,addEventListener:(k,fn)=>{keydown=fn;}};
    const controller=initBookTocTree(list,{state:saved,bookId:storage ? 'demo' : null,storage,onChange:s=>{state=s;}});
    return {rows,controller,state:()=>state,key(event){keydown(event);},focused:()=>focused};
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
    const e={key:'ArrowDown',target:{closest:()=>h.rows[0]},preventDefault(){}};
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
