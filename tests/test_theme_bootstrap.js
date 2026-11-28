const test = require('node:test');
const assert = require('node:assert/strict');
const ThemeBootstrap = require('../epub_browser/assets/theme-bootstrap.js');

function themedRoot(storedTheme) {
  const classes = new Set(['light-mode']);
  return {
    localStorage: { getItem(key) { return key === 'theme' ? storedTheme : null; } },
    document: {
      documentElement: {
        classList: {
          add(value) { classes.add(value); },
          remove(value) { classes.delete(value); },
          contains(value) { return classes.has(value); },
        },
      },
    },
    classes,
  };
}

test('public account bootstrap applies the saved EPUB Browser theme', () => {
  const root = themedRoot('forest');

  assert.equal(ThemeBootstrap.apply(root), 'forest');
  assert.equal(root.classes.has('forest-mode'), true);
  assert.equal(root.classes.has('light-mode'), false);
});

test('public account bootstrap rejects unknown stored theme names', () => {
  const root = themedRoot('injected-theme');

  assert.equal(ThemeBootstrap.apply(root), 'light');
  assert.equal(root.classes.has('light-mode'), true);
  assert.equal(root.classes.has('injected-theme-mode'), false);
});


test('configured themes follow the device at startup without replacing the manual theme', () => {
  const root = themedRoot('forest');
  root.EpubBrowserAppearance = { automatic: true, day: 'sepia', night: 'lavender', manual: 'ocean' };
  root.EpubBrowserMode = 'server';
  const device = { matches: true };
  root.matchMedia = query => {
    assert.equal(query, '(prefers-color-scheme: dark)');
    return device;
  };

  assert.equal(ThemeBootstrap.apply(root), 'lavender');
  device.matches = false;
  assert.equal(ThemeBootstrap.apply(root), 'sepia');
  assert.deepEqual([...root.classes], ['sepia-mode']);

  root.EpubBrowserAppearance.automatic = false;
  assert.equal(ThemeBootstrap.apply(root), 'ocean');

  root.EpubBrowserMode = 'ssg';
  assert.equal(ThemeBootstrap.apply(root), 'forest');
});

test('anonymous Server readers choose and restore a local dark theme without account requests', () => {
  const vm = require('node:vm'), fs = require('node:fs');
  const values = {theme:'dark'}, root = themedRoot('dark');
  root.EpubBrowserMode='server'; root.EpubBrowserAnonymous=true;
  root.EpubBrowserAppearance={manual:'light'};
  root.localStorage={getItem:k=>values[k]||null,setItem:(k,v)=>{values[k]=v;}};
  root.EpubBrowserThemeBootstrap=ThemeBootstrap;
  root.EpubBrowserAuth={fetch:()=>assert.fail('anonymous theme must not use account API')};
  root.EpubBrowserI18n={t:k=>k,onLocaleChange(){}};
  root.addEventListener=()=>{};root.innerWidth=1000;
  function node() {return {children:[],style:{},listeners:{},setAttribute(){},querySelector(){return null;},
    appendChild(n){this.children.push(n);},addEventListener(k,f){this.listeners[k]=f;},focus(){},
    getBoundingClientRect(){return {bottom:10,right:20};},set innerHTML(v){this.children=[];}};}
  const toggle=node(), body=node();
  Object.assign(root.document,{body,createElement:node,createTextNode:()=>({}),addEventListener(){},
    getElementById:id=>id==='themeToggle'?toggle:null});
  vm.runInNewContext(fs.readFileSync(require.resolve('../epub_browser/assets/theme.js'),'utf8'),{window:root,document:root.document});
  root.initTheme();
  assert.equal(root.classes.has('dark-mode'),true);
  toggle.listeners.click({stopPropagation(){}});
  const menu=body.children[0];
  menu.children[2].listeners.click();
  assert.equal(values.theme,'sepia');
  assert.equal(root.classes.has('sepia-mode'),true);
  menu.children[1].listeners.click();
  assert.equal(values.theme,'dark');
  assert.equal(ThemeBootstrap.apply(root),'dark');
});
