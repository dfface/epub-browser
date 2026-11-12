'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const browser = [
  process.env.EPUB_BROWSER_TEST_BROWSER,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].find(candidate => candidate && fs.existsSync(candidate));

test('cross-cell highlights preserve table geometry and wrapped highlights have no fragment borders', {
  skip: browser ? false : 'Chrome, Edge, or Chromium is required for annotation layout',
}, () => {
  const asset = filename => fs.readFileSync(path.join(__dirname, '../epub_browser/assets', filename), 'utf8');
  const annotation = asset('annotation.js').replace(
    /\}\)\(window\);\s*$/, 'window.interaction = HighlightInteraction; })(window);',
  );
  const html = `<!doctype html>
    <style>${asset('annotation.css')}</style>
    <style>td {border: 1px solid; padding: 5px} p {width: 12em}</style>
    <main id="eb-content">
      <table><tbody>
        <tr><td>First row</td><td>Other column</td><td>Last column</td></tr>
        <tr><td id="start">The first cell</td>
            <td id="end">The second cell</td>
            <td>Keep this cell unselected</td></tr>
      </tbody></table>
      <p id="paragraph">Selected words that wrap onto <strong>another line</strong> and end here.</p>
    </main>
    <script>${asset('vendor/web-highlighter/web-highlighter.min.js')}</script>
    <script>${annotation}</script>
    <script>
      try {
        const check = (ok, message) => { if (!ok) throw new Error(message); };
        const table = document.querySelector('table');
        const geometry = () => JSON.stringify([...table.querySelectorAll('td')].map(cell =>
          cell.getBoundingClientRect().toJSON()));
        const before = geometry();
        const highlight = (start, startOffset, end, endOffset) => {
          const range = document.createRange();
          range.setStart(start, startOffset);
          range.setEnd(end, endOffset);
          const selection = getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          end.parentElement.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
          check(interaction.pendingDraft, 'selection did not create a draft');
          return interaction.pendingDraft.source;
        };

        // Use the real selection handler and painter; the floating menu is
        // unrelated to these checks.
        interaction.showCreateDialogFromSource = () => {};
        interaction.init();
        const start = document.querySelector('#start').firstChild;
        const end = document.querySelector('#end').firstChild;
        const draft = highlight(start, 4, end, 10);
        const selectedCells = () => [...table.querySelectorAll('.annotation-highlight')].map(node =>
          [node.closest('td')?.id, node.textContent]);
        const expected = JSON.stringify([['start', 'first cell'], ['end', 'The second']]);
        check(geometry() === before, 'draft changed table cell geometry');
        check(JSON.stringify(selectedCells()) === expected, 'draft wrapped extra nodes or selected the wrong text');
        check(draft.text.includes(String.fromCharCode(10)), 'fixture must retain table indentation in the stored quote');
        const saved = interaction.buildAnnotationFromSource(draft, '#ffeb3b', '');
        interaction.cancelPendingDraft();
        check(!selectedCells().length, 'cancel left draft highlights behind');
        check(interaction.renderHighlight(saved), 'could not replay the stored cross-cell quote');
        check(geometry() === before, 'replay changed table cell geometry');
        check(JSON.stringify(selectedCells()) === expected, 'replay selected the wrong text');

        const paragraph = document.querySelector('#paragraph');
        highlight(paragraph.firstChild, 0, paragraph.lastChild, paragraph.lastChild.length);
        const fragments = [...paragraph.querySelectorAll('.annotation-highlight')];
        check(fragments.length >= 3 && fragments.some(node => node.getClientRects().length > 1),
          'fixture must cover both line wrapping and inline markup');
        const defaultColor = getComputedStyle(fragments[0]).backgroundColor;
        fragments[1].dispatchEvent(new MouseEvent('mouseenter'));
        for (const node of fragments) {
          check(getComputedStyle(node).outlineStyle === 'none', 'hover drew a fragment outline');
          check(node.classList.contains('annotation-hover-active'), 'hover missed a fragment');
        }
        // Finish the color transition before comparing the computed fills.
        for (const node of fragments) node.style.transition = 'none';
        check(getComputedStyle(fragments[0]).backgroundColor !== defaultColor, 'hover did not deepen the fill');
        fragments[1].dispatchEvent(new MouseEvent('mouseleave'));
        for (const node of fragments) {
          node.classList.add('annotation-focus-active');
          check(getComputedStyle(node).outlineStyle === 'none', 'focus drew a fragment outline');
        }
        document.body.dataset.result = 'passed';
      } catch (error) {
        document.body.dataset.result = error.message;
      }
    </script>`;
  const result = spawnSync(browser, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--dump-dom',
    'data:text/html;charset=utf-8,' + encodeURIComponent(html),
  ], { encoding: 'utf8', timeout: 15000 });

  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.match(/<body data-result="([^"]*)"/)?.[1], 'passed');
});
