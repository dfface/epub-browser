/* Catalogue sorting also runs on the ES5 Kindle library. */
(function(root) {
    'use strict';

    function manualOrder() {
        try {
            var order = JSON.parse(root.localStorage.getItem('book-grid-sortable-order'));
            return Array.isArray(order) ? order : [];
        } catch (error) {
            return [];
        }
    }

    function shelfState() {
        var data;
        try {
            data = JSON.parse(root.localStorage.getItem('bookshelf'));
        } catch (error) {
            data = null;
        }
        var added = data && data.added && typeof data.added === 'object' ? data.added : {};
        var state = { added: Object.create(null), inShelf: Object.create(null) };
        var seen = Object.create(null);
        var index = 0;

        function visit(container) {
            if (!container || typeof container !== 'object') return;
            var groups = container.groups && typeof container.groups === 'object' ? container.groups : {};
            var items = Array.isArray(container.items) ? container.items : [];
            var order = Array.isArray(container.order) ? container.order : items.concat(Object.keys(groups));

            function addBook(id) {
                if (typeof id !== 'string' || seen[id]) return;
                seen[id] = true;
                index += 1;
                state.inShelf[id] = true;
                var value = added[id];
                state.added[id] = typeof value === 'number' && isFinite(value) ? value : index;
            }

            order.forEach(function(id) {
                if (groups[id]) visit(groups[id]);
                else addBook(id);
            });
            items.forEach(addBook);
            Object.keys(groups).forEach(function(id) {
                if (order.indexOf(id) === -1) visit(groups[id]);
            });
        }

        visit(data);
        return state;
    }

    function sortBooks(books, sort, locale) {
        var ranks = Object.create(null);
        if (sort === 'manual' || sort === 'shelf_first') {
            manualOrder().forEach(function(id, index) { ranks[id] = index; });
        }
        var shelf = sort === 'shelf_first' ? shelfState() : null;
        var titleCollator = typeof Intl !== 'undefined' && Intl.Collator
            ? new Intl.Collator(locale || undefined, { sensitivity: 'base' }) : null;
        function compare(left, right) {
            return left < right ? -1 : left > right ? 1 : 0;
        }

        function titleDifference(left, right) {
            var leftTitle = String(left.title || '');
            var rightTitle = String(right.title || '');
            return titleCollator ? titleCollator.compare(leftTitle, rightTitle)
                : leftTitle.toLowerCase().localeCompare(rightTitle.toLowerCase());
        }

        return books.slice().sort(function(left, right) {
            var difference;
            if (sort === 'shelf_first') {
                var leftInShelf = shelf.inShelf[left.hash] ? 0 : 1;
                var rightInShelf = shelf.inShelf[right.hash] ? 0 : 1;
                difference = leftInShelf - rightInShelf;
                if (!difference && leftInShelf === 0) {
                    difference = (shelf.added[right.hash] || 0) - (shelf.added[left.hash] || 0);
                }
                if (!difference) {
                    var leftShelfRank = ranks[left.hash];
                    var rightShelfRank = ranks[right.hash];
                    difference = (leftShelfRank === undefined ? -1 : leftShelfRank)
                        - (rightShelfRank === undefined ? -1 : rightShelfRank);
                }
            } else if (sort === 'manual') {
                var leftRank = ranks[left.hash];
                var rightRank = ranks[right.hash];
                difference = (leftRank === undefined ? -1 : leftRank) - (rightRank === undefined ? -1 : rightRank);
            } else if (sort === 'pdf_first') {
                difference = (left.format === 'pdf' ? 0 : 1) - (right.format === 'pdf' ? 0 : 1);
                if (!difference) {
                    difference = compare(right.created_at || '', left.created_at || '');
                }
                if (!difference) difference = titleDifference(left, right);
            } else {
                if (sort === 'created_desc' || sort === 'updated_desc') {
                    var field = sort === 'created_desc' ? 'created_at' : 'updated_at';
                    difference = compare(right[field] || '', left[field] || '');
                    if (difference) return difference;
                }
                difference = titleDifference(left, right);
                if (sort === 'title_desc') difference = -difference;
            }
            return difference || compare(left.hash, right.hash);
        });
    }

    root.EpubBrowserBookSort = { sortBooks: sortBooks, manualOrder: manualOrder };
})(window);
