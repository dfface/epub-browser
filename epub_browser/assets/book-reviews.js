(function(root, factory) {
  var api = factory(root);
  api.create = function(target) { return factory(target).create(); };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.EpubBookReviews = api;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  var instanceCount = 0;
  function translate(key) { var i18n = root.EpubBrowserI18n; return i18n && i18n.t ? i18n.t(key) : key; }
  function endpoint(bookId) {
    var path = '/api/book-reviews/' + encodeURIComponent(bookId);
    return root.EpubBrowserURL && root.EpubBrowserURL.publicPath ? root.EpubBrowserURL.publicPath(path) : path;
  }
  function request(bookId, method, body) {
    if (!root.EpubBrowserAuth || !root.EpubBrowserAuth.fetch) return Promise.reject(new Error('authenticated_fetch_unavailable'));
    var options = { method: method, headers: {} };
    if (body) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    return Promise.resolve(root.EpubBrowserAuth.fetch(endpoint(bookId), options)).then(function(response) {
      if (!response || !response.ok) throw new Error('book_review_request_failed');
      return method === 'DELETE' ? null : response.json().catch(function() { return {}; });
    });
  }

  function createClient() {
    var documentTarget = root.document, view = {}, bookId = '', savedRating = '', savedText = '';
    var displayRoot = null, modal = null, dialog = null, trigger = null, keydownBound = false, scrollY = 0;
    function hasSavedReview() { return Boolean(savedRating); }
    function icon(name) { var node = documentTarget.createElement('i'); node.className = 'fas ' + name; node.setAttribute('aria-hidden', 'true'); return node; }
    function setStatus(message, isError) {
      if (!isError) return;
      if (view.status) { view.status.textContent = message; view.status.setAttribute('data-state', 'error'); }
      if (root.EpubBrowserNotification && root.EpubBrowserNotification.show) root.EpubBrowserNotification.show(message, 'error');
    }
    function setBusy(busy) {
      [view.rating, view.reviewText, view.saveButton, view.deleteButton].concat(view.ratingOptions || []).forEach(function(control) { if (control) control.disabled = busy; });
      if (view.root) view.root.setAttribute('aria-busy', busy ? 'true' : 'false');
    }
    function clearRatingError() {
      if (!view.ratingError || !view.ratingField) return;
      view.ratingError.textContent = ''; view.ratingError.hidden = true; view.ratingField.removeAttribute('aria-invalid');
    }
    function showRatingError() {
      if (!view.ratingError || !view.ratingField) return;
      view.ratingError.textContent = translate('bookReviews.ratingRequired'); view.ratingError.hidden = false; view.ratingField.setAttribute('aria-invalid', 'true');
      var first = (view.ratingOptions || [])[0]; if (first && first.focus) first.focus();
    }
    function currentRating() { return view.rating ? String(view.rating.value || '') : ''; }
    function applyRating(rating) {
      if (view.rating) view.rating.value = rating || '';
      (view.ratingOptions || []).forEach(function(option) {
        var selected = option.value === String(rating || '');
        option.setAttribute('aria-checked', selected ? 'true' : 'false');
        option.className = 'book-review-star-option' + (Number(option.value) <= Number(rating || 0) ? ' is-filled' : '');
      });
      clearRatingError();
    }
    function renderDisplay() {
      if (!displayRoot) return;
      displayRoot.replaceChildren(); displayRoot.hidden = !hasSavedReview();
      if (!hasSavedReview()) return;
      var header = documentTarget.createElement('div'); header.className = 'book-review-display-header';
      var title = documentTarget.createElement('h2'); title.textContent = translate('bookReviews.title');
      var rating = documentTarget.createElement('span'); rating.className = 'book-review-display-rating'; rating.setAttribute('aria-label', translate('bookReviews.ratingValue').replace('{rating}', savedRating));
      var stars = documentTarget.createElement('span'); stars.setAttribute('aria-hidden', 'true'); stars.textContent = '★★★★★'.slice(0, Number(savedRating));
      var score = documentTarget.createElement('span'); score.className = 'book-review-display-score'; score.textContent = savedRating + '/5';
      rating.appendChild(stars); rating.appendChild(score); header.appendChild(title); header.appendChild(rating); displayRoot.appendChild(header);
      var privacy = documentTarget.createElement('p'); privacy.className = 'book-review-display-private'; privacy.textContent = translate('bookReviews.private'); displayRoot.appendChild(privacy);
      if (!savedText) return;
      var copy = documentTarget.createElement('p'); copy.className = 'book-review-display-copy is-collapsed'; copy.textContent = savedText; displayRoot.appendChild(copy);
      var expand = documentTarget.createElement('button'); expand.type = 'button'; expand.className = 'book-review-expand'; expand.textContent = translate('bookReviews.showMore'); expand.setAttribute('aria-expanded', 'false'); expand.hidden = savedText.length <= 100;
      expand.addEventListener('click', function() {
        var expanded = expand.getAttribute('aria-expanded') === 'true';
        var labelKey = expanded ? 'bookReviews.showMore' : 'bookReviews.showLess';
        expand.setAttribute('aria-expanded', expanded ? 'false' : 'true'); expand.textContent = translate(labelKey);
        copy.className = 'book-review-display-copy' + (expanded ? ' is-collapsed' : '');
      });
      displayRoot.appendChild(expand);
      if (root.requestAnimationFrame) root.requestAnimationFrame(function() { if (copy.scrollHeight && copy.clientHeight) expand.hidden = copy.scrollHeight <= copy.clientHeight; });
    }
    function render(target) {
      var id = 'book-review-' + (++instanceCount); target.replaceChildren(); target.className = (target.className ? target.className + ' ' : '') + 'book-reviews'; target.setAttribute('aria-labelledby', 'book-review-dialog-title');
      var header = documentTarget.createElement('div'); header.className = 'book-review-header';
      var heading = documentTarget.createElement('h2'); heading.id = 'book-review-dialog-title'; heading.textContent = translate('bookReviews.write');
      var closeButton = documentTarget.createElement('button'); closeButton.type = 'button'; closeButton.className = 'book-review-close'; closeButton.setAttribute('aria-label', translate('dialog.cancel')); closeButton.appendChild(icon('fa-times'));
      header.appendChild(heading); header.appendChild(closeButton);
      var form = documentTarget.createElement('form'); form.className = 'book-review-form'; form.setAttribute('novalidate', '');
      var ratingField = documentTarget.createElement('fieldset'); ratingField.className = 'book-review-rating'; ratingField.setAttribute('aria-describedby', id + '-rating-error');
      var legend = documentTarget.createElement('legend'); legend.className = 'book-review-visually-hidden'; legend.textContent = translate('bookReviews.rating');
      var options = documentTarget.createElement('div'); options.className = 'book-review-rating-options'; options.setAttribute('role', 'radiogroup'); options.setAttribute('aria-label', translate('bookReviews.rating'));
      var rating = documentTarget.createElement('input'); rating.type = 'hidden'; rating.value = '';
      var ratingOptions = [];
      for (var value = 1; value <= 5; value++) {
        var option = documentTarget.createElement('button'); option.type = 'button'; option.value = String(value); option.className = 'book-review-star-option'; option.setAttribute('role', 'radio'); option.setAttribute('aria-checked', 'false'); option.setAttribute('aria-label', translate('bookReviews.ratingValue').replace('{rating}', String(value))); option.appendChild(icon('fa-star'));
        option.addEventListener('click', (function(selected) { return function() { applyRating(String(selected)); }; })(value)); options.appendChild(option); ratingOptions.push(option);
      }
      var ratingError = documentTarget.createElement('p'); ratingError.id = id + '-rating-error'; ratingError.className = 'book-review-rating-error'; ratingError.setAttribute('role', 'alert'); ratingError.hidden = true;
      ratingField.appendChild(legend); ratingField.appendChild(options); ratingField.appendChild(ratingError);
      var reviewLabel = documentTarget.createElement('label'); reviewLabel.className = 'book-review-visually-hidden'; reviewLabel.setAttribute('for', id + '-text'); reviewLabel.textContent = translate('bookReviews.review');
      var reviewText = documentTarget.createElement('textarea'); reviewText.id = id + '-text'; reviewText.maxLength = 10000; reviewText.setAttribute('maxlength', '10000'); reviewText.setAttribute('aria-describedby', id + '-hint');
      var hint = documentTarget.createElement('p'); hint.id = id + '-hint'; hint.className = 'book-review-hint'; hint.textContent = translate('bookReviews.reviewHint');
      var actions = documentTarget.createElement('div'); actions.className = 'book-review-actions';
      var deleteButton = documentTarget.createElement('button'); deleteButton.type = 'button'; deleteButton.className = 'book-review-delete'; deleteButton.textContent = translate('bookReviews.delete');
      var saveButton = documentTarget.createElement('button'); saveButton.type = 'submit'; saveButton.className = 'css-btn primary'; saveButton.textContent = translate('bookReviews.save'); actions.appendChild(deleteButton); actions.appendChild(saveButton);
      var status = documentTarget.createElement('p'); status.className = 'book-review-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.setAttribute('aria-atomic', 'true');
      form.appendChild(ratingField); form.appendChild(reviewLabel); form.appendChild(reviewText); form.appendChild(hint); form.appendChild(actions); target.appendChild(header); target.appendChild(form); target.appendChild(status);
      view = { root: target, rating: rating, ratingOptions: ratingOptions, reviewText: reviewText, saveButton: saveButton, deleteButton: deleteButton, status: status, ratingField: ratingField, ratingError: ratingError, closeButton: closeButton };
      form.addEventListener('submit', function(event) { event.preventDefault(); save(currentRating(), reviewText.value); }); deleteButton.addEventListener('click', deleteReview);
    }
    function restoreSaved() { applyRating(savedRating); if (view.reviewText) view.reviewText.value = savedText; }
    function applyReview(review) { savedRating = review && Number.isInteger(review.rating) ? String(review.rating) : ''; savedText = review && typeof review.review_text === 'string' ? review.review_text : ''; restoreSaved(); renderDisplay(); if (view.deleteButton) view.deleteButton.hidden = !hasSavedReview(); }
    function load() { return request(bookId, 'GET').then(function(payload) { applyReview(payload && payload.review); return payload && payload.review; }).catch(function() { restoreSaved(); setStatus(translate('book.error.server_error'), true); return null; }); }
    function save(rating, reviewText) {
      var normalizedRating = Number(rating);
      if (!Number.isInteger(normalizedRating) || normalizedRating < 1 || normalizedRating > 5) { showRatingError(); return Promise.resolve(null); }
      clearRatingError(); setBusy(true);
      return request(bookId, 'PUT', { rating: normalizedRating, review_text: String(reviewText || '') }).then(function(payload) { applyReview(payload && payload.review ? payload.review : { rating: normalizedRating, review_text: String(reviewText || '') }); closePanel(); return payload; }).catch(function() { restoreSaved(); setStatus(translate('book.error.server_error'), true); return null; }).finally(function() { setBusy(false); });
    }
    function deleteReview() {
      if (!hasSavedReview()) return Promise.resolve(null);
      if (typeof root.confirm === 'function' && !root.confirm(translate('bookReviews.deleteConfirm'))) return Promise.resolve(null);
      setBusy(true);
      return request(bookId, 'DELETE').then(function() { applyReview(null); closePanel(); return true; }).catch(function() { restoreSaved(); setStatus(translate('book.error.server_error'), true); return null; }).finally(function() { setBusy(false); });
    }
    function focusEditor() { var selected = (view.ratingOptions || []).filter(function(option) { return option.getAttribute('aria-checked') === 'true'; })[0]; var control = selected || (view.ratingOptions || [])[0] || view.reviewText || dialog; if (control && control.focus) control.focus(); }
    function closePanel() {
      if (!modal) return;
      modal.hidden = true;
      if (documentTarget && documentTarget.body) { documentTarget.body.classList.remove('book-review-open'); documentTarget.body.style.top = ''; }
      if (root.scrollTo) root.scrollTo(0, scrollY);
      if (trigger) { trigger.setAttribute('aria-expanded', 'false'); if (trigger.focus) trigger.focus(); }
    }
    function onKeydown(event) {
      if (!modal || modal.hidden) return;
      if (event.key === 'Escape') { event.preventDefault(); closePanel(); return; }
      if (event.key !== 'Tab' || !modal.querySelectorAll) return;
      var focusable = modal.querySelectorAll('button:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
      if (!focusable.length) return;
      var first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && documentTarget.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && documentTarget.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    function openPanel() {
      if (!modal) return;
      scrollY = root.scrollY || 0;
      if (documentTarget && documentTarget.body) { documentTarget.body.classList.add('book-review-open'); documentTarget.body.style.top = '-' + scrollY + 'px'; }
      modal.hidden = false;
      if (trigger) trigger.setAttribute('aria-expanded', 'true'); focusEditor();
    }
    function mount(rootElement, suppliedBookId, suppliedDisplayRoot) {
      var target = rootElement;
      if (typeof rootElement === 'string' || !rootElement) { suppliedDisplayRoot = suppliedBookId; suppliedBookId = rootElement || suppliedBookId; target = documentTarget && documentTarget.querySelector('[data-book-reviews]'); }
      if (!target || !suppliedBookId) return Promise.resolve(null);
      bookId = String(suppliedBookId); displayRoot = suppliedDisplayRoot || (documentTarget && documentTarget.querySelector('[data-book-review-display]')); render(target);
      trigger = documentTarget && documentTarget.querySelector('[data-book-review-toggle]'); modal = documentTarget && documentTarget.querySelector('[data-book-review-modal]'); dialog = documentTarget && documentTarget.querySelector('[data-book-review-modal] .book-review-dialog');
      if (trigger) trigger.addEventListener('click', openPanel); if (modal) modal.addEventListener('click', function(event) { if (event.target === modal) closePanel(); }); if (view.closeButton) view.closeButton.addEventListener('click', closePanel);
      if (!keydownBound && documentTarget && documentTarget.addEventListener) { keydownBound = true; documentTarget.addEventListener('keydown', onKeydown); }
      return load();
    }
    return { mount: mount, save: save, deleteReview: deleteReview, get rating() { return view.rating; }, get ratingOptions() { return view.ratingOptions || []; }, get reviewText() { return view.reviewText; }, get ratingError() { return view.ratingError; }, get ratingField() { return view.ratingField; }, get deleteButton() { return view.deleteButton; } };
  }
  var defaultClient = createClient();
  return { mount: function(rootElement, bookId, displayRoot) { return defaultClient.mount(rootElement, bookId, displayRoot); }, create: createClient };
});
