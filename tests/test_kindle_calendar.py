from datetime import date
import socket
import unittest
from unittest.mock import patch

from epub_browser.kindle_calendar import calendar_events, calendar_url, load_calendar_events


class KindleCalendarTests(unittest.TestCase):
    def test_subscription_normalizes_webcal_and_rejects_private_destinations(self):
        self.assertEqual(
            calendar_url("webcal://calendar.example.com/feed.ics?key=abc"),
            "https://calendar.example.com/feed.ics?key=abc",
        )
        for value in (
            "https://127.0.0.1/calendar", "https://[::1]/calendar",
            "https://[::ffff:192.168.1.1]/calendar", "https://192.168.0.1/feed.ics",
            "http://calendar.example.com", "https://calendar.example.com:8080",
            "https://user:password@calendar.example.com",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calendar_url(value)

    def test_dns_results_with_a_private_address_are_rejected_before_connection(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443)),
        ]
        with patch("epub_browser.kindle_calendar.socket.getaddrinfo", return_value=addresses), patch(
            "epub_browser.kindle_calendar._CalendarConnection"
        ) as connect:
            events = load_calendar_events("reader", "https://mixed.example.com/feed.ics", 1)
        self.assertIsNone(events)
        connect.assert_not_called()

    def test_calendar_keeps_all_day_dates_and_expands_recurring_events(self):
        feed = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//EPUB Browser//Calendar Test//EN
BEGIN:VEVENT
UID:reading-group
DTSTART;VALUE=DATE:20261112
DTEND;VALUE=DATE:20261113
RRULE:FREQ=DAILY;COUNT=3
EXDATE;VALUE=DATE:20261113
SUMMARY:Reading group
END:VEVENT
END:VCALENDAR
"""
        self.assertEqual(
            calendar_events(feed, date(2026, 11, 12)),
            [
                {"start": "2026-11-12", "end": "2026-11-13", "title": "Reading group"},
                {"start": "2026-11-14", "end": "2026-11-15", "title": "Reading group"},
            ],
        )
