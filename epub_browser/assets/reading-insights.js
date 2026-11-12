(function(root, factory) {
  var api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.EpubReadingInsights = api;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  function translate(target, key, fallback, params) {
    var i18n = target.EpubBrowserI18n;
    var value = i18n && typeof i18n.t === 'function' ? i18n.t(key, params) : '';
    return value && value !== key ? value : fallback;
  }

  function localIsoDate(value) {
    var date = value instanceof Date ? value : new Date(value || Date.now());
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
  }

  function utcIsoDate(value) {
    var date = value instanceof Date ? value : new Date(value);
    return [date.getUTCFullYear(), String(date.getUTCMonth() + 1).padStart(2, '0'), String(date.getUTCDate()).padStart(2, '0')].join('-');
  }

  function publicPath(target, path) {
    return target.EpubBrowserURL && typeof target.EpubBrowserURL.publicPath === 'function'
      ? target.EpubBrowserURL.publicPath(path) : path;
  }

  function chapterPath(target, bookId, chapterIndex) {
    var path = '/book/' + encodeURIComponent(bookId) + '/chapter_' + encodeURIComponent(chapterIndex) + '.html';
    return target.EpubBrowserURL && typeof target.EpubBrowserURL.publicPath === 'function'
      ? target.EpubBrowserURL.publicPath(path) : path;
  }

  function createClient(target) {
    var documentTarget = target.document;
    var state = {
      period: 'overview',
      anchor: localIsoDate(),
      timezone: 'UTC',
      insights: null,
      bookId: '',
      book: null,
      bookOrigin: null,
      sessions: null,
      sessionPage: 1,
      reportStatus: '',
      sessionStatus: '',
      request: null,
      tooltipTimer: null,
      selectedDay: '',
      root: null,
      view: {},
      modal: null,
      container: null,
      closeButton: null,
      opener: null,
      scrollY: 0,
      localeBound: false,
      activityMetric: 'duration'
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
      if (value < 60) return Math.floor(value) + ' ' + translate(target, 'readingInsights.duration.second', 'sec');
      var hours = Math.floor(value / 3600);
      var minutes = Math.floor(value % 3600 / 60);
      var hour = translate(target, 'readingInsights.duration.hour', 'hr');
      var minute = translate(target, 'readingInsights.duration.minute', 'min');
      return hours ? hours + ' ' + hour + (minutes ? ' ' + minutes + ' ' + minute : '') : minutes + ' ' + minute;
    }

    function durationTone(seconds) {
      var value = Math.max(0, Number(seconds) || 0);
      if (value < 60) return 'glance';
      if (value < 15 * 60) return 'light';
      if (value < 60 * 60) return 'focused';
      return 'deep';
    }

    function activityTone(seconds) {
      var value = Math.max(0, Number(seconds) || 0);
      if (!value) return 0;
      // These are deliberate, stable session-length bands rather than a
      // data-relative scale. A colour must mean the same thing every time a
      // reader opens a different year or changes their reading history.
      if (value < 5 * 60) return 1;
      if (value < 20 * 60) return 2;
      if (value < 60 * 60) return 3;
      return 4;
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

    function formatDay(value) {
      try {
        return new intl().DateTimeFormat(locale(), {
          weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'
        }).format(new Date(value + 'T12:00:00Z'));
      } catch (error) {
        return value;
      }
    }

    function formatDayShort(value) {
      try {
        return new intl().DateTimeFormat(locale(), {
          weekday: 'short', timeZone: 'UTC'
        }).format(new Date(value + 'T12:00:00Z'));
      } catch (error) {
        return value;
      }
    }

    function formatDayNumber(value) {
      try {
        return new intl().DateTimeFormat(locale(), {
          day: 'numeric', month: 'numeric', timeZone: 'UTC'
        }).format(new Date(value + 'T12:00:00Z'));
      } catch (error) {
        return value;
      }
    }

    function formatTrendBucket(bucket, granularity) {
      if (granularity === 'month') {
        try {
          return new intl().DateTimeFormat(locale(), { month: 'short', timeZone: 'UTC' }).format(new Date(bucket + '-01T12:00:00Z'));
        } catch (error) { return bucket; }
      }
      if (granularity === 'day') return formatDayNumber(bucket);
      var hour = Math.max(0, Math.min(23, Number(bucket) || 0));
      try {
        return new intl().DateTimeFormat(locale(), { hour: 'numeric', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, 0, 1, hour)));
      } catch (error) { return hour + ':00'; }
    }

    function trendScaleMaximum(value, metric) {
      var raw = Math.max(1, Number(value) || 0);
      if (metric === 'book_count') return Math.max(1, Math.ceil(raw));
      var steps = [10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 28800, 43200, 86400];
      for (var index = 0; index < steps.length; index += 1) {
        if (raw <= steps[index]) return steps[index];
      }
      return Math.ceil(raw / 86400) * 86400;
    }

    function selectedDayLabel(value) {
      return value === localIsoDate()
        ? translate(target, 'readingInsights.today', 'Today')
        : formatDay(value);
    }

    function append(parent, tag, className, text) {
      var item = documentTarget.createElement(tag);
      if (className) item.className = className;
      if (text !== undefined) item.textContent = text;
      parent.appendChild(item);
      return item;
    }

    function hideTooltip() {
      clearTimeout(state.tooltipTimer);
      if (state.view.tooltip) state.view.tooltip.hidden = true;
    }

    function deferTooltipHide() {
      clearTimeout(state.tooltipTimer);
      state.tooltipTimer = setTimeout(hideTooltip, 220);
    }

    function attachTooltip(trigger, label) {
      trigger.addEventListener('mouseenter', show);
      trigger.addEventListener('focus', show);
      trigger.addEventListener('mouseleave', deferTooltipHide);
      trigger.addEventListener('blur', deferTooltipHide);
      function show() {
        var tooltip = state.view.tooltip;
        if (!tooltip) return;
        clearTimeout(state.tooltipTimer);
        tooltip.textContent = label;
        tooltip.hidden = false;
        if (!trigger.getBoundingClientRect || !tooltip.style) return;
        var rect = trigger.getBoundingClientRect();
        var half = tooltip.offsetWidth / 2;
        var left = Math.min(target.innerWidth - half - 8, Math.max(half + 8, rect.left + rect.width / 2));
        var headerBottom = state.modal?.querySelector('.reading-insights-modal-header').getBoundingClientRect().bottom || 0;
        var below = rect.top - tooltip.offsetHeight - 6 < headerBottom;
        tooltip.classList.toggle('is-below', below);
        tooltip.style.left = Math.round(left) + 'px';
        tooltip.style.top = Math.round(below ? rect.bottom : rect.top) + 'px';
      }
    }

    function arrowNavigation(items, initial, columnStep) {
      items.forEach(function(item, index) {
        item.setAttribute('tabindex', index === initial ? '0' : '-1');
        item.addEventListener('focus', function() {
          items[initial].setAttribute('tabindex', '-1');
          item.setAttribute('tabindex', '0');
          initial = index;
        });
        item.addEventListener('keydown', function(event) {
          var rtl = target.getComputedStyle?.(item).direction === 'rtl';
          var next = {
            ArrowLeft: index + (rtl ? columnStep : -columnStep),
            ArrowRight: index + (rtl ? -columnStep : columnStep),
            ArrowUp: index - 1,
            ArrowDown: index + 1,
            Home: 0,
            End: items.length - 1
          }[event.key];
          if (next === undefined) return;
          event.preventDefault();
          items[Math.max(0, Math.min(items.length - 1, next))].focus();
        });
      });
    }

    function statusPanel(parent, retry) {
      var panel = append(parent, 'div', 'reading-insights-status');
      var message = append(panel, 'p', '');
      message.setAttribute('role', 'status');
      var button = append(panel, 'button', 'reading-insights-action', translate(target, 'readingInsights.retry', 'Retry'));
      button.type = 'button';
      button.hidden = true;
      button.addEventListener('click', function() {
        if (state.root.focus) state.root.focus({ preventScroll: true });
        retry();
      });
      return { message: message, retry: button };
    }

    function renderStatus(panel, status) {
      var message = status === 'loading'
        ? translate(target, 'readingInsights.loading', 'Loading reading insights…')
        : status === 'error'
          ? translate(target, 'readingInsights.error', 'Unable to load reading insights. Please try again.')
          : '';
      panel.message.textContent = message;
      panel.retry.hidden = status !== 'error';
    }

    function bookButton(parent, className, label, bookId, source) {
      var button = append(parent, 'button', className, label);
      button.type = 'button';
      button.addEventListener('click', function() {
        state.bookOrigin = { bookId: bookId, source: source };
        showBook(bookId);
      });
      state.view.bookButtons[source + ':' + bookId] = button;
      return button;
    }

    function periodLabel(period) {
      return translate(target, 'readingInsights.period.' + period, period.charAt(0).toUpperCase() + period.slice(1));
    }

    function dateRange(period, anchor) {
      var anchorDate = new Date(anchor + 'T12:00:00Z');
      if (period === 'overview') {
        return [
          new Date(Date.UTC(anchorDate.getUTCFullYear(), 0, 1, 12)),
          new Date(Date.UTC(anchorDate.getUTCFullYear(), 11, 31, 12))
        ];
      }
      if (period === 'day') return [anchorDate, anchorDate];
      if (period === 'week') {
        var mondayOffset = (anchorDate.getUTCDay() + 6) % 7;
        var weekStart = new Date(anchorDate);
        weekStart.setUTCDate(weekStart.getUTCDate() - mondayOffset);
        var weekEnd = new Date(weekStart);
        weekEnd.setUTCDate(weekEnd.getUTCDate() + 6);
        return [weekStart, weekEnd];
      }
      var monthStart = new Date(Date.UTC(anchorDate.getUTCFullYear(), anchorDate.getUTCMonth(), 1, 12));
      var monthEnd = new Date(Date.UTC(anchorDate.getUTCFullYear(), anchorDate.getUTCMonth() + 1, 0, 12));
      return [monthStart, monthEnd];
    }

    function formatDateRange(period, anchor) {
      var dates = dateRange(period, anchor);
      try {
        var formatter = new intl().DateTimeFormat(locale(), {
          day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'
        });
        if (dates[0].getTime() === dates[1].getTime()) return formatter.format(dates[0]);
        if (typeof formatter.formatRange === 'function') return formatter.formatRange(dates[0], dates[1]);
        return formatter.format(dates[0]) + '–' + formatter.format(dates[1]);
      } catch (error) {
        return dates[0].toISOString().slice(0, 10) + (dates[0].getTime() === dates[1].getTime() ? '' : '–' + dates[1].toISOString().slice(0, 10));
      }
    }

    function updatePeriodControls() {
      (state.view.periodButtons || []).forEach(function(button) {
        button.setAttribute(
          'aria-pressed',
          button.getAttribute('data-reading-insights-period') === state.period ? 'true' : 'false'
        );
      });
    }

    function updateRangeControls() {
      if (state.view.rangeLabel) {
        state.view.rangeLabel.textContent = formatDateRange(state.period, state.anchor);
      }
      if (state.view.previousRange) state.view.previousRange.setAttribute('aria-label', translate(target, 'readingInsights.previousRange', 'Previous range'));
      if (state.view.nextRange) state.view.nextRange.setAttribute('aria-label', translate(target, 'readingInsights.nextRange', 'Next range'));
      if (state.view.nextRange) state.view.nextRange.disabled = shiftAnchor(state.anchor, state.period, 1) > localIsoDate();
      if (state.view.todayRange) state.view.todayRange.hidden = state.anchor === localIsoDate();
    }

    function build(targetRoot) {
      hideTooltip();
      targetRoot.replaceChildren();
      targetRoot.className = 'reading-insights-page';
      targetRoot.setAttribute('tabindex', '-1');
      targetRoot.setAttribute('aria-labelledby', 'readingInsightsTitle');
      if (state.modal) {
        state.modal.querySelector('.reading-insights-header-label span').textContent = translate(target, 'readingInsights.navigation', 'Reading insights');
        state.modal.classList.toggle('is-book', Boolean(state.bookId));
        state.backButton.hidden = !state.bookId || !canReturnToTime();
        state.backButton.querySelector('span').textContent = translate(target, 'readingInsights.backToOverview', 'Back to reading insights');
        state.closeButton.setAttribute('aria-label', translate(target, 'readingInsights.close', 'Close'));
      }

      if (state.bookId) {
        buildBook(targetRoot);
        return;
      }

      var title = append(targetRoot, 'h1', 'reading-insights-visually-hidden', translate(target, 'readingInsights.title', 'Reading insights'));
      title.id = 'readingInsightsTitle';

      var controls = append(targetRoot, 'section', 'reading-insights-controls');
      var periods = append(controls, 'div', 'reading-insights-periods');
      periods.setAttribute('aria-label', translate(target, 'readingInsights.periodLabel', 'Reading period'));
      var periodButtons = ['overview', 'day', 'week', 'month'].map(function(period) {
        var button = append(periods, 'button', '', periodLabel(period));
        button.type = 'button';
        button.setAttribute('data-reading-insights-period', period);
        button.setAttribute('aria-pressed', period === state.period ? 'true' : 'false');
        button.addEventListener('click', function() { setPeriod(period); });
        return button;
      });
      var range = append(controls, 'nav', 'reading-insights-range');
      range.setAttribute('aria-label', translate(target, 'readingInsights.rangeLabel', 'Reading range'));
      var previousRange = append(range, 'button', 'reading-insights-range-button');
      previousRange.type = 'button';
      previousRange.setAttribute('data-reading-insights-previous', '');
      previousRange.innerHTML = '<i class="fas fa-chevron-left" aria-hidden="true"></i>';
      previousRange.addEventListener('click', function() { previousRangeForPeriod(); });
      var rangeLabel = append(range, 'p', 'reading-insights-range-label');
      rangeLabel.setAttribute('aria-live', 'polite'); rangeLabel.setAttribute('aria-atomic', 'true');
      var todayRange = append(range, 'button', 'reading-insights-today', translate(target, 'readingInsights.today', 'Today'));
      todayRange.type = 'button';
      todayRange.addEventListener('click', function() { setPeriod(state.period, localIsoDate()); });
      var nextRange = append(range, 'button', 'reading-insights-range-button');
      nextRange.type = 'button';
      nextRange.setAttribute('data-reading-insights-next', '');
      nextRange.innerHTML = '<i class="fas fa-chevron-right" aria-hidden="true"></i>';
      nextRange.addEventListener('click', function() { nextRangeForPeriod(); });
      var status = statusPanel(targetRoot, load);
      var tooltip = append(targetRoot, 'div', 'reading-insights-tooltip');
      tooltip.id = 'readingInsightsTooltip';
      tooltip.setAttribute('role', 'tooltip');
      tooltip.hidden = true;
      tooltip.addEventListener('mouseenter', function() { clearTimeout(state.tooltipTimer); });
      tooltip.addEventListener('mouseleave', deferTooltipHide);
      var summary = append(targetRoot, 'section', 'reading-insights-summary');
      summary.setAttribute('aria-label', translate(target, 'readingInsights.summaryLabel', 'Reading summary'));
      var totalCard = append(summary, 'article', 'reading-insights-summary-card');
      append(totalCard, 'p', '', translate(target, 'readingInsights.total', 'Active reading'));
      var total = append(totalCard, 'strong', '', '—');
      var bookCard = append(summary, 'article', 'reading-insights-summary-card');
      append(bookCard, 'p', '', translate(target, 'readingInsights.topBook', 'Top book'));
      var topBook = append(bookCard, 'div', '');
      var books = append(targetRoot, 'section', 'reading-insights-rank');
      append(books, 'h2', 'reading-insights-card-title', translate(target, 'readingInsights.rankedBooks', 'Top books by reading time'));
      var bookList = append(books, 'ol', 'reading-insights-book-list');
      bookList.setAttribute('role', 'list');
      var analytics = append(targetRoot, 'div', 'reading-insights-analytics');
      var analyticsGrid = append(analytics, 'div', 'reading-insights-analytics-grid');
      var heatmapCard = append(analyticsGrid, 'article', 'reading-insights-analytics-card reading-insights-heatmap-card');
      append(heatmapCard, 'h2', 'reading-insights-card-title', translate(target, 'readingInsights.activityHeatmap', 'Activity calendar'));
      var calendarHint = append(heatmapCard, 'p', 'reading-insights-card-hint',
        translate(target, 'readingInsights.calendarHint', 'Select a square to view that day’s reading activity.'));
      calendarHint.id = 'readingInsightsCalendarHint';
      var heatmapScroll = append(heatmapCard, 'div', 'reading-insights-heatmap-scroll');
      heatmapScroll.setAttribute('aria-label', translate(target, 'readingInsights.activityHeatmap', 'Activity calendar'));
      var heatmapMonths = append(heatmapScroll, 'div', 'reading-insights-heatmap-months');
      heatmapMonths.setAttribute('aria-hidden', 'true');
      var heatmap = append(heatmapScroll, 'div', 'reading-insights-heatmap');
      heatmap.setAttribute('role', 'group');
      heatmap.setAttribute('aria-describedby', calendarHint.id);
      heatmap.setAttribute('aria-label', translate(target, 'readingInsights.activityHeatmap', 'Activity calendar'));
      var legend = append(heatmapCard, 'div', 'reading-insights-heatmap-legend');
      append(legend, 'span', '', translate(target, 'readingInsights.activityLess', 'Less'));
      var legendScale = append(legend, 'span', 'reading-insights-heatmap-legend-scale');
      [0, 1, 2, 3, 4].forEach(function(level) { append(legendScale, 'i', 'is-level-' + level); });
      append(legend, 'span', '', translate(target, 'readingInsights.activityMore', 'More'));
      var activityScale = translate(
        target,
        'readingInsights.activityScale',
        'Color reflects active reading per day: under 5 minutes, 5–20 minutes, 20–60 minutes, and 1 hour or more.'
      );
      var activityInfo = append(legend, 'button', 'reading-insights-activity-info');
      activityInfo.type = 'button';
      activityInfo.setAttribute('aria-label', activityScale);
      activityInfo.innerHTML = '<i class="fas fa-circle-info" aria-hidden="true"></i>';
      attachTooltip(activityInfo, activityScale);
      var trendCard = append(analyticsGrid, 'article', 'reading-insights-analytics-card reading-insights-trend-card');
      var trendTitle = append(trendCard, 'h2', 'reading-insights-card-title');
      var metricButtons = ['duration', 'books'].map(function(metric) {
        var key = metric === 'duration' ? 'readingInsights.trend.duration' : 'readingInsights.trend.books';
        var fallback = metric === 'duration' ? 'Reading time' : 'Books read';
        var button = append(trendCard, 'button', 'reading-insights-metric-button', translate(target, key, fallback));
        button.type = 'button';
        button.setAttribute('data-reading-insights-metric', metric);
        button.setAttribute('aria-pressed', metric === state.activityMetric ? 'true' : 'false');
        button.addEventListener('click', function() {
          if (state.activityMetric === metric) return;
          state.activityMetric = metric;
          renderActivity();
        });
        return button;
      });
      var trendAxis = append(trendCard, 'div', 'reading-insights-trend-axis');
      var trendYAxis = append(trendAxis, 'div', 'reading-insights-trend-y-axis');
      var trendChart = append(trendAxis, 'div', 'reading-insights-trend-chart');
      trendChart.setAttribute('role', 'group');
      var trendXAxis = append(trendCard, 'div', 'reading-insights-trend-x-axis');
      var trendValue = append(trendCard, 'p', 'reading-insights-trend-value', '—');
      var days = append(targetRoot, 'section', 'reading-insights-days');
      var daysTitle = append(days, 'h2', 'reading-insights-card-title', translate(target, 'readingInsights.days', 'Days'));
      daysTitle.id = 'readingInsightsDaysTitle';
      days.setAttribute('aria-labelledby', daysTitle.id);
      var dayList = append(days, 'div', 'reading-insights-day-list');
      var sessions = append(days, 'section', 'reading-insights-session-detail');
      var sessionHeading = append(sessions, 'div', 'reading-insights-session-heading');
      var selectedDay = append(sessionHeading, 'h2', 'reading-insights-card-title', translate(target, 'readingInsights.selectedDay', 'Selected day'));
      var selectedDuration = append(sessionHeading, 'span', 'reading-insights-selected-duration');
      selectedDay.id = 'readingInsightsSelectedDay';
      selectedDay.setAttribute('tabindex', '-1');
      sessions.setAttribute('aria-labelledby', selectedDay.id);
      var sessionStatus = statusPanel(sessions, function() { return loadSessions(state.sessionPage); });
      var sessionList = append(sessions, 'ol', 'reading-insights-session-list');
      var pagination = append(sessions, 'div', 'reading-insights-range');
      var previousSessions = append(pagination, 'button', '', translate(target, 'readingInsights.previousSessions', 'Previous sessions'));
      var nextSessions = append(pagination, 'button', '', translate(target, 'readingInsights.nextSessions', 'Next sessions'));
      previousSessions.type = nextSessions.type = 'button';
      function changeSessionPage(step) {
        if (selectedDay.focus) selectedDay.focus();
        loadSessions(state.sessionPage + step);
      }
      previousSessions.addEventListener('click', function() { changeSessionPage(-1); });
      nextSessions.addEventListener('click', function() { changeSessionPage(1); });
      state.view = { periodButtons: periodButtons, previousRange: previousRange, nextRange: nextRange, todayRange: todayRange, rangeLabel: rangeLabel, status: status, summary: summary, tooltip: tooltip, total: total, topBook: topBook, analytics: analytics, heatmapCard: heatmapCard, heatmap: heatmap, heatmapMonths: heatmapMonths, heatmapScroll: heatmapScroll, trendChart: trendChart, trendValue: trendValue, trendTitle: trendTitle, trendYAxis: trendYAxis, trendXAxis: trendXAxis, metricButtons: metricButtons, days: days, daysTitle: daysTitle, dayList: dayList, selectedDay: selectedDay, selectedDuration: selectedDuration, sessions: sessions, sessionList: sessionList, sessionStatus: sessionStatus, previousSessions: previousSessions, nextSessions: nextSessions, books: books, bookList: bookList, bookButtons: {}, dayButtons: [] };
      updatePeriodControls();
      updateRangeControls();
    }

    function renderSessions() {
      var payload = state.sessions;
      renderStatus(state.view.sessionStatus, state.sessionStatus);
      state.view.previousSessions.hidden = !payload || state.sessionPage <= 1;
      state.view.nextSessions.hidden = !payload || !payload.has_more;
      state.view.sessionList.replaceChildren();
      if (!payload) return;
      var matching = payload.sessions;
      if (!matching.length) {
        append(state.view.sessionList, 'li', 'reading-insights-empty', translate(target, 'readingInsights.emptyDay', 'No active reading recorded for this day.'));
        return;
      }
      matching.forEach(function(session, index) {
        var time = formatTime(session.started_at);
        var book = session.book_title || translate(target, 'readingInsights.unknownBook', 'Unknown book');
        var chapter = session.chapter_label || translate(target, 'readingInsights.unknownChapter', 'Unknown chapter');
        var duration = formatDuration(session.active_seconds);
        var item = append(state.view.sessionList, 'li', 'reading-insights-session');
        item.setAttribute('aria-label', [time, book, chapter, duration].join(' '));
        append(item, 'time', 'reading-insights-session-time', time);
        var details = append(item, 'span', 'reading-insights-session-details');
        if (session.book_id) {
          bookButton(details, 'reading-insights-session-book reading-insights-text-button', book, session.book_id, 'session-' + index);
        } else {
          append(details, 'span', 'reading-insights-session-book', book);
        }
        var chapterLink = append(details, 'a', 'reading-insights-session-chapter', chapter);
        if (session.book_id && Number.isInteger(session.chapter_index) && session.chapter_index >= 0) {
          chapterLink.setAttribute('href', chapterPath(target, session.book_id, session.chapter_index));
        } else chapterLink.removeAttribute('href');
        append(item, 'span', 'reading-insights-session-duration is-' + durationTone(session.active_seconds), duration);
      });
    }

    function renderActivity() {
      hideTooltip();
      var activity = state.insights && state.insights.activity;
      var days = activity && Array.isArray(activity.days) ? activity.days : [];
      var metric = state.activityMetric === 'books' ? 'book_count' : 'active_seconds';
      if (state.view.heatmap) {
        state.view.heatmap.replaceChildren();
        if (state.view.heatmapMonths) state.view.heatmapMonths.replaceChildren();
        if (days.length) {
          var first = new Date(days[0].date + 'T12:00:00Z');
          var leadingDays = (first.getUTCDay() + 6) % 7;
          var weeks = Math.ceil((leadingDays + days.length) / 7);
          var monthLabels = {};
          days.forEach(function(day, index) {
            var date = new Date(day.date + 'T12:00:00Z');
            if (index === 0 || date.getUTCDate() === 1) {
              var column = Math.floor((leadingDays + index) / 7);
              try {
                monthLabels[column] = new intl().DateTimeFormat(locale(), { month: 'short', timeZone: 'UTC' }).format(date);
              } catch (error) { monthLabels[column] = day.date.slice(5, 7); }
            }
          });
          if (state.view.heatmapMonths) {
            state.view.heatmapMonths.setAttribute('style', '--reading-insights-heatmap-weeks:' + weeks);
            for (var week = 0; week < weeks; week += 1) append(state.view.heatmapMonths, 'span', '', monthLabels[week] || '');
          }
          for (var index = 0; index < leadingDays; index += 1) append(state.view.heatmap, 'span', 'reading-insights-heatmap-spacer');
        }
        var recent = days.findLastIndex(function(day) { return day.date <= localIsoDate(); });
        var cells = days.map(function(day) {
          var seconds = Math.max(0, Number(day.active_seconds) || 0);
          var count = Math.max(0, Number(day.book_count) || 0);
          var label = formatDay(day.date) + ': ' + formatDuration(seconds) + '. ' + translate(
            target,
            'readingInsights.booksRead',
            'Books read: ' + count,
            { count: count }
          );
          var cell = append(state.view.heatmap, 'button', 'reading-insights-heatmap-cell is-level-' + activityTone(seconds));
          cell.type = 'button';
          cell.setAttribute('aria-label', label);
          attachTooltip(cell, label);
          cell.addEventListener('click', function() {
            if (state.root.focus) state.root.focus({ preventScroll: true });
            setPeriod('day', day.date);
          });
          return cell;
        });
        if (cells.length) {
          recent = Math.max(0, recent);
          arrowNavigation(cells, recent, 7);
          var scroller = state.view.heatmapScroll;
          if (scroller.getBoundingClientRect && scroller.scrollWidth > scroller.clientWidth) {
            var bounds = scroller.getBoundingClientRect();
            var current = cells[recent].getBoundingClientRect();
            var rtl = target.getComputedStyle(scroller).direction === 'rtl';
            scroller.scrollLeft += rtl ? current.left - bounds.left - 12 : current.right - bounds.right + 12;
          }
        }
      }
      (state.view.metricButtons || []).forEach(function(button) {
        button.hidden = state.period === 'day';
        var isSelected = button.getAttribute('data-reading-insights-metric') === state.activityMetric;
        button.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
      });
      var trend = state.insights && state.insights.trend || {};
      var trendPoints = Array.isArray(trend.points) ? trend.points : [];
      var trendGranularity = trend.granularity || 'day';
      var values = trendPoints.map(function(point) { return Math.max(0, Number(point[metric]) || 0); });
      var duration = formatDuration(state.insights?.total_active_seconds);
      var count = state.insights?.books_read_count || 0;
      var trendValueText = metric === 'active_seconds'
        ? translate(target, 'readingInsights.trendTotalDuration', 'Total reading time: ' + duration, { duration: duration })
        : translate(target, 'readingInsights.trendTotalBooks', 'Total books read: ' + count, { count: count });
      state.view.trendValue.textContent = trendValueText;
      state.view.trendValue.hidden = metric === 'active_seconds';
      var monthly = state.period === 'overview';
      var title;
      if (state.period === 'day') {
        title = translate(target, 'readingInsights.hourlyReading', 'Reading time by hour');
      } else if (metric === 'book_count') {
        title = monthly
          ? translate(target, 'readingInsights.monthlyBooks', 'Books read per month')
          : translate(target, 'readingInsights.dailyBooks', 'Books read per day');
      } else {
        title = monthly
          ? translate(target, 'readingInsights.monthlyDuration', 'Monthly reading time')
          : translate(target, 'readingInsights.dailyDuration', 'Daily reading time');
      }
      state.view.trendTitle.textContent = title;
      if (!state.view.trendChart) return;
      var maximum = trendScaleMaximum(Math.max.apply(Math, values.concat([1])), metric);
      if (state.view.trendYAxis) {
        state.view.trendYAxis.replaceChildren();
        [maximum, maximum / 2, 0].forEach(function(value) {
          if (metric === 'book_count' && !Number.isInteger(value)) return;
          var label = metric === 'active_seconds'
            ? formatDuration(Math.round(value))
            : String(value);
          append(state.view.trendYAxis, 'span', 'reading-insights-trend-y-tick', label)
            .setAttribute('style', '--reading-insights-tick-y:' + (90 - value / maximum * 75) + '%');
        });
      }
      if (state.view.trendXAxis) {
        state.view.trendXAxis.replaceChildren();
        if (trendPoints.length) {
          [0, Math.floor((trendPoints.length - 1) / 2), trendPoints.length - 1].filter(function(index, position, indices) {
            return indices.indexOf(index) === position;
          }).forEach(function(index) {
            append(state.view.trendXAxis, 'span', '', formatTrendBucket(trendPoints[index].bucket, trendGranularity));
          });
        }
      }
      state.view.trendChart.setAttribute('aria-label', title + ' · ' + trendValueText);
      state.view.trendChart.replaceChildren();
      if (!trendPoints.length || !documentTarget.createElementNS) return;
      var svg = documentTarget.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 100 40');
      svg.setAttribute('preserveAspectRatio', 'none');
      svg.setAttribute('aria-hidden', 'true');
      var points = values.map(function(value, index) {
        var x = values.length === 1 ? 50 : index * 100 / (values.length - 1);
        var y = 36 - value / maximum * 30;
        return x.toFixed(2) + ',' + y.toFixed(2);
      });
      var area = documentTarget.createElementNS('http://www.w3.org/2000/svg', 'path');
      area.setAttribute('class', 'reading-insights-trend-area');
      area.setAttribute('d', 'M ' + points.join(' L ') + ' L 100,36 L 0,36 Z');
      var line = documentTarget.createElementNS('http://www.w3.org/2000/svg', 'path');
      line.setAttribute('class', 'reading-insights-trend-line');
      line.setAttribute('d', 'M ' + points.join(' L '));
      svg.appendChild(area);
      svg.appendChild(line);
      var pointButtons = trendPoints.map(function(point, index) {
        var value = values[index];
        var x = values.length === 1 ? 50 : index * 100 / (values.length - 1);
        var y = 36 - value / maximum * 30;
        var pointValue = metric === 'active_seconds'
          ? formatDuration(value)
          : translate(target, 'readingInsights.booksRead', 'Books read: ' + value, { count: value });
        var pointLabel = formatTrendBucket(point.bucket, trendGranularity) + ': ' + pointValue;
        var hitArea = append(state.view.trendChart, 'button', 'reading-insights-trend-point-hit');
        hitArea.type = 'button';
        hitArea.setAttribute('aria-label', pointLabel);
        hitArea.setAttribute('style', '--reading-insights-point-x:' + x.toFixed(2) + '%;--reading-insights-point-y:' + (y / 40 * 100).toFixed(2) + '%');
        attachTooltip(hitArea, pointLabel);
        hitArea.addEventListener('click', function() { hitArea.focus(); });
        return hitArea;
      });
      arrowNavigation(pointButtons, 0, 1);
      state.view.trendChart.appendChild(svg);
    }

    function renderInsights() {
      renderStatus(state.view.status, state.reportStatus);
      var insights = state.insights;
      var isOverview = state.period === 'overview';
      state.view.summary.hidden = state.view.analytics.hidden = !insights;
      var hasDates = !isOverview && state.period !== 'day';
      state.view.days.hidden = !insights || isOverview;
      state.view.daysTitle.hidden = state.view.dayList.hidden = !hasDates;
      state.view.days.setAttribute('aria-labelledby', hasDates ? 'readingInsightsDaysTitle' : 'readingInsightsSelectedDay');
      state.view.sessions.hidden = !insights || isOverview;
      state.view.books.hidden = !insights || !insights.books?.length || (state.period === 'day' && insights.books.length === 1);
      if (!insights) return;

      var days = insights.days || [];
      if (!state.selectedDay) {
        var today = localIsoDate();
        state.selectedDay = days.some(function(day) { return day.date === today; })
          ? today : (days.length ? days[days.length - 1].date : state.anchor);
      }
      state.view.total.textContent = formatDuration(insights.total_active_seconds);
      state.view.topBook.replaceChildren();
      var top = insights.top_book;
      if (top) {
        renderBookRow(state.view.topBook, top, 'top');
      } else {
        append(state.view.topBook, 'strong', '', '—');
      }
      state.view.bookList.replaceChildren();
      (insights.books || []).forEach(function(book, index) {
        var row = append(state.view.bookList, 'li', '');
        renderBookRow(row, book, 'ranked', index + 1);
      });
      if (state.period === 'day') state.activityMetric = 'duration';
      state.view.heatmapCard.hidden = !isOverview;
      renderActivity();
      var isMonth = state.period === 'month';
      state.view.dayList.className = 'reading-insights-day-list ' + (isMonth ? 'is-month' : 'is-week');
      state.view.dayList.replaceChildren();
      if (isMonth && days.length) {
        for (var weekday = 1; weekday <= 7; weekday += 1) {
          append(state.view.dayList, 'span', 'reading-insights-weekday',
            formatDayShort('2024-01-0' + weekday)).setAttribute('aria-hidden', 'true');
        }
        var leading = (new Date(days[0].date + 'T12:00:00Z').getUTCDay() + 6) % 7;
        for (var blank = 0; blank < leading; blank += 1) append(state.view.dayList, 'span', '');
      }
      state.view.dayButtons = days.map(function(day) {
        var button = append(state.view.dayList, 'button', 'reading-insights-day-button');
        button.type = 'button';
        button.setAttribute('data-date', day.date);
        button.setAttribute('aria-pressed', day.date === state.selectedDay ? 'true' : 'false');
        var dayLabel = formatDay(day.date);
        button.setAttribute('aria-label', dayLabel + ': ' + formatDuration(day.active_seconds));
        if (!isMonth) append(button, 'span', 'reading-insights-day-name', formatDayShort(day.date));
        append(button, 'span', 'reading-insights-day-date', new intl().NumberFormat(locale()).format(Number(day.date.slice(-2))));
        if (day.active_seconds > 0) button.className += ' has-reading';
        append(button, 'strong', 'reading-insights-day-duration', formatDuration(day.active_seconds));
        button.addEventListener('click', function() { selectDay(day.date); });
        return button;
      });
      updateSessionHeading();
      renderSessions();
    }

    function renderBookRow(parent, book, source, rank) {
      var button = bookButton(parent, 'reading-insights-book-row' + (rank ? ' reading-insights-ranked-book' : ''), '', book.book_id, source);
      if (rank) append(button, 'span', 'reading-insights-book-rank', new intl().NumberFormat(locale()).format(rank)).setAttribute('aria-hidden', 'true');
      append(button, 'span', 'reading-insights-book-name', book.title);
      append(button, 'span', 'reading-insights-book-duration', formatDuration(book.active_seconds));
      var arrow = append(button, 'i', 'fas fa-chevron-right');
      arrow.setAttribute('aria-hidden', 'true');
    }

    function canReturnToTime() {
      return state.bookOrigin || state.opener?.hasAttribute('data-reading-insights-show-overview');
    }

    function buildBook(targetRoot) {
      var heading = append(targetRoot, 'section', 'reading-insights-heading reading-insights-book-heading');
      var identity = append(heading, 'div', '');
      var label = append(identity, 'p', 'reading-insights-book-label', translate(target, 'readingInsights.bookReport', 'Book reading stats'));
      var title = append(identity, 'h1', '');
      title.id = 'readingInsightsTitle';
      if (!state.modal && canReturnToTime()) {
        var back = append(heading, 'button', 'reading-insights-action', translate(target, 'readingInsights.backToOverview', 'Back to reading insights'));
        back.type = 'button';
        back.addEventListener('click', backToTime);
      }
      var bookLink = append(heading, 'a', 'reading-insights-book-link reading-insights-text-button',
        translate(target, 'reader.openBookHome', 'Open book home'));
      bookLink.setAttribute('href', publicPath(target, '/book/' + encodeURIComponent(state.bookId) + '/index.html'));
      var status = statusPanel(targetRoot, load);
      var summary = append(targetRoot, 'section', 'reading-insights-book-summary');
      state.view = { status: status, summary: summary, name: title, label: label, bookLink: bookLink };
    }

    function renderBook() {
      renderStatus(state.view.status, state.reportStatus);
      var book = state.book;
      state.view.summary.hidden = state.view.bookLink.hidden = !book;
      state.view.label.hidden = !book;
      state.view.name.textContent = book ? book.title : state.view.label.textContent;
      if (!book) return;
      state.view.summary.replaceChildren();
      var metrics = append(state.view.summary, 'dl', 'reading-insights-book-metrics');
      var dates = append(state.view.summary, 'dl', 'reading-insights-book-dates');
      function metric(group, label, value, timestamp) {
        var card = append(group, 'div', '');
        append(card, 'dt', '', label);
        var description = append(card, 'dd', '');
        if (timestamp) append(description, 'time', '', value).setAttribute('datetime', timestamp);
        else description.textContent = value;
      }
      function readDate(timestamp) {
        return timestamp ? new intl().DateTimeFormat(locale(), {
          dateStyle: 'medium', timeStyle: 'short', timeZone: state.timezone
        }).format(new Date(timestamp)) : '—';
      }
      metric(metrics, translate(target, 'readingInsights.total', 'Active reading'), formatDuration(book.active_seconds));
      metric(metrics, translate(target, 'readingInsights.annotations', 'Annotations'), new intl().NumberFormat(locale()).format(book.annotation_count));
      metric(dates, translate(target, 'readingInsights.firstRead', 'First read'), readDate(book.first_read_at), book.first_read_at);
      metric(dates, translate(target, 'readingInsights.lastRead', 'Last read'), readDate(book.last_read_at), book.last_read_at);
    }

    function refresh() {
      if (state.bookId) renderBook();
      else renderInsights();
      updateRangeControls();
    }

    function cancelRequest() {
      if (state.request) state.request.abort();
      state.request = null;
    }

    async function fetchReport(path, success, failure) {
      cancelRequest();
      var controller = new AbortController();
      state.request = controller;
      var timer = setTimeout(function() { controller.abort(); }, 30000);
      try {
        var response = await target.EpubBrowserAuth.fetch(publicPath(target, path), {
          method: 'GET', signal: controller.signal
        });
        if (!response || !response.ok) throw new Error('reading_insights_request_failed');
        var payload = await response.json();
        if (state.request !== controller) return null;
        return success(payload);
      } catch (error) {
        if (state.request === controller) failure();
        return null;
      } finally {
        clearTimeout(timer);
        if (state.request === controller) state.request = null;
      }
    }

    function load() {
      state.reportStatus = 'loading';
      refresh();
      var path = state.bookId ? '/api/books/' + encodeURIComponent(state.bookId) + '/insights'
        : '/api/reading-insights?period=' + encodeURIComponent(state.period) +
          '&anchor=' + encodeURIComponent(state.anchor) + '&timezone=' + encodeURIComponent(state.timezone);
      return fetchReport(path, function(payload) {
        if (!payload.insights) throw new Error('reading_insights_payload_invalid');
        if (state.bookId) state.book = payload.insights;
        else state.insights = payload.insights;
        state.reportStatus = '';
        refresh();
        if (!state.bookId && state.period !== 'overview') return loadSessions(1);
        return payload.insights;
      }, function() {
        state.reportStatus = 'error';
        refresh();
      });
    }

    function loadSessions(page) {
      state.sessionPage = page;
      state.sessions = null;
      state.sessionStatus = 'loading';
      renderSessions();
      var path = '/api/reading-insights/sessions?date=' + encodeURIComponent(state.selectedDay) +
        '&timezone=' + encodeURIComponent(state.timezone) + '&page=' + page;
      return fetchReport(path, function(payload) {
        if (!Array.isArray(payload.sessions)) throw new Error('reading_insights_payload_invalid');
        state.sessions = payload;
        state.sessionStatus = '';
        renderSessions();
        return payload;
      }, function() {
        state.sessionStatus = 'error';
        renderSessions();
      });
    }

    function updateSessionHeading() {
      state.view.selectedDay.textContent = selectedDayLabel(state.selectedDay);
      var day = state.insights.days?.find(function(item) { return item.date === state.selectedDay; });
      state.view.selectedDuration.textContent = day ? formatDuration(day.active_seconds) : '';
    }

    function selectDay(day) {
      if (!day || day === state.selectedDay || state.period === 'overview') return Promise.resolve(null);
      state.selectedDay = day;
      updateSessionHeading();
      state.view.dayButtons.forEach(function(button) {
        button.setAttribute('aria-pressed', button.getAttribute('data-date') === day ? 'true' : 'false');
      });
      return loadSessions(1);
    }

    function focusReport() {
      if (!state.modal) return;
      state.modal.querySelector('.reading-insights-dialog').scrollTop = 0;
      state.root.focus({ preventScroll: true });
    }

    function showBook(bookId) {
      state.bookId = bookId;
      state.book = null;
      build(state.root);
      focusReport();
      return load();
    }

    function backToTime() {
      cancelRequest();
      var origin = state.bookOrigin;
      state.bookId = '';
      state.bookOrigin = null;
      state.reportStatus = '';
      build(state.root);
      if (!origin) {
        focusReport();
        return load();
      }
      refresh();
      var trigger = state.view.bookButtons[origin.source + ':' + origin.bookId];
      if (trigger && trigger.focus) trigger.focus();
      if (state.sessionStatus === 'loading') loadSessions(state.sessionPage);
    }

    function shiftAnchor(anchor, period, amount) {
      var parts = String(anchor).split('-').map(Number);
      if (parts.length !== 3 || parts.some(function(value) { return !Number.isInteger(value); })) return localIsoDate();
      var year = parts[0];
      var month = parts[1] - 1;
      var day = parts[2];
      if (period === 'overview') {
        return utcIsoDate(new Date(Date.UTC(year + amount, month, day)));
      }
      if (period === 'month') {
        var shiftedMonth = new Date(Date.UTC(year, month + amount, 1));
        var lastDay = new Date(Date.UTC(shiftedMonth.getUTCFullYear(), shiftedMonth.getUTCMonth() + 1, 0)).getUTCDate();
        return utcIsoDate(new Date(Date.UTC(shiftedMonth.getUTCFullYear(), shiftedMonth.getUTCMonth(), Math.min(day, lastDay))));
      }
      var shifted = new Date(Date.UTC(year, month, day + (period === 'week' ? amount * 7 : amount)));
      return utcIsoDate(shifted);
    }

    function previousRangeForPeriod() {
      return setPeriod(state.period, shiftAnchor(state.anchor, state.period, -1));
    }

    function nextRangeForPeriod() {
      return setPeriod(state.period, shiftAnchor(state.anchor, state.period, 1));
    }

    function setPeriod(period, anchor) {
      if (!['overview', 'day', 'week', 'month'].includes(period)) return Promise.resolve(null);
      if (period === state.period && (!anchor || anchor === state.anchor)) return Promise.resolve(state.insights);
      state.period = period;
      state.anchor = anchor || localIsoDate();
      state.selectedDay = '';
      hideTooltip();
      state.insights = state.sessions = null;
      state.sessionStatus = '';
      updatePeriodControls();
      updateRangeControls();
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
      if (!state.localeBound && i18n && typeof i18n.onLocaleChange === 'function') {
        state.localeBound = true;
        i18n.onLocaleChange(function() {
          if (state.root && (!state.modal || !state.modal.hidden)) {
            build(state.root);
            refresh();
            focusReport();
          }
        });
      }
      return load();
    }

    function trapFocus(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (state.view.tooltip && !state.view.tooltip.hidden) hideTooltip();
        else close();
        return;
      }
      if (event.key !== 'Tab') return;
      var focusable = Array.from(state.modal.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), [tabindex]'))
        .filter(function(item) { return item.tabIndex >= 0 && !item.closest('[hidden]'); });
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && documentTarget.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && documentTarget.activeElement === last) { event.preventDefault(); first.focus(); }
    }

    function ensure() {
      if (state.modal || !documentTarget) return state.modal;
      var modal = documentTarget.createElement('div');
      modal.className = 'reading-insights-modal';
      modal.hidden = true;
      modal.setAttribute('role', 'dialog');
      modal.setAttribute('aria-modal', 'true');
      modal.setAttribute('aria-labelledby', 'readingInsightsTitle');
      modal.innerHTML = '<div class="reading-insights-backdrop" data-reading-insights-close></div><section class="reading-insights-dialog"><header class="reading-insights-modal-header"><button type="button" class="reading-insights-icon-button reading-insights-back-button" hidden><i class="fas fa-arrow-left" aria-hidden="true"></i><span></span></button><span class="reading-insights-header-label"><i class="fas fa-chart-column" aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></span><button type="button" class="reading-insights-icon-button" data-reading-insights-close-button><i class="fas fa-times" aria-hidden="true"></i></button></header><main class="reading-insights-container" data-reading-insights tabindex="-1"></main></section>';
      documentTarget.body.appendChild(modal);
      state.modal = modal;
      state.container = modal.querySelector('.reading-insights-container');
      state.backButton = modal.querySelector('.reading-insights-back-button');
      state.backButton.addEventListener('click', backToTime);
      state.closeButton = modal.querySelector('[data-reading-insights-close-button]');
      state.closeButton.addEventListener('click', close);
      modal.querySelector('[data-reading-insights-close]').addEventListener('click', close);
      modal.addEventListener('keydown', trapFocus);
      return modal;
    }

    function open(opener) {
      var modal = ensure();
      if (!modal) return Promise.resolve(null);
      if (modal.hidden) {
        // Start with the annual overview; day/week/month are drills into a
        // specific range, not sticky state from a previous visit.
        state.period = 'overview';
        state.anchor = localIsoDate();
        state.selectedDay = '';
        state.bookId = opener && opener.getAttribute('data-book-id') || '';
        state.bookOrigin = null;
        state.book = state.insights = state.sessions = null;
        state.sessionStatus = '';
        state.opener = opener || documentTarget.activeElement;
        state.scrollY = target.scrollY || 0;
        documentTarget.body.classList.add('reading-insights-open');
        documentTarget.body.style.top = '-' + state.scrollY + 'px';
        modal.hidden = false;
      }
      var result = mount(state.container);
      target.setTimeout(function() { if (state.closeButton) state.closeButton.focus(); }, 0);
      return result;
    }

    function close() {
      if (!state.modal || state.modal.hidden) return;
      cancelRequest();
      hideTooltip();
      state.modal.hidden = true;
      documentTarget.body.classList.remove('reading-insights-open');
      documentTarget.body.style.top = '';
      if (typeof target.scrollTo === 'function') target.scrollTo(0, state.scrollY);
      if (state.opener && typeof state.opener.focus === 'function') state.opener.focus({ preventScroll: true });
    }

    function bind(scope) {
      var targetScope = scope || documentTarget;
      if (!targetScope || !targetScope.querySelectorAll) return;
      Array.prototype.forEach.call(targetScope.querySelectorAll('[data-reading-insights]'), function(trigger) {
        if (trigger === state.container || trigger.dataset.readingInsightsBound) return;
        trigger.dataset.readingInsightsBound = 'true';
        trigger.addEventListener('click', function() { open(trigger); });
      });
    }

    return { mount: mount, open: open, close: close, bind: bind, selectDay: selectDay, setPeriod: setPeriod, previousRange: previousRangeForPeriod, nextRange: nextRangeForPeriod, load: load, get sessionRows() { return state.view.sessionList ? state.view.sessionList.children : []; }, get activityCells() { return state.view.heatmap ? Array.prototype.filter.call(state.view.heatmap.children, function(item) { return /reading-insights-heatmap-cell/.test(item.className); }) : []; }, get metricButtons() { return state.view.metricButtons || []; }, get periodButtons() { return state.view.periodButtons || []; }, get rangeLabel() { return state.view.rangeLabel; }, get rangeButtons() { return { previous: state.view.previousRange, next: state.view.nextRange }; } };
  }

  var defaultClient = null;
  function client() {
    defaultClient = defaultClient || createClient(root);
    return defaultClient;
  }
  function bind() { return client().bind(); }
  if (root.document) {
    if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', bind);
    else bind();
  }
  return {
    create: createClient,
    mount: function(target) {
      return client().mount(target);
    },
    open: function(opener) { return client().open(opener); },
    close: function() { return client().close(); },
    bind: bind
  };
});
