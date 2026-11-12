"""Dependency-free Server dashboard for legacy Kindle browsers."""

import json
from html import escape
from typing import Callable

from .i18n_bundles import get_bundle
from .locales import SUPPORTED_LOCALES


KINDLE_WIDGETS = ("clock", "calendar", "memo", "default")
KINDLE_MEMO_MAX_LENGTH = 4000


def valid_kindle_memo(text):
    return (
        isinstance(text, str) and len(text) <= KINDLE_MEMO_MAX_LENGTH
        and "\x00" not in text
        and not any(0xD800 <= ord(char) <= 0xDFFF for char in text)
    )


def kindle_message(locale, key):
    keys = {
        "library": "library.title",
        "language": "common.language",
        "previousPage": "reader.previousPage",
        "nextPage": "reader.nextPage",
        "pageOf": "pdf.pageOf",
        "settings": "reader.settings",
        "light": "theme.light",
        "sepia": "theme.sepia",
        "dark": "theme.dark",
        "fontFamily": "settings.fontFamily",
        "fontSize": "settings.fontSize",
        "bookDefault": "settings.bookDefault",
        "pageMode": "settings.paginationMode",
        "tapTurn": "reader.clickToTurn",
        "bookshelf": "bookshelf.title",
        "continue": "library.recentReading.title",
        "emptyLibrary": "library.empty",
        "emptyShelf": "bookshelf.empty",
        "screensaver": "account.kindle.screensaver",
        "calendar": "account.kindle.calendar",
        "memo": "account.kindle.memo",
        "pomodoro": "account.kindle.pomodoro",
        "reset": "settings.reset",
        "search": "library.searchPlaceholder",
        "searchAction": "admin.books.searchLabel",
        "agenda": "account.kindle.agenda",
        "noEvents": "account.kindle.noEvents",
        "calendarUnavailable": "account.kindle.calendarUnavailable",
    }
    prefix = "account.kindle." if key.startswith("pomo") else "kindle."
    message_key = keys.get(key, prefix + key)
    return get_bundle(locale).get(message_key) or get_bundle("en")[message_key]


def kindle_locale_script(messages, *, use_initial_locale=False):
    """Share the UI language across the library, dashboard and reader."""
    bundles = {locale: messages(locale) for locale in SUPPORTED_LOCALES}
    serialized = json.dumps(bundles, ensure_ascii=True).replace("<", "\\u003c")
    return r"""
(function () {
  var dictionaries = %s;
  var keys = Object.keys(dictionaries);
  var listeners = [];
  var active;
  function normalize(value) {
    var code = (value || '').toLowerCase().replace(/_/g, '-');
    var base = code.split('-')[0];
    if (base === 'zh') return /^zh-(tw|hk|mo|hant)/.test(code) ? 'zh-TW' : 'zh-CN';
    if (base === 'pt') return 'pt-BR';
    for (var i = 0; i < keys.length; i++) if (keys[i] === base) return base;
    return '';
  }
  window.kTranslate = function (key) { return dictionaries[active][key]; };
  window.kOnLocaleChange = function (callback) { listeners.push(callback); };
  window.kLocalize = function (root) {
    var elements = (root || document).querySelectorAll('[data-i18n],[data-i18n-aria-label],[data-i18n-placeholder]');
    for (var i = 0; i < elements.length; i++) {
      var element = elements[i];
      var message = kTranslate(element.getAttribute('data-i18n'));
      if (typeof message === 'string') element.textContent = message;
      var attributes = ['aria-label', 'placeholder'];
      for (var j = 0; j < attributes.length; j++) {
        var text = kTranslate(element.getAttribute('data-i18n-' + attributes[j]));
        if (typeof text === 'string') {
          text = text.replace('{number}', element.getAttribute('data-page') || '')
                     .replace('{total}', element.getAttribute('data-total') || '');
          element.setAttribute(attributes[j], text);
        }
      }
    }
  };
  function apply(locale) {
    active = locale;
    document.documentElement.lang = locale;
    var select = document.getElementById('kLanguage');
    if (select) select.value = locale;
    var chrome = document.querySelectorAll('[data-k-ui-language]');
    for (var i = 0; i < chrome.length; i++) chrome[i].lang = locale;
    kLocalize(document);
    for (var j = 0; j < listeners.length; j++) listeners[j]();
  }
  window.kSetLocale = function (locale) {
    locale = normalize(locale);
    if (!locale) return;
    setCookie('epub_browser_locale', locale, 365);
    apply(locale);
  };
  function sync() {
    var fallback = %s ? initial : (navigator.language || navigator.userLanguage);
    apply(normalize(getCookie('epub_browser_locale')) || normalize(fallback) || 'en');
  }
  var initial = document.documentElement.lang;
  var previousPageShow = window.onpageshow;
  sync();
  window.onpageshow = function (event) {
    if (event && event.persisted) sync();
    if (previousPageShow) previousPageShow(event);
  };
})();
""" % (serialized, "true" if use_initial_locale else "false")


def render_kindle_dock(urls, locale, *, default_view=None, tools=None):
    """Keep the same destinations and order throughout the Kindle interface."""
    tabs = [("library", "kLibraryView")]
    if tools is not None:
        tabs.append(("screensaver", "kDashboardWidgets"))
        if tools.get("pomodoro"):
            tabs.append(("pomodoro", "kPomodoro"))
    tabs.append(("settings", "kHomeSettings"))
    local = default_view is not None
    base = "" if local else urls.public("/kindle-library.html")
    links = []
    for key, view in tabs:
        href = base + "#" + view if local or key != "library" else base
        current = ' aria-current="location"' if not local and key == "library" else ""
        links.append(
            f'<a href="{escape(href)}" data-i18n="{key}"{current}>'
            f'{escape(kindle_message(locale, key))}</a>'
        )
    default = f' data-default="{escape(default_view)}"' if local else ""
    return f'<nav class="k-dock k-surface" id="kDock"{default}>{"".join(links)}</nav>'


def _render_pomodoro(copy: Callable[[str], str]) -> str:
    def presets(name, label, values, default):
        buttons = "".join(
            f'<label><input type="radio" name="{name}" value="{value}"'
            f'{" checked" if value == default else ""}><span>{value}</span></label>'
            for value in values
        )
        return f'<fieldset><legend data-i18n="{label}">{copy(label)}</legend>{buttons}</fieldset>'

    return f"""
<section id="kPomodoro" class="k-dash-card k-surface" data-k-view style="display:none">
    <h2 data-i18n="pomodoro">{copy("pomodoro")}</h2>
    <div class="k-pomo-display">
        <span id="kPomoTime" role="timer" aria-live="off">25:00</span>
        <p id="kPomoPhase" role="status"></p>
    </div>
    <div id="kPomoChoices">
        {presets("focus", "pomoFocusMinutes", (15, 25, 45), 25)}
        {presets("break", "pomoBreakMinutes", (3, 5, 10), 5)}
        {presets("rounds", "pomoRounds", (1, 2, 4, 6), 4)}
    </div>
    <div class="k-pomo-actions">
        <button class="k-control" id="kPomoToggle" type="button">{copy("pomoStart")}</button>
        <button class="k-control" id="kPomoReset" type="button" data-i18n="reset">{copy("reset")}</button>
    </div>
</section>"""


def render_kindle_dashboard_widgets(settings, locale, active):
    def copy(key):
        return escape(kindle_message(locale, key))

    clock = (
        '<section class="k-clock-panel k-surface">'
        '<p id="kClockDate" class="k-clock-date"></p>'
        '<time id="kClock" class="k-clock">'
        '<span id="kHour" class="k-digit k-control"></span><span class="k-colon">:</span>'
        '<span id="kMinute" class="k-digit k-control"></span></time></section>'
        if settings["clock"] else ""
    )
    calendar = (
        f'<section id="kCalendar" class="k-dash-card k-surface" data-i18n-aria-label="calendar" aria-label="{copy("calendar")}">'
        '<h2 id="kMonth"></h2><table id="kDays"></table></section>'
        if settings["calendar"] else ""
    )
    agenda = (
        f'<section id="kAgenda" class="k-dash-card k-surface"><h2 data-i18n="agenda">{copy("agenda")}</h2>'
        '<p id="kCalendarStatus" role="status"></p>'
        '<ol id="kEvents"></ol></section>'
        if settings["calendar"] and (settings.get("calendar_urls") or settings.get("calendar_url")) else ""
    )
    memo = (
        f'<section class="k-dash-card k-surface"><h2 data-i18n="memo">{copy("memo")}</h2>'
        f'<div id="kMemo">{escape(settings["text"])}</div></section>'
        if settings["memo"] else ""
    )
    widgets = (
        '<div class="k-dash-widgets' + (' k-dash-pair' if calendar and memo else '') + '">'
        + calendar + memo + '</div>'
        if calendar or memo else ""
    )
    pomodoro = _render_pomodoro(copy) if settings["pomodoro"] else ""
    pomodoro_script = _POMODORO_JS if pomodoro else ""
    visible = '' if active else ' style="display:none"'
    panels = f'<section id="kDashboardWidgets" class="k-dashboard" data-k-view{visible}>{clock}{widgets}{agenda}</section>'
    return panels + pomodoro, _DASHBOARD_JS + pomodoro_script


_KINDLE_DASHBOARD_CSS = """
.k-dashboard{box-sizing:border-box;margin:0 auto;padding:0;max-width:660px;font:15px/1.4 Arial,sans-serif}
.k-dashboard .k-clock-panel.k-surface{padding:8px 12px 12px;margin:0 0 8px;text-align:center}
.k-clock-date{margin:0 0 6px;font-size:.88em;font-weight:bold}
.k-clock{display:block;white-space:nowrap;font-size:0}
.k-digit{display:inline-block;vertical-align:middle;box-sizing:border-box;width:43%;max-width:220px;
  padding:5px 0 7px;border-color:transparent;
  font:700 78px/1.04 Arial,sans-serif;letter-spacing:-.045em}
.k-colon{display:inline-block;vertical-align:middle;width:8%;max-width:34px;font:700 33px/1 Arial,sans-serif}
.k-dash-widgets{font-size:0;margin-bottom:8px}
.k-dash-card{box-sizing:border-box;padding:8px 10px;font:15px/1.35 Arial,sans-serif}
.k-dash-widgets .k-dash-card + .k-dash-card{margin-top:8px}
.k-dash-card h2{font-size:.9em;margin:0 0 4px}
#kDays{width:100%;table-layout:fixed;text-align:center;border-spacing:1px;font-size:.83em}
#kDays td,#kDays th{height:20px;padding:0}
#kDays td.today{background:#111;color:#fff;font-weight:bold}
body.dark #kDays td.today{background:#eee;color:#111}
#kDays .event-day{text-decoration:underline;font-weight:bold}
#kCalendarStatus{margin:3px 0;font-size:.84em}
#kCalendarStatus:empty{display:none}
#kEvents{list-style:none;padding:0;margin:0}
#kEvents li{border-top:1px solid #aaa;padding:5px 0;word-wrap:break-word;font-size:.87em}
#kEvents time{display:inline-block;margin-right:9px;font-weight:bold}
#kMemo{white-space:pre-wrap;word-wrap:break-word;max-height:11em;overflow:auto}
#kPomodoro{margin-bottom:8px;padding:14px 16px}
.k-pomo-display{text-align:center;padding:10px 0 14px;margin:0 0 10px;border-bottom:1px solid #aaa}
#kPomoTime{display:block;font:700 64px/1 Arial,sans-serif;font-variant-numeric:tabular-nums;letter-spacing:-.035em}
#kPomoPhase{min-height:1.4em;margin:6px 0 0;font-weight:bold;font-size:.87em}
#kPomoChoices fieldset{margin:0 0 8px;padding:0;border:0}
#kPomoChoices legend{font-size:.84em;font-weight:bold;margin-bottom:3px}
#kPomoChoices label{display:inline-block;position:relative;margin:0 5px 0 0}
#kPomoChoices input{position:absolute;left:0;top:0;opacity:0}
#kPomoChoices label span{display:block;min-width:32px;padding:9px 8px;min-height:24px;
  text-align:center;border:1px solid #888;border-radius:8px}
#kPomoChoices input:checked + span{border-color:currentColor;box-shadow:inset 0 0 0 1px currentColor;font-weight:bold}
#kPomoChoices input:focus + span{outline:2px solid;outline-offset:2px}
.k-pomo-actions{text-align:center}
#kPomoToggle,#kPomoReset{margin:4px 3px 0;min-width:100px;font-size:.88em}
#kPomoToggle{border:2px solid currentColor;font-weight:bold}
#kPomoReset{display:none}
@media (min-width:460px){
  .k-dash-pair{display:-webkit-box;display:-webkit-flex;display:flex;-webkit-box-align:stretch}
  .k-dash-pair .k-dash-card{display:inline-block;vertical-align:top;width:49%;min-height:162px}
  .k-dash-pair .k-dash-card + .k-dash-card{margin:0 0 0 2%}
}
@media (max-width:370px){.k-digit{font-size:60px}}
"""


_DASHBOARD_JS = r"""
(function () {
  var clock = document.getElementById('kClock');
  var clockDate = document.getElementById('kClockDate');
  var hour = document.getElementById('kHour');
  var minute = document.getElementById('kMinute');
  var month = document.getElementById('kMonth');
  var days = document.getElementById('kDays');
  var memo = document.getElementById('kMemo');
  var agenda = document.getElementById('kEvents');
  var calendarStatus = document.getElementById('kCalendarStatus');
  var events = [];
  var calendarUnavailable = false;
  var calendarLoaded = false;
  var calendarPartial = false;
  var locale = document.documentElement.lang;
  var lastDate = '';
  function weekdays() {
    return locale.indexOf('zh') === 0 ? ['一','二','三','四','五','六','日']
      : ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  }
  function pad(value) { return value < 10 ? '0' + value : String(value); }
  function label(date, options, fallback) {
    try {
      if (window.Intl && Intl.DateTimeFormat) {
        return new Intl.DateTimeFormat(locale, options).format(date);
      }
    } catch (error) {}
    return fallback;
  }
  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }
  function eventDate(text) {
    if (!text) return null;
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
      var parts = text.split('-');
      return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    }
    var parsed = new Date(text);
    return isNaN(parsed.getTime()) ? null : parsed;
  }
  function eventOnDay(event, day) {
    var start = eventDate(event.start);
    if (!start) return false;
    var end = eventDate(event.end) || start;
    var tomorrow = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1);
    return start < tomorrow && (end > day || start >= day);
  }
  function drawAgenda(now) {
    if (!agenda) return;
    agenda.innerHTML = '';
    var startDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var endDay = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7);
    for (var i = 0; i < events.length && agenda.children.length < 12; i++) {
      var event = events[i];
      var start = eventDate(event.start);
      var end = eventDate(event.end) || start;
      if (!start || start >= endDay || (end <= startDay && start < startDay)) continue;
      var row = document.createElement('li');
      var time = document.createElement('time');
      var shown = start < startDay ? startDay : start;
      var dateLabel = shown.getFullYear() + '-' + pad(shown.getMonth() + 1) + '-' + pad(shown.getDate());
      time.setAttribute('datetime', shown === start ? event.start : dateLabel);
      time.textContent = label(shown, {month: 'short', day: 'numeric'},
        pad(shown.getMonth() + 1) + '/' + pad(shown.getDate()));
      if (shown === start && event.start.length > 10) {
        time.textContent += ' · ' + pad(start.getHours()) + ':' + pad(start.getMinutes());
      }
      row.appendChild(time);
      row.appendChild(document.createTextNode(event.title));
      agenda.appendChild(row);
    }
    var message = calendarUnavailable || calendarPartial ? 'calendarUnavailable' : 'noEvents';
    setText(calendarStatus, calendarUnavailable || calendarPartial || (calendarLoaded && !agenda.children.length)
      ? kTranslate(message) : '');
  }
  function refreshCalendar() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/kindle/screensaver/calendar', true);
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      if (xhr.status === 401 || xhr.status === 403) events = [];
      calendarUnavailable = xhr.status !== 200;
      if (!calendarUnavailable) {
        try {
          var payload = JSON.parse(xhr.responseText);
          calendarUnavailable = payload.unavailable;
          calendarPartial = payload.partial === true;
          if (!calendarUnavailable) events = payload.events;
        } catch (error) { calendarUnavailable = true; }
      }
      calendarLoaded = true;
      lastDate = '';
      update();
    };
    xhr.send(null);
  }
  function update() {
    var now = new Date();
    if (clock) {
      var hours = pad(now.getHours());
      var minutes = pad(now.getMinutes());
      setText(hour, hours);
      setText(minute, minutes);
      var time = hours + ':' + minutes;
      if (clock.getAttribute('datetime') !== time) clock.setAttribute('datetime', time);
    }
    var dateKey = now.toDateString();
    if (lastDate === dateKey) return;
    lastDate = dateKey;
    var year = now.getFullYear();
    var m = now.getMonth();
    if (clockDate) {
      setText(clockDate, label(now, {weekday: 'long', month: 'long', day: 'numeric'},
        year + '/' + pad(m + 1) + '/' + pad(now.getDate())));
    }
    if (!days) return;
    var first = (new Date(year, m, 1).getDay() + 6) % 7;
    var count = new Date(year, m + 1, 0).getDate();
    setText(month, label(now, {year: 'numeric', month: 'long'}, year + ' / ' + pad(m + 1)));
    var rows = '<thead><tr>';
    var fallbackDays = weekdays();
    for (var i = 0; i < 7; i++) {
      var heading = document.createElement('span');
      heading.textContent = label(new Date(2024, 0, i + 1), {weekday: 'short'}, fallbackDays[i]);
      rows += '<th scope="col">' + heading.innerHTML + '</th>';
    }
    rows += '</tr></thead><tbody>';
    for (var offset = 0; offset < first + count; offset += 7) {
      rows += '<tr>';
      for (var col = 0; col < 7; col++) {
        var day = offset + col - first + 1;
        var today = day === now.getDate();
        rows += '<td' + (today ? ' class="today" aria-current="date"' : '') + '>';
        if (day > 0 && day <= count) {
          var marked = false;
          var date = new Date(year, m, day);
          for (var e = 0; e < events.length && !marked; e++) marked = eventOnDay(events[e], date);
          rows += marked ? '<span class="event-day">' + day + '</span>' : day;
        }
        rows += '</td>';
      }
      rows += '</tr>';
    }
    days.innerHTML = rows + '</tbody>';
    drawAgenda(now);
  }
  function refreshMemo() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/kindle/screensaver/memo', true);
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      if (xhr.status === 401 || xhr.status === 403) setText(memo, '');
      if (xhr.status === 200) {
        try { setText(memo, JSON.parse(xhr.responseText).memo); } catch (error) {}
      }
    };
    xhr.send(null);
  }
  kOnLocaleChange(function () {
    locale = document.documentElement.lang;
    lastDate = '';
    if (!window.kActivateDashboard) update();
  });
  window.kActivateDashboard = function () {
    window.kActivateDashboard = null;
    if (clock || days) {
      update();
      (function tick() {
        window.setTimeout(function () {
          update();
          tick();
        }, 60000 - new Date().getTime() % 60000 + 25);
      })();
    }
    if (memo) window.setInterval(refreshMemo, 60000);
    if (agenda) {
      refreshCalendar();
      window.setInterval(refreshCalendar, 600000);
    }
  };
})();
"""


_POMODORO_JS = """
(function () {
  var choices = document.getElementById('kPomoChoices');
  function selected(name) {
    var options = document.getElementsByName(name);
    for (var i = 0; i < options.length; i++) {
      if (options[i].checked) return Number(options[i].value);
    }
    return Number(options[0].value);
  }
  var rounds = 1;
  var phaseLabel = document.getElementById('kPomoPhase');
  var clock = document.getElementById('kPomoTime');
  var toggle = document.getElementById('kPomoToggle');
  var reset = document.getElementById('kPomoReset');
  var phase = '';
  var round = 0;
  var remaining = 0;
  var deadline = 0;
  var interval;
  var paused = false;
  function word(key) { return kTranslate('pomo' + key.charAt(0).toUpperCase() + key.slice(1)); }
  function setText(node, value) {
    if (node.textContent !== value) node.textContent = value;
  }
  function pad(value) { return value < 10 ? '0' + value : String(value); }
  function draw() {
    var seconds = phase ? Math.ceil(remaining / 1000) : selected('focus') * 60;
    var active = phase === 'focus' || phase === 'break';
    setText(clock, phase === 'complete' ? '00:00' : pad(Math.floor(seconds / 60)) + ':' + pad(seconds % 60));
    setText(phaseLabel, active ? word(phase) + ' · ' + round + '/' + rounds
      : (phase === 'complete' ? word('complete') : ''));
    setText(toggle, word(deadline ? 'pause' : paused ? 'resume' : 'start'));
    choices.style.display = phase ? 'none' : '';
    toggle.style.display = phase === 'complete' ? 'none' : '';
    reset.style.display = phase ? 'inline-block' : 'none';
    if (phase === 'complete' && document.activeElement === toggle) reset.focus();
  }
  function stop() {
    if (interval) window.clearInterval(interval);
    interval = null;
    deadline = 0;
  }
  function stage(next) {
    phase = next;
    paused = false;
    remaining = selected(next) * 60000;
  }
  function update() {
    remaining = Math.max(0, deadline - new Date().getTime());
    if (!remaining) {
      stop();
      if (phase === 'break') {
        round++;
        stage('focus');
      } else if (round < rounds) stage('break');
      else phase = 'complete';
    }
    draw();
  }
  toggle.onclick = function () {
    if (deadline) {
      update();
      if (!deadline) return;
      stop();
      paused = true;
    } else {
      if (!phase) {
        round = 1;
        rounds = selected('rounds');
        stage('focus');
      }
      deadline = new Date().getTime() + remaining;
      paused = false;
      interval = window.setInterval(update, 250);
    }
    draw();
  };
  var presets = choices.getElementsByTagName('input');
  for (var i = 0; i < presets.length; i++) presets[i].onchange = draw;
  kOnLocaleChange(draw);
  reset.onclick = function () {
    stop();
    paused = false;
    phase = '';
    draw();
    toggle.focus();
  };
})();
"""
