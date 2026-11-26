const test = require('node:test');
const assert = require('node:assert/strict');
const { createOrderModel } = require('../epub_browser/assets/mobile-toolbar.js');
function storage(initial) {
  const data = new Map(initial ? [['mobileToolbarOrder', initial]] : []);
  return { getItem: key => data.get(key) || null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) };
}
test('toolbar order persists, keeps absent controls in place, and restores defaults', () => {
  const store = storage();
  const model = createOrderModel(store, ['outline', 'pdf', 'home', 'settings']);
  model.move('settings', -1, ['outline', 'home', 'settings']);
  assert.deepEqual(model.order(), ['outline', 'pdf', 'settings', 'home']);
  assert.deepEqual(createOrderModel(store, ['outline', 'pdf', 'home', 'settings']).order(), model.order());
  model.reorder(['home', 'outline', 'settings']);
  assert.deepEqual(model.order(), ['home', 'pdf', 'outline', 'settings']);
  model.reset();
  assert.equal(store.getItem('mobileToolbarOrder'), null);
  assert.deepEqual(model.order(), ['outline', 'pdf', 'home', 'settings']);
});
test('new toolbar controls get their default neighbors and corrupt preferences recover safely', () => {
  assert.deepEqual(createOrderModel(storage('["settings","home"]'), ['home', 'search', 'settings']).order(),
    ['settings', 'home', 'search']);
  for (const saved of ['not JSON', '{}', '[null,"home","home",42]']) {
    assert.deepEqual(createOrderModel(storage(saved), ['home', 'settings']).order(), ['home', 'settings']);
  }
});
