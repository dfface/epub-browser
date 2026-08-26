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

  function endpoint(target, period, anchor, timezone) {
    var path = '/api/reading-insights?period=' + encodeURIComponent(period) +
      '&anchor=' + encodeURIComponent(anchor) + '&timezone=' + encodeURIComponent(timezone);
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
      selectedDay: '',
      loading: false,
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
      if (value < 60) return 1;
      if (value < 15 * 60) return 2;
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

    function selectedDayLabel(value) {
      return value === localIsoDate()
        ? translate(target, 'readingInsights.today', 'Today')
        : formatDay(value);
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
      if (state.view.previousRange) state.view.previousRange.disabled = busy;
      if (state.view.nextRange) state.view.nextRange.disabled = busy;
      if (state.view.todayRange) state.view.todayRange.disabled = busy;
      (state.view.metricButtons || []).forEach(function(button) { button.disabled = busy; });
    }

    function setLive(message) {
      if (state.view.live) state.view.live.textContent = message;
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
      targetRoot.replaceChildren();
      targetRoot.className = 'reading-insights-page';
      targetRoot.setAttribute('tabindex', '-1');
      targetRoot.setAttribute('aria-labelledby', 'readingInsightsTitle');
      if (state.modal) {
        state.modal.querySelector('.reading-insights-header-label span').textContent = translate(target, 'readingInsights.navigation', 'Reading insights');
        state.closeButton.setAttribute('aria-label', translate(target, 'readingInsights.close', 'Close'));
      }

      var heading = append(targetRoot, 'section', 'reading-insights-heading');
      append(heading, 'p', 'reading-insights-kicker', translate(target, 'readingInsights.privateKicker', 'Private to your account'));
      var title = append(heading, 'h1', '', translate(target, 'readingInsights.title', 'Reading insights'));
      title.id = 'readingInsightsTitle';
      append(heading, 'p', '', translate(target, 'readingInsights.intro', 'See when you actively read and where your time went.'));

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
      var analytics = append(targetRoot, 'section', 'reading-insights-analytics');
      var analyticsTitle = append(analytics, 'h2', '', translate(target, 'readingInsights.activity', 'Reading activity'));
      analyticsTitle.id = 'readingInsightsActivityTitle';
      analytics.setAttribute('aria-labelledby', analyticsTitle.id);
      var analyticsGrid = append(analytics, 'div', 'reading-insights-analytics-grid');
      var heatmapCard = append(analyticsGrid, 'article', 'reading-insights-analytics-card reading-insights-heatmap-card');
      append(heatmapCard, 'h3', '', translate(target, 'readingInsights.activityHeatmap', 'Activity calendar'));
      var heatmapRange = append(heatmapCard, 'p', 'reading-insights-analytics-description');
      var heatmapScroll = append(heatmapCard, 'div', 'reading-insights-heatmap-scroll');
      heatmapScroll.setAttribute('tabindex', '0');
      heatmapScroll.setAttribute('aria-label', translate(target, 'readingInsights.activityHeatmap', 'Activity calendar'));
      var heatmapMonths = append(heatmapScroll, 'div', 'reading-insights-heatmap-months');
      heatmapMonths.setAttribute('aria-hidden', 'true');
      var heatmap = append(heatmapScroll, 'div', 'reading-insights-heatmap');
      heatmap.setAttribute('role', 'group');
      heatmap.setAttribute('aria-label', translate(target, 'readingInsights.activityHeatmap', 'Activity calendar'));
      var legend = append(heatmapCard, 'div', 'reading-insights-heatmap-legend');
      append(legend, 'span', '', translate(target, 'readingInsights.activityLess', 'Less'));
      var legendScale = append(legend, 'span', 'reading-insights-heatmap-legend-scale');
      [0, 1, 2, 3, 4].forEach(function(level) { append(legendScale, 'i', 'is-level-' + level); });
      append(legend, 'span', '', translate(target, 'readingInsights.activityMore', 'More'));
      var trendCard = append(analyticsGrid, 'article', 'reading-insights-analytics-card reading-insights-trend-card');
      append(trendCard, 'h3', '', translate(target, 'readingInsights.trend', 'Daily trend'));
      var trendRange = append(trendCard, 'p', 'reading-insights-analytics-description');
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
      var trendYLabel = append(trendYAxis, 'span', 'reading-insights-trend-y-label');
      var trendYMax = append(trendYAxis, 'strong', 'reading-insights-trend-y-max');
      var trendChart = append(trendAxis, 'div', 'reading-insights-trend-chart');
      trendChart.setAttribute('role', 'img');
      var trendXAxis = append(trendCard, 'div', 'reading-insights-trend-x-axis');
      var trendValue = append(trendCard, 'p', 'reading-insights-trend-value', '—');
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
      state.view = { periodButtons: periodButtons, previousRange: previousRange, nextRange: nextRange, todayRange: todayRange, rangeLabel: rangeLabel, live: live, total: total, topBook: topBook, analytics: analytics, heatmap: heatmap, heatmapMonths: heatmapMonths, heatmapRange: heatmapRange, trendChart: trendChart, trendValue: trendValue, trendRange: trendRange, trendYLabel: trendYLabel, trendYMax: trendYMax, trendXAxis: trendXAxis, metricButtons: metricButtons, days: days, dayList: dayList, selectedDay: selectedDay, sessions: sessions, sessionList: sessionList, dayButtons: [] };
      updatePeriodControls();
      updateRangeControls();
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
        var time = formatTime(session.started_at);
        var book = session.book_title || translate(target, 'readingInsights.unknownBook', 'Unknown book');
        var chapter = session.chapter_label || translate(target, 'readingInsights.unknownChapter', 'Unknown chapter');
        var duration = formatDuration(session.active_seconds);
        var item = append(state.view.sessionList, 'li', 'reading-insights-session');
        item.setAttribute('aria-label', [time, book, chapter, duration].join(' '));
        append(item, 'time', 'reading-insights-session-time', time);
        var details = append(item, 'span', 'reading-insights-session-details');
        append(details, 'strong', 'reading-insights-session-book', book);
        append(details, 'span', 'reading-insights-session-chapter', chapter);
        append(item, 'span', 'reading-insights-session-duration is-' + durationTone(session.active_seconds), duration);
      });
    }

    function renderActivity() {
      var activity = state.insights && state.insights.activity;
      var days = activity && Array.isArray(activity.days) ? activity.days : [];
      var metric = state.activityMetric === 'books' ? 'book_count' : 'active_seconds';
      if (state.view.heatmapRange) {
        var heatmapRangeText = days.length
          ? formatDateRange('overview', days[days.length - 1].date)
          : translate(target, 'readingInsights.activityRange', 'Past year');
        state.view.heatmapRange.textContent = heatmapRangeText;
      }
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
        days.forEach(function(day) {
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
          cell.setAttribute('title', label);
          cell.addEventListener('click', function() { setPeriod('day', day.date); });
        });
      }
      (state.view.metricButtons || []).forEach(function(button) {
        var isSelected = button.getAttribute('data-reading-insights-metric') === state.activityMetric;
        button.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
      });
      var trendMonth = state.anchor.slice(0, 7);
      var trendDays = days.filter(function(day) { return day.date.slice(0, 7) === trendMonth; });
      var trendRangeText = formatDateRange('month', state.anchor);
      if (state.view.trendRange) state.view.trendRange.textContent = trendRangeText;
      var values = trendDays.map(function(day) { return Math.max(0, Number(day[metric]) || 0); });
      var total = values.reduce(function(sum, value) { return sum + value; }, 0);
      var trendValueText = metric === 'active_seconds'
        ? formatDuration(total)
        : translate(target, 'readingInsights.booksRead', 'Books read: ' + total, { count: total });
      if (state.view.trendValue) {
        state.view.trendValue.textContent = trendValueText;
      }
      if (!state.view.trendChart) return;
      var maximum = Math.max.apply(Math, values.concat([1]));
      var trendAxisText = metric === 'active_seconds'
        ? translate(target, 'readingInsights.axis.readingTime', 'Reading time')
        : translate(target, 'readingInsights.axis.books', 'Books');
      if (state.view.trendYLabel) {
        state.view.trendYLabel.textContent = trendAxisText;
      }
      var trendMaximumText = metric === 'active_seconds'
        ? formatDuration(maximum)
        : translate(target, 'readingInsights.booksRead', 'Books read: ' + maximum, { count: maximum });
      if (state.view.trendYMax) {
        state.view.trendYMax.textContent = trendMaximumText;
      }
      if (state.view.trendXAxis) {
        state.view.trendXAxis.replaceChildren();
        if (trendDays.length) {
          [0, Math.floor((trendDays.length - 1) / 2), trendDays.length - 1].filter(function(index, position, indices) {
            return indices.indexOf(index) === position;
          }).forEach(function(index) {
            append(state.view.trendXAxis, 'span', '', formatDayNumber(trendDays[index].date));
          });
        }
      }
      var trendTitleKey = metric === 'active_seconds' ? 'readingInsights.trend.duration' : 'readingInsights.trend.books';
      var trendTitleFallback = metric === 'active_seconds' ? 'Reading time' : 'Books read';
      var trendAriaLabel = translate(target, trendTitleKey, trendTitleFallback) + ': ' + trendValueText;
      state.view.trendChart.setAttribute('aria-label', trendAriaLabel);
      state.view.trendChart.replaceChildren();
      if (!trendDays.length || !documentTarget.createElementNS) return;
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
      area.setAttribute('d', 'M ' + points.join(' L ') + ' L 100,40 L 0,40 Z');
      var line = documentTarget.createElementNS('http://www.w3.org/2000/svg', 'path');
      line.setAttribute('class', 'reading-insights-trend-line');
      line.setAttribute('d', 'M ' + points.join(' L '));
      svg.appendChild(area);
      svg.appendChild(line);
      state.view.trendChart.appendChild(svg);
    }

    function renderInsights() {
      var insights = state.insights || {};
      var days = Array.isArray(insights.days) ? insights.days : [];
      if (!state.selectedDay || !days.some(function(day) { return day.date === state.selectedDay; })) {
        var today = localIsoDate();
        state.selectedDay = days.some(function(day) { return day.date === today; })
          ? today : (days.length ? days[days.length - 1].date : state.anchor);
      }
      state.view.total.textContent = formatDuration(insights.total_active_seconds);
      state.view.topBook.textContent = insights.top_book
        ? insights.top_book.title + ' · ' + formatDuration(insights.top_book.active_seconds) : '—';
      renderActivity();
      state.view.analytics.hidden = state.period !== 'overview';
      state.view.days.hidden = state.period === 'day' || state.period === 'overview';
      state.view.sessions.hidden = state.period === 'overview';
      state.view.dayList.replaceChildren();
      state.view.dayButtons = days.map(function(day) {
        var button = append(state.view.dayList, 'button', 'reading-insights-day-button');
        button.type = 'button';
        button.setAttribute('aria-pressed', day.date === state.selectedDay ? 'true' : 'false');
        var dayLabel = formatDay(day.date);
        button.setAttribute('aria-label', dayLabel + ': ' + formatDuration(day.active_seconds));
        append(button, 'span', 'reading-insights-day-name', formatDayShort(day.date));
        append(button, 'span', 'reading-insights-day-date', formatDayNumber(day.date));
        append(button, 'strong', 'reading-insights-day-duration', formatDuration(day.active_seconds));
        button.addEventListener('click', function() { selectDay(day.date); });
        return button;
      });
      state.view.selectedDay.textContent = state.selectedDay
        ? selectedDayLabel(state.selectedDay)
        : translate(target, 'readingInsights.selectedDay', 'Selected day');
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
        .finally(function() { setBusy(false); updateRangeControls(); });
    }

    function selectDay(day) {
      if (!day || day === state.selectedDay) return Promise.resolve(state.insights);
      state.selectedDay = day;
      renderInsights();
      return Promise.resolve(state.insights);
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
        i18n.onLocaleChange(function() { if (state.root) { build(state.root); renderInsights(); } });
      }
      return load();
    }

    function trapFocus(event) {
      if (event.key === 'Escape') { event.preventDefault(); close(); return; }
      if (event.key !== 'Tab') return;
      var focusable = state.modal.querySelectorAll('button:not([hidden]):not([disabled]), a[href], [tabindex]:not([tabindex="-1"])');
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
      modal.innerHTML = '<div class="reading-insights-backdrop" data-reading-insights-close></div><section class="reading-insights-dialog"><header class="reading-insights-modal-header"><span class="reading-insights-header-label"><i class="fas fa-chart-column" aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></span><button type="button" class="reading-insights-icon-button" data-reading-insights-close-button><i class="fas fa-times" aria-hidden="true"></i></button></header><main class="reading-insights-container" data-reading-insights tabindex="-1"></main></section>';
      documentTarget.body.appendChild(modal);
      state.modal = modal;
      state.container = modal.querySelector('.reading-insights-container');
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
      state.modal.hidden = true;
      documentTarget.body.classList.remove('reading-insights-open');
      documentTarget.body.style.top = '';
      if (typeof target.scrollTo === 'function') target.scrollTo(0, state.scrollY);
      if (state.opener && typeof state.opener.focus === 'function') state.opener.focus();
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
