(function(root, factory) {
  var api = factory(root);
  api.create = function(target) { return factory(target).create(); };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.EpubBookReviews = api;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  var instanceCount = 0;

  function translate(key) {
    var i18n = root.EpubBrowserI18n;
    return i18n && typeof i18n.t === 'function' ? i18n.t(key) : key;
  }

  function endpoint(bookId) {
    var path = '/api/book-reviews/' + encodeURIComponent(bookId);
    return root.EpubBrowserURL && typeof root.EpubBrowserURL.publicPath === 'function'
      ? root.EpubBrowserURL.publicPath(path) : path;
  }

  function request(bookId, method, body) {
    if (!root.EpubBrowserAuth || typeof root.EpubBrowserAuth.fetch !== 'function') {
      return Promise.reject(new Error('authenticated_fetch_unavailable'));
    }
    var options = { method: method, headers: {} };
    if (body) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    return Promise.resolve(root.EpubBrowserAuth.fetch(endpoint(bookId), options)).then(function(response) {
      if (!response || !response.ok) throw new Error('book_review_request_failed');
      if (method === 'DELETE') return null;
      return response.json().catch(function() { return {}; });
    });
  }

  function createClient() {
    var documentTarget = root.document;
    var view = {};
    var bookId = '';
    var savedRating = '';
    var savedText = '';

    function setStatus(message, isError) {
      if (view.status) {
        view.status.textContent = message;
        view.status.setAttribute('data-state', isError ? 'error' : 'success');
      }
      if (root.EpubBrowserNotification && typeof root.EpubBrowserNotification.show === 'function') {
        root.EpubBrowserNotification.show(message, isError ? 'error' : 'success');
      }
    }

    function setBusy(busy) {
      [view.rating, view.reviewText, view.saveButton, view.deleteButton].forEach(function(control) {
        if (control) control.disabled = busy;
      });
      if (view.root) view.root.setAttribute('aria-busy', busy ? 'true' : 'false');
    }

    function currentRating() {
      if (!view.rating) return '';
      return String(view.rating.value || '');
    }

    function updateSummary() {
      if (!view.summary) return;
      view.summary.replaceChildren();
      if (!savedRating) {
        view.summary.hidden = true;
        return;
      }
      var stars = documentTarget.createElement('span');
      stars.className = 'book-review-summary-stars';
      stars.setAttribute('aria-hidden', 'true');
      stars.textContent = '★★★★★'.slice(0, Number(savedRating));
      var copy = documentTarget.createElement('span');
      copy.className = 'book-review-summary-copy';
      copy.textContent = translate('bookReviews.savedRating');
      view.summary.appendChild(stars);
      view.summary.appendChild(copy);
      view.summary.setAttribute('aria-label', translate('bookReviews.ratingValue').replace('{rating}', savedRating));
      view.summary.hidden = false;
    }

    function restoreSaved() {
      if (view.rating) view.rating.value = savedRating;
      (view.ratingOptions || []).forEach(function(input) {
        input.checked = input.value === savedRating;
      });
      if (view.reviewText) view.reviewText.value = savedText;
    }

    function render(target) {
      var id = 'book-review-' + (++instanceCount);
      target.replaceChildren();
      target.className = (target.className ? target.className + ' ' : '') + 'book-reviews';
      target.setAttribute('aria-labelledby', id + '-title');

      var heading = documentTarget.createElement('h2');
      heading.id = id + '-title';
      heading.textContent = translate('bookReviews.title');
      var summary = documentTarget.createElement('p');
      summary.className = 'book-review-summary';
      summary.hidden = true;

      var form = documentTarget.createElement('form');
      form.className = 'book-review-form';
      form.setAttribute('novalidate', '');
      var ratingField = documentTarget.createElement('fieldset');
      ratingField.className = 'book-review-rating';
      var legend = documentTarget.createElement('legend');
      legend.textContent = translate('bookReviews.rating');
      var options = documentTarget.createElement('div');
      options.className = 'book-review-rating-options';
      var rating = documentTarget.createElement('input');
      rating.type = 'hidden';
      rating.value = '';
      var ratingOptions = [];
      for (var value = 1; value <= 5; value++) {
        var label = documentTarget.createElement('label');
        label.className = 'book-review-star-option';
        var input = documentTarget.createElement('input');
        input.type = 'radio';
        input.name = id + '-rating';
        input.value = String(value);
        if (value === 1) input.required = true;
        input.setAttribute('aria-label', translate('bookReviews.ratingValue').replace('{rating}', String(value)));
        input.addEventListener('change', (function(selected) {
          return function() { rating.value = String(selected); };
        })(value));
        var star = documentTarget.createElement('span');
        star.setAttribute('aria-hidden', 'true');
        star.textContent = '★';
        label.appendChild(input);
        label.appendChild(star);
        options.appendChild(label);
        ratingOptions.push(input);
      }
      ratingField.appendChild(legend);
      ratingField.appendChild(options);

      var reviewLabel = documentTarget.createElement('label');
      reviewLabel.className = 'book-review-label';
      reviewLabel.setAttribute('for', id + '-text');
      reviewLabel.textContent = translate('bookReviews.review');
      var reviewText = documentTarget.createElement('textarea');
      reviewText.id = id + '-text';
      reviewText.maxLength = 10000;
      reviewText.setAttribute('maxlength', '10000');
      reviewText.setAttribute('aria-describedby', id + '-hint');
      var hint = documentTarget.createElement('p');
      hint.id = id + '-hint';
      hint.className = 'book-review-hint';
      hint.textContent = translate('bookReviews.reviewHint');

      var actions = documentTarget.createElement('div');
      actions.className = 'book-review-actions';
      var saveButton = documentTarget.createElement('button');
      saveButton.type = 'submit';
      saveButton.className = 'css-btn primary';
      saveButton.textContent = translate('bookReviews.save');
      var deleteButton = documentTarget.createElement('button');
      deleteButton.type = 'button';
      deleteButton.className = 'css-btn secondary book-review-delete';
      deleteButton.textContent = translate('bookReviews.delete');
      actions.appendChild(saveButton);
      actions.appendChild(deleteButton);

      var status = documentTarget.createElement('p');
      status.className = 'book-review-status';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      status.setAttribute('aria-atomic', 'true');

      form.appendChild(ratingField);
      form.appendChild(reviewLabel);
      form.appendChild(reviewText);
      form.appendChild(hint);
      form.appendChild(actions);
      target.appendChild(heading);
      target.appendChild(summary);
      target.appendChild(form);
      target.appendChild(status);
      view = { root: target, rating: rating, ratingOptions: ratingOptions, reviewText: reviewText, saveButton: saveButton,
        deleteButton: deleteButton, status: status, summary: summary };

      form.addEventListener('submit', function(event) {
        event.preventDefault();
        save(currentRating(), reviewText.value);
      });
      deleteButton.addEventListener('click', function() { deleteReview(); });
    }

    function applyReview(review) {
      savedRating = review && Number.isInteger(review.rating) ? String(review.rating) : '';
      savedText = review && typeof review.review_text === 'string' ? review.review_text : '';
      restoreSaved();
      updateSummary();
      if (view.deleteButton) view.deleteButton.hidden = !savedRating && !savedText;
    }

    function load() {
      return request(bookId, 'GET').then(function(payload) {
        applyReview(payload && payload.review);
        return payload && payload.review;
      }).catch(function() {
        restoreSaved();
        setStatus(translate('book.error.server_error'), true);
        return null;
      });
    }

    function save(rating, reviewText) {
      var normalizedRating = Number(rating);
      if (!Number.isInteger(normalizedRating) || normalizedRating < 1 || normalizedRating > 5) {
        restoreSaved();
        setStatus(translate('book.error.server_error'), true);
        return Promise.resolve(null);
      }
      setBusy(true);
      return request(bookId, 'PUT', { rating: normalizedRating, review_text: String(reviewText || '') })
        .then(function(payload) {
          applyReview(payload && payload.review ? payload.review : { rating: normalizedRating, review_text: String(reviewText || '') });
          setStatus(translate('bookReviews.saved'), false);
          return payload;
        }).catch(function() {
          restoreSaved();
          setStatus(translate('book.error.server_error'), true);
          return null;
        }).finally(function() { setBusy(false); });
    }

    function deleteReview() {
      if (!savedRating && !savedText) return Promise.resolve(null);
      if (typeof root.confirm === 'function' && !root.confirm(translate('bookReviews.deleteConfirm'))) return Promise.resolve(null);
      setBusy(true);
      return request(bookId, 'DELETE').then(function() {
        applyReview(null);
        setStatus(translate('bookReviews.deleted'), false);
        return true;
      }).catch(function() {
        restoreSaved();
        setStatus(translate('book.error.server_error'), true);
        return null;
      }).finally(function() { setBusy(false); });
    }

    function mount(rootElement, suppliedBookId) {
      var target = rootElement;
      if (typeof rootElement === 'string' || !rootElement) {
        suppliedBookId = rootElement || suppliedBookId;
        target = documentTarget && documentTarget.querySelector('[data-book-reviews]');
      }
      if (!target || !suppliedBookId) return Promise.resolve(null);
      bookId = String(suppliedBookId);
      render(target);
      return load();
    }

    return {
      mount: mount,
      save: save,
      deleteReview: deleteReview,
      get rating() { return view.rating; },
      get ratingOptions() { return view.ratingOptions || []; },
      get reviewText() { return view.reviewText; }
    };
  }

  var defaultClient = createClient();
  return {
    mount: function(rootElement, bookId) { return defaultClient.mount(rootElement, bookId); },
    create: function() { return createClient(); }
  };
});
