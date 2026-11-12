"""Read per-account iCalendar feeds without allowing access to private hosts."""

from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from gzip import GzipFile
from http.client import HTTPException, HTTPSConnection
from io import BytesIO
from ipaddress import ip_address
import re
import socket
import ssl
from threading import Timer
from urllib.parse import urljoin, urlsplit, urlunsplit
from zlib import error as CompressionError

from icalendar import Calendar
import recurring_ical_events


CALENDAR_REFRESH_SECONDS = 600
CALENDAR_URL_MAX_LENGTH = 2048
_MAX_FEED_BYTES = 512 * 1024
_MAX_EVENTS = 250
_TIMEOUT = 6


def _public_address(address):
    return (
        address.is_global and not address.is_multicast and not address.is_reserved
        and not getattr(address, "ipv4_mapped", None)
        and not getattr(address, "sixtofour", None)
        and not getattr(address, "teredo", None)
    )


def calendar_url(value):
    """Accept direct HTTPS feeds and the equivalent webcal subscription URL."""
    if not isinstance(value, str) or len(value) > CALENDAR_URL_MAX_LENGTH:
        raise ValueError("Invalid calendar URL")
    value = value.strip()
    if not value:
        return ""
    if not value.isascii() or re.search(r"[\x00-\x20\x7f\\]", value):
        raise ValueError("Invalid calendar URL")
    parsed = urlsplit(value)
    host = parsed.hostname
    if (
        parsed.scheme not in {"https", "webcal"} or not host or parsed.fragment
        or parsed.username is not None or parsed.port not in (None, 443)
        or "%" in host
    ):
        raise ValueError("Invalid calendar URL")
    try:
        address = ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or "." not in host:
            raise ValueError("Invalid calendar host") from None
    else:
        if not _public_address(address):
            raise ValueError("Invalid calendar host")
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


class _CalendarConnection(HTTPSConnection):
    def __init__(self, host, target):
        super().__init__(host, 443, timeout=_TIMEOUT, context=ssl.create_default_context())
        self.target = target

    def connect(self):
        # Connect to the vetted address directly. The original name is used for
        # TLS and Host, but cannot trigger a second DNS lookup.
        family, socktype, protocol, _, address = self.target
        with socket.socket(family, socktype, protocol) as raw:
            raw.settimeout(self.timeout)
            raw.connect(address)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _download(url):
    parsed = urlsplit(url)
    targets = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not targets or any(not _public_address(ip_address(target[4][0])) for target in targets):
        raise ValueError("Invalid calendar host")
    # Prefer IPv4 for installations without IPv6 routing.
    target = next((target for target in targets if target[0] == socket.AF_INET), targets[0])
    connection = _CalendarConnection(parsed.hostname, target)
    try:
        connection.connect()
        transport = connection.sock

        def stop_download():
            with suppress(OSError):
                transport.shutdown(socket.SHUT_RDWR)

        # A socket inactivity timeout alone cannot stop a server that trickles bytes.
        timer = Timer(_TIMEOUT, stop_download)
        timer.daemon = True
        timer.start()
        try:
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            connection.request("GET", path, headers={
                "Accept": "text/calendar", "Accept-Encoding": "identity",
            })
            with connection.getresponse() as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if location:
                        return None, calendar_url(urljoin(url, location))
                if response.status != 200:
                    raise ValueError("Calendar request failed")
                payload = response.read(_MAX_FEED_BYTES + 1)
                if len(payload) > _MAX_FEED_BYTES:
                    raise ValueError("Calendar exceeded its download limit")
                if payload.startswith(b"\x1f\x8b"):
                    with GzipFile(fileobj=BytesIO(payload)) as compressed:
                        payload = compressed.read(_MAX_FEED_BYTES + 1)
                    if len(payload) > _MAX_FEED_BYTES:
                        raise ValueError("Calendar exceeded its decoded size limit")
                return payload, None
        finally:
            timer.cancel()
    finally:
        connection.close()


def _fetch_calendar(url):
    for _ in range(3):
        payload, redirect = _download(url)
        if redirect is None:
            return payload
        url = redirect
    raise ValueError("Too many calendar redirects")


def _event_date(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value.isoformat()


def calendar_events(payload, today):
    calendar = Calendar.from_ical(payload)
    # Sub-daily schedules are not suitable for a small e-ink agenda. In
    # particular, expanding a secondly recurrence can exhaust server memory.
    components = []
    for component in calendar.subcomponents:
        if component.name == "VEVENT":
            rule = component.get("RRULE")
            if rule and (
                any(str(freq).upper() in {"SECONDLY", "MINUTELY", "HOURLY"}
                    for freq in rule.get("FREQ", ()))
                or any(key in rule for key in ("BYHOUR", "BYMINUTE", "BYSECOND"))
            ):
                continue
        components.append(component)
    calendar.subcomponents = components
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    events = recurring_ical_events.of(calendar, skip_bad_series=True).between(
        month_start - timedelta(days=1), next_month + timedelta(days=8)
    )
    result = []
    for event in events:
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start = event.get("DTSTART")
        end = event.get("DTEND")
        if start is None or not isinstance(start.dt, date):
            continue
        result.append({
            "start": _event_date(start.dt),
            "end": _event_date(end.dt) if end is not None and isinstance(end.dt, date) else "",
            "title": str(event.get("SUMMARY", ""))[:300],
        })
    return sorted(result, key=lambda event: event["start"])[:_MAX_EVENTS]


@lru_cache(maxsize=96)
def load_calendar_events(user_id, url, refresh_window):
    """Cache a short rolling agenda for this account and exact feed URL."""
    try:
        payload = _fetch_calendar(calendar_url(url))
        return calendar_events(payload, datetime.now(timezone.utc).date())
    except (HTTPException, OSError, ValueError, TypeError, OverflowError, KeyError, EOFError, CompressionError):
        # Provider URLs can contain private subscription keys. Keep them out of
        # errors and logs.
        return None
