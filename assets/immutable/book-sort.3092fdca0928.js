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

    function sortBooks(books, sort, locale) {
        var ranks = Object.create(null);
        if (sort === 'manual') {
            manualOrder().forEach(function(id, index) { ranks[id] = index; });
        }
        var titleCollator = typeof Intl !== 'undefined' && Intl.Collator
            ? new Intl.Collator(locale || undefined, { sensitivity: 'base' }) : null;
        function compare(left, right) {
            return left < right ? -1 : left > right ? 1 : 0;
        }

        return books.slice().sort(function(left, right) {
            var difference;
            if (sort === 'manual') {
                var leftRank = ranks[left.hash];
                var rightRank = ranks[right.hash];
                difference = (leftRank === undefined ? -1 : leftRank) - (rightRank === undefined ? -1 : rightRank);
            } else {
                if (sort === 'created_desc' || sort === 'updated_desc') {
                    var field = sort === 'created_desc' ? 'created_at' : 'updated_at';
                    difference = compare(right[field] || '', left[field] || '');
                    if (difference) return difference;
                }
                var leftTitle = String(left.title || '');
                var rightTitle = String(right.title || '');
                difference = titleCollator ? titleCollator.compare(leftTitle, rightTitle)
                    : leftTitle.toLowerCase().localeCompare(rightTitle.toLowerCase());
                if (sort === 'title_desc') difference = -difference;
            }
            return difference || compare(left.hash, right.hash);
        });
    }

    root.EpubBrowserBookSort = { sortBooks: sortBooks, manualOrder: manualOrder };
})(window);
