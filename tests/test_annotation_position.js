const test = require('node:test');
const assert = require('node:assert/strict');

const Position = require('../epub_browser/assets/annotation-position.js');

function element(tagName, chapterIndex) {
  return {
    tagName: tagName.toUpperCase(),
    chapterIndex,
    getAttribute(name) {
      return name === 'data-chapter-index' && chapterIndex !== undefined
        ? String(chapterIndex)
        : null;
    },
  };
}

function section(chapterIndex, descendants) {
  const result = element('section', chapterIndex);
  result.contains = node => node === result || descendants.includes(node);
  result.getElementsByTagName = tagName => descendants.filter(
    node => node.tagName === tagName.toUpperCase()
  );
  descendants.forEach(node => {
    node.closest = selector => selector === '.continuous-chapter' ? result : null;
  });
  return result;
}

function root(elements) {
  return {
    getElementsByTagName(tagName) {
      return elements.filter(node => node.tagName === tagName.toUpperCase());
    },
  };
}

test('continuous annotations belong to the chapter containing their highlight nodes', () => {
  const paragraph = element('p');
  section(9, [paragraph]);

  assert.equal(Position.chapterIndexForNodes([paragraph], 7), 9);
  assert.equal(Position.chapterIndexForNodes([], 7), 7);
});

test('continuous metadata is stored relative to its chapter and restored against the full root', () => {
  const chapter7Paragraph = element('p');
  const chapter8Paragraph = element('p');
  const chapter9First = element('p');
  const chapter9Second = element('p');
  const chapter7 = section(7, [chapter7Paragraph]);
  const chapter8 = section(8, [chapter8Paragraph]);
  const chapter9 = section(9, [chapter9First, chapter9Second]);
  const content = root([
    chapter7,
    chapter7Paragraph,
    chapter8,
    chapter8Paragraph,
    chapter9,
    chapter9First,
    chapter9Second,
  ]);
  const globalMeta = { parentTagName: 'P', parentIndex: 3, textOffset: 12 };

  const chapterMeta = Position.toChapterMeta(globalMeta, content, chapter9);
  assert.deepEqual(chapterMeta, { parentTagName: 'P', parentIndex: 1, textOffset: 12 });
  assert.deepEqual(Position.toRootMeta(chapterMeta, content, chapter9), globalMeta);
});

test('metadata rooted directly at a continuous chapter round-trips through the full root', () => {
  const paragraph = element('p');
  const chapter7 = section(7, [paragraph]);
  const content = root([chapter7, paragraph]);
  const chapterRootMeta = { parentTagName: 'SECTION', parentIndex: -2, textOffset: 4 };

  const rootMeta = Position.toRootMeta(chapterRootMeta, content, chapter7);
  assert.deepEqual(rootMeta, { parentTagName: 'SECTION', parentIndex: 0, textOffset: 4 });
  assert.deepEqual(Position.toChapterMeta(rootMeta, content, chapter7), chapterRootMeta);
});
