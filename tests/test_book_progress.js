const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('epub_browser/assets/book.js','utf8');
const start=source.indexOf('function markReadingChapter(');
const end=source.indexOf('\nfunction ',start+1);
test('book progress expands the target before scrolling a positioned TOC row into view',()=>{
 let revealed=false;
 const row={};
 const link={id:'eb_ci_24#section',offsetTop:0,classList:{add(){},remove(){}},
  setAttribute(){},querySelector:()=>null,closest:()=>row,
  getBoundingClientRect(){assert.equal(revealed,true);return {top:900};}};
 const list={scrollTop:200,offsetTop:500,clientTop:2,getBoundingClientRect:()=>({top:300})};
 const context=vm.createContext({document:{querySelectorAll:()=>[link],getElementById:()=>link,querySelector:()=>list},
  bookPageTocTree:{reveal(target){assert.equal(target,row);revealed=true;}}});
 vm.runInContext(source.slice(start,end),context);
 context.markReadingChapter('eb_ci_24#section');
 assert.equal(list.scrollTop,748);
});
