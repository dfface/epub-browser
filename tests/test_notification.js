const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const NotificationModule = require('../epub_browser/assets/notification.js');

function element(tagName) {
  const classes = [];
  return {
    tagName,
    parentNode: null,
    children: [],
    listeners: {},
    appendChild(node) {node.parentNode=this;this.children.push(node);},
    addEventListener(name,callback) {this.listeners[name]=callback;},
    attributes: {},
    textContent: '',
    className: '',
    classList: {
      add(value) { if (!classes.includes(value)) classes.push(value); },
      contains(value) { return classes.includes(value); },
    },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

function fakeRoot() {
  const timers = [];
  const body = {
    children: [],
    appendChild(node) {
      node.parentNode = this;
      this.children.push(node);
    },
    removeChild(node) {
      this.children = this.children.filter(child => child !== node);
      node.parentNode = null;
    },
  };
  return {
    document: { body, createElement: element },
    setTimeout(callback, delay) {
      timers.push({ callback, delay, cancelled: false });
      return timers.length;
    },
    clearTimeout(id) {
      if (timers[id - 1]) timers[id - 1].cancelled = true;
    },
    timers,
  };
}

test('standard notification replaces the active toast and preserves accessibility semantics', () => {
  const root = fakeRoot();
  const notifications = NotificationModule.create(root);

  const first = notifications.show('Saved', 'success');
  const second = notifications.show('Denied', 'error', { persistent: true });

  assert.equal(root.document.body.children.length, 1);
  assert.equal(root.document.body.children[0], second);
  assert.equal(first.parentNode, null);
  assert.equal(second.className, 'app-notification custom-css-notification error');
  assert.equal(second.attributes.role, 'alert');
  assert.equal(second.attributes['aria-live'], 'assertive');
  assert.equal(second.textContent, 'Denied');
});

test('standard notification uses the shared default type and auto-dismiss lifecycle', () => {
  const root = fakeRoot();
  const notifications = NotificationModule.create(root);
  const toast = notifications.show('Working');

  assert.equal(toast.className, 'app-notification custom-css-notification info');
  assert.equal(root.timers[0].delay, 3000);
  root.timers[0].callback();
  assert.equal(toast.classList.contains('fade-out'), true);
  assert.equal(root.timers[1].delay, 300);
  root.timers[1].callback();
  assert.equal(root.document.body.children.length, 0);
});

test('standard notification uses one neutral theme surface with restrained semantic accents', () => {
  const css = fs.readFileSync(
    path.join(__dirname, '../epub_browser/assets/notification.css'),
    'utf8',
  );

  assert.match(css, /background:\s*var\(--toast-bg/);
  assert.match(css, /color:\s*var\(--toast-text/);
  assert.match(css, /border:\s*1px solid var\(--toast-border/);
  assert.doesNotMatch(css, /border-inline-start:/);
  assert.match(
    css,
    /\.custom-css-notification\.info\s*\{\s*--notification-accent:\s*var\(--primary/,
  );
  assert.doesNotMatch(css, /\.custom-css-notification\.info\s*\{\s*background:/);
  assert.doesNotMatch(css, /\.custom-css-notification\.success\s*\{\s*background:/);
});

test('shared notifications support localized undo actions and pause expiry during interaction', async () => {
  const root = fakeRoot();
  let undone = 0;
  root.EpubBrowserI18n = { t:key => ({'bookmarks.removed':'Removed','bookmarks.undo':'Undo'})[key] };
  const api = NotificationModule.create(root);
  const toast = api.show('', 'info', {messageKey:'bookmarks.removed',duration:8000,
    action:{labelKey:'bookmarks.undo',onClick:()=>undone++}});
  const action = toast.children.find(node => node.tagName === 'button');
  assert.equal(action.textContent, 'Undo');
  assert.equal(action.attributes['data-i18n'], 'bookmarks.undo');
  toast.listeners.mouseenter();
  assert.equal(root.timers[0].cancelled, true);
  action.listeners.click();
  await Promise.resolve();
  assert.equal(undone, 1);
});

test('notification position is a browser preference with a safe automatic default', () => {
  const root=fakeRoot(), values={};
  root.localStorage={getItem:k=>values[k]||null,setItem:(k,v)=>values[k]=v};
  const api=NotificationModule.create(root);
  assert.equal(api.getPosition(),'auto');
  api.setPosition('bottom');
  assert.equal(NotificationModule.create(root).getPosition(),'bottom');
  api.setPosition('sideways');
  assert.equal(api.getPosition(),'auto');
  root.localStorage.getItem=()=>{throw Error('blocked');};
  assert.equal(api.getPosition(),'auto');
});

test('corner preferences persist while mobile presentation collapses to a safe centered toast', () => {
  const root=fakeRoot(), values={};
  root.innerWidth=1200;root.innerHeight=800;
  root.localStorage={getItem:k=>values[k],setItem:(k,v)=>values[k]=v};
  root.document.querySelectorAll=()=>[];
  const create=root.document.createElement;
  root.document.createElement=tag=>Object.assign(create(tag),{style:{setProperty(){}}});
  const api=NotificationModule.create(root);
  for(const choice of ['top-left','top-right','bottom-left','bottom-right']) {
    api.setPosition(choice);
    assert.equal(api.getPosition(),choice);
    assert.equal(api.show('Preview').attributes['data-notification-placement'],choice);
    root.innerWidth=390;
    assert.equal(api.show('Preview').attributes['data-notification-placement'],choice.startsWith('top')?'top':'bottom');
    assert.equal(api.getPosition(),choice);
    root.innerWidth=1200;
  }
});
