const test = require('node:test');
const assert = require('node:assert/strict');
const B = require('../epub_browser/assets/bookmarks.js');
const p = {format:'epub',chapter:'OPS/one.xhtml',chapter_index:0,element:'p:3',text:'Hello',offset:5};
test('paragraph equivalence ignores layout and text offset, PDF equivalence uses original page', () => {
  assert.equal(B.samePosition(p, {...p, offset:20, chapter_index:9}), true);
  assert.equal(B.samePosition(p, {...p, element:'p:4'}), false);
  assert.equal(B.samePosition({format:'pdf',page:8,y:.2},{format:'pdf',page:8,y:.8}), true);
  assert.equal(B.samePosition({format:'pdf',page:8,y:.2},{format:'pdf',page:9,y:.2}), false);
});
test('chapter resolution and ordering survive reconversion; missing identity is never replaced by old index', () => {
  const chapters = [{path:'OPS/new.xhtml'}, {path:'OPS/one.xhtml'}];
  assert.equal(B.chapterIndex(p, chapters), 1);
  assert.equal(B.chapterIndex({...p,chapter:'removed.xhtml'}, chapters), -1);
  const rows = [{id:'late',position:{...p,element:'p:12'}}, {id:'early',position:{...p,element:'p:3'}}];
  assert.deepEqual(B.sort(rows, chapters).map(x=>x.id), ['early','late']);
});
test('local adapter persists independent books and names, deduplicates and deletes', async () => {
  const values = {};
  const storage = {getItem:k=>values[k]||null,setItem:(k,v)=>values[k]=v};
  const a = B.localStore(storage, 'a'), b = B.localStore(storage, 'b');
  const row = await a.add({position:p,name:''});
  assert.equal((await a.add({position:{...p,offset:10}})).id, row.id);
  await a.rename(row.id,'Home');
  assert.equal((await B.localStore(storage,'a').list())[0].name,'Home');
  assert.deepEqual(await b.list(),[]);
  await a.remove(row.id);
  assert.deepEqual(await a.list(),[]);
});
test('storage failure and damaged data remain errors rather than silently overwriting bookmarks', async () => {
  const a = B.localStore({getItem:()=>'{broken',setItem:()=>assert.fail('must not overwrite')},'a');
  await assert.rejects(a.list());
  const b = B.localStore({getItem:()=>null,setItem:()=>{throw Error('quota');}},'b');
  await assert.rejects(b.add({position:p}));
});
test('text context follows inserted text and refuses ambiguous or removed text', () => {
  const p={offset:4,quote:'the door opened',quote_offset:4};
  assert.equal(B.textOffset('the door opened',p),4);
  assert.equal(B.textOffset('Later, the door opened',p),11);
  assert.equal(B.textOffset('the door opened; the door opened',{...p,offset:100}),-1);
  assert.equal(B.textOffset('the window opened',p),-1);
});
