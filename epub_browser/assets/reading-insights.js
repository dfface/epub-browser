(function(root, factory) {
  var api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.EpubReadingInsights = api;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  function translate(target, key, fallback) {
    var i18n = target.EpubBrowserI18n;
    var value = i18n && typeof i18n.t === 'function' ? i18n.t(key) : '';
    return value && value !== key ? value : fallback;
  }

  function localIsoDate(value) {
    var date = value instanceof Date ? value : new Date(value || Date.now());
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
  }

  function endpoint(target, period, anchor, timezone) {
    var path = '/api/reading-insights?period=' + encodeURIComponent(period) +
      '&anchor=' + encodeURIComponent(anchor) + '&timezone=' + encodeURIComponent(timezone);
    return target.EpubBrowserURL && typeof target.EpubBrowserURL.publicPath === 'function'
      ? target.EpubBrowserURL.publicPath(path) : path;
  }

  function createClient(target) {
    var documentTarget = target.document;
    var state = {
      period: 'week',
      anchor: localIsoDate(),
      timezone: 'UTC',
      insights: null,
      selectedDay: '',
      loading: false,
      root: null,
      view: {}
    };

    function intl() { return target.Intl || Intl; }

    function locale() {
      var i18n = target.EpubBrowserI18n;
      return i18n && typeof i18n.getLocale === 'function' ? i18n.getLocale() : undefined;
    }

    function formatDuration(seconds) {
      var value = Math.max(0, Number(seconds) || 0);
      if (intl().DurationFormat) {
        try {
          return new intl().DurationFormat(locale(), { style: 'narrow' }).format({
            hours: Math.floor(value / 3600), minutes: Math.floor(value % 3600 / 60), seconds: value % 60
          });
        } catch (error) {}
      }
      if (value < 60) return Math.floor(value) + ' sec';
      var hours = Math.floor(value / 3600);
      var minutes = Math.floor(value % 3600 / 60);
      return hours ? hours + ' hr' + (minutes ? ' ' + minutes + ' min' : '') : minutes + ' min';
    }

    function formatTime(value) {
      try {
        return new intl().DateTimeFormat(locale(), {
          hour: '2-digit', minute: '2-digit', timeZone: state.timezone
        }).format(new Date(value));
      } catch (error) {
        return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
    }

    function sessionDate(value) {
      var date = new Date(value);
      try {
        var parts = new intl().DateTimeFormat('en-CA', {
          timeZone: state.timezone, year: 'numeric', month: '2-digit', day: '2-digit'
        }).formatToParts(date);
        var values = {};
        parts.forEach(function(part) { values[part.type] = part.value; });
        if (values.year && values.month && values.day) return values.year + '-' + values.month + '-' + values.day;
      } catch (error) {}
      return localIsoDate(date);
    }

    function append(parent, tag, className, text) {
      var item = documentTarget.createElement(tag);
      if (className) item.className = className;
      if (text !== undefined) item.textContent = text;
      parent.appendChild(item);
      return item;
    }

    function setBusy(busy) {
      state.loading = busy;
      if (state.root) state.root.setAttribute('aria-busy', busy ? 'true' : 'false');
      (state.view.periodButtons || []).forEach(function(button) { button.disabled = busy; });
      (state.view.dayButtons || []).forEach(function(button) { button.disabled = busy; });
    }

    function setLive(message) {
      if (state.view.live) state.view.live.textContent = message;
    }

    function build(targetRoot) {
      targetRoot.replaceChildren();
      targetRoot.className = 'reading-insights-page';
      targetRoot.setAttribute('tabindex', '-1');
      targetRoot.setAttribute('aria-labelledby', 'readingInsightsTitle');

      var heading = append(targetRoot, 'section', 'reading-insights-heading');
      append(heading, 'p', 'reading-insights-kicker', translate(target, 'readingInsights.privateKicker', 'Private to your account'));
      var title = append(heading, 'h1', '', translate(target, 'readingInsights.title', 'Reading insights'));
      title.id = 'readingInsightsTitle';
      append(heading, 'p', '', translate(target, 'readingInsights.intro', 'See when you actively read and where your time went.'));

      var periods = append(targetRoot, 'section', 'reading-insights-periods');
      periods.setAttribute('aria-label', translate(target, 'readingInsights.periodLabel', 'Reading period'));
      var periodButtons = ['day', 'week', 'month'].map(function(period) {
        var button = append(periods, 'button', '', translate(target, 'readingInsights.period.' + period, period.charAt(0).toUpperCase() + period.slice(1)));
        button.type = 'button';
        button.setAttribute('data-reading-insights-period', period);
        button.setAttribute('aria-pressed', period === state.period ? 'true' : 'false');
        button.addEventListener('click', function() { setPeriod(period); });
        return button;
      });
      var live = append(targetRoot, 'p', 'reading-insights-live', translate(target, 'readingInsights.loading', 'Loading reading insights…'));
      live.setAttribute('role', 'status'); live.setAttribute('aria-live', 'polite'); live.setAttribute('aria-atomic', 'true');
      var summary = append(targetRoot, 'section', 'reading-insights-summary');
      summary.setAttribute('aria-label', translate(target, 'readingInsights.summaryLabel', 'Reading summary'));
      var totalCard = append(summary, 'article', 'reading-insights-summary-card');
      append(totalCard, 'p', '', translate(target, 'readingInsights.total', 'Active reading'));
      var total = append(totalCard, 'strong', '', '—');
      var bookCard = append(summary, 'article', 'reading-insights-summary-card');
      append(bookCard, 'p', '', translate(target, 'readingInsights.topBook', 'Top book'));
      var topBook = append(bookCard, 'strong', '', '—');
      var days = append(targetRoot, 'section', 'reading-insights-days');
      var daysTitle = append(days, 'h2', '', translate(target, 'readingInsights.days', 'Days'));
      daysTitle.id = 'readingInsightsDaysTitle';
      days.setAttribute('aria-labelledby', daysTitle.id);
      var dayList = append(days, 'div', 'reading-insights-day-list');
      var sessions = append(targetRoot, 'section', 'reading-insights-sessions');
      var selectedDay = append(sessions, 'h2', '', translate(target, 'readingInsights.selectedDay', 'Selected day'));
      selectedDay.id = 'readingInsightsSelectedDay';
      sessions.setAttribute('aria-labelledby', selectedDay.id);
      var sessionList = append(sessions, 'ol', 'reading-insights-session-list');
      state.view = { periodButtons: periodButtons, live: live, total: total, topBook: topBook, dayList: dayList, selectedDay: selectedDay, sessionList: sessionList, dayButtons: [] };
    }

    function renderSessions() {
      var sessions = state.insights && Array.isArray(state.insights.sessions) ? state.insights.sessions : [];
      var matching = sessions.filter(function(session) { return sessionDate(session.started_at) === state.selectedDay; })
        .sort(function(left, right) { return new Date(left.started_at) - new Date(right.started_at); });
      state.view.sessionList.replaceChildren();
      if (!matching.length) {
        append(state.view.sessionList, 'li', 'reading-insights-empty', translate(target, 'readingInsights.emptyDay', 'No active reading recorded for this day.'));
        return;
      }
      matching.forEach(function(session) {
        append(
          state.view.sessionList,
          'li',
          'reading-insights-session',
          [formatTime(session.started_at), session.book_title || translate(target, 'readingInsights.unknownBook', 'Unknown book'), session.chapter_label || translate(target, 'readingInsights.unknownChapter', 'Unknown chapter'), formatDuration(session.active_seconds)].join(' ')
        );
      });
    }

    function renderInsights() {
      var insights = state.insights || {};
      var days = Array.isArray(insights.days) ? insights.days : [];
      if (!state.selectedDay || !days.some(function(day) { return day.date === state.selectedDay; })) {
        state.selectedDay = days.length ? days[days.length - 1].date : state.anchor;
      }
      state.view.total.textContent = formatDuration(insights.total_active_seconds);
      state.view.topBook.textContent = insights.top_book
        ? insights.top_book.title + ' · ' + formatDuration(insights.top_book.active_seconds) : '—';
      state.view.dayList.replaceChildren();
      state.view.dayButtons = days.map(function(day) {
        var button = append(state.view.dayList, 'button', 'reading-insights-day-button');
        button.type = 'button';
        button.setAttribute('aria-pressed', day.date === state.selectedDay ? 'true' : 'false');
        button.setAttribute('aria-label', day.date + ': ' + formatDuration(day.active_seconds));
        button.textContent = day.date + ' ' + formatDuration(day.active_seconds);
        button.addEventListener('click', function() { selectDay(day.date); });
        return button;
      });
      state.view.selectedDay.textContent = state.selectedDay || translate(target, 'readingInsights.selectedDay', 'Selected day');
      renderSessions();
      setLive(days.length ? translate(target, 'readingInsights.loaded', 'Reading insights updated.') : translate(target, 'readingInsights.empty', 'No active reading recorded yet.'));
    }

    function load() {
      if (!target.EpubBrowserAuth || typeof target.EpubBrowserAuth.fetch !== 'function') {
        setLive(translate(target, 'readingInsights.error', 'Unable to load reading insights. Please try again.'));
        return Promise.resolve(null);
      }
      setBusy(true);
      setLive(translate(target, 'readingInsights.loading', 'Loading reading insights…'));
      return Promise.resolve(target.EpubBrowserAuth.fetch(endpoint(target, state.period, state.anchor, state.timezone), { method: 'GET' }))
        .then(function(response) {
          if (!response || !response.ok) throw new Error('reading_insights_request_failed');
          return response.json();
        })
        .then(function(payload) {
          state.insights = payload && payload.insights ? payload.insights : {};
          renderInsights();
          return state.insights;
        })
        .catch(function() {
          setLive(translate(target, 'readingInsights.error', 'Unable to load reading insights. Please try again.'));
          return null;
        })
        .finally(function() { setBusy(false); });
    }

    function selectDay(day) {
      if (!day || day === state.selectedDay) return Promise.resolve(state.insights);
      state.selectedDay = day;
      renderInsights();
      return Promise.resolve(state.insights);
    }

    function setPeriod(period, anchor) {
      if (!['day', 'week', 'month'].includes(period)) return Promise.resolve(null);
      if (period === state.period && (!anchor || anchor === state.anchor)) return Promise.resolve(state.insights);
      state.period = period;
      state.anchor = anchor || localIsoDate();
      state.selectedDay = '';
      return load();
    }

    function mount(targetRoot) {
      state.root = targetRoot || (documentTarget && documentTarget.querySelector('[data-reading-insights]'));
      if (!state.root) return Promise.resolve(null);
      try {
        state.timezone = intl().DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      } catch (error) { state.timezone = 'UTC'; }
      build(state.root);
      var i18n = target.EpubBrowserI18n;
      if (i18n && typeof i18n.onLocaleChange === 'function') {
        i18n.onLocaleChange(function() { if (state.root) { build(state.root); renderInsights(); } });
      }
      return load();
    }

    return { mount: mount, selectDay: selectDay, setPeriod: setPeriod, load: load, get sessionRows() { return state.view.sessionList ? state.view.sessionList.children : []; } };
  }

  var defaultClient = null;
  return {
    create: createClient,
    mount: function(target) {
      defaultClient = defaultClient || createClient(root);
      return defaultClient.mount(target);
    }
  };
});
