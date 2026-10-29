// Focused unit test for scopeCSS() in epub_browser/assets/chapter.js.
// Verifies that book :root / html / body custom properties are scoped to the
// content container (no document-root leak) and that @media prefers-color-scheme:
// dark is bridged to the reader's .dark-mode toggle.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const chapterJsPath = path.resolve(
  __dirname, '..', 'epub_browser', 'assets', 'chapter.js'
);
const code = fs.readFileSync(chapterJsPath, 'utf8');

const sandbox = {
  document: {
    createElement: () => ({ getContext: () => ({ font: '', measureText: () => ({ width: 0 }) }) }),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
  },
  window: {},
  history: {},
  console: console,
};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

const scopeCSS = sandbox.scopeCSS;
if (typeof scopeCSS !== 'function') {
  console.error('scopeCSS is not defined on sandbox');
  process.exit(1);
}

const SCOPE = '[data-eb-styles]';
let failures = 0;
function check(name, cond) {
  if (cond) { console.log('PASS: ' + name); }
  else { console.error('FAIL: ' + name); failures++; }
}

// 1. :root variables scoped to content container, not document :root (no leak).
const r1 = scopeCSS(':root { --accent: #008b8b; --code-bg: #f5f5f5; }', SCOPE);
check(':root -> [data-eb-styles] (not :root)', r1.includes(SCOPE + '{') && !/:root\s*\{/.test(r1));

// 2. standalone html / body selectors map to the content container.
const r2 = scopeCSS('html { --x: 1 } body { color: red }', SCOPE);
check('html -> scope', r2.includes(SCOPE + '{ --x: 1 }'));
check('body -> scope', r2.includes(SCOPE + '{ color: red }'));

// 3. ordinary selectors still scoped as descendants.
const r3 = scopeCSS('pre { color: red }', SCOPE);
check('pre -> scope pre', r3.includes(SCOPE + ' pre'));

// 4. prefers-color-scheme: dark is CONVERTED to the reader .dark-mode block and
//    the original OS-driven @media wrapper is dropped (no OS leak into light).
const r4 = scopeCSS(
  '@media (prefers-color-scheme: dark) { :root { --code-bg: #161b22; --code-text: #e6edf3; } }',
  SCOPE
);
check('does NOT keep raw @media prefers-color-scheme: dark (no OS leak)',
  !r4.includes('@media (prefers-color-scheme: dark)'));
check('converts to .dark-mode scope',
  r4.includes('.dark-mode ' + SCOPE + '{') &&
  r4.includes('--code-bg: #161b22'));

// 5. combined media (screen and prefers-color-scheme: dark) also converted.
const r5 = scopeCSS(
  '@media screen and (prefers-color-scheme: dark) { :root { --c: #000; } }',
  SCOPE
);
check('converts combined media to .dark-mode', r5.includes('.dark-mode ' + SCOPE + '{'));
check('does NOT keep raw combined @media', !r5.includes('@media screen and (prefers-color-scheme: dark)'));

// 6. prefers-color-scheme: light must NOT be bridged.
const r6 = scopeCSS(
  '@media (prefers-color-scheme: light) { :root { --c: #fff; } }',
  SCOPE
);
check('light media not bridged', !r6.includes('.dark-mode ' + SCOPE + ' {'));

if (failures > 0) {
  console.error('\n' + failures + ' failure(s)');
  process.exit(1);
}
console.log('\nAll scopeCSS checks passed.');
