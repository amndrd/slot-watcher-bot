"""Parser behaviour, including the traps found on real booking sites."""

import unittest
from datetime import date

from slotwatcher.config import ParseRules, WatchRules, parse_interval, ConfigError
from slotwatcher.parser import Parser, select

TODAY = date(2026, 8, 20)


def parse(text, today=TODAY, **rules):
    return Parser(ParseRules.from_dict(rules)).parse(text, today=today)


class TestAvailability(unittest.TestCase):
    def test_times_under_a_date_mean_available(self):
        slots = parse("9/09/2026\n07:00\n08:00\n")
        self.assertEqual([s.label for s in slots], ["9/09/2026"])
        self.assertEqual(slots[0].times, ("07:00", "08:00"))

    def test_full_marker_hides_a_date(self):
        slots = parse("20/08/2026\n Volzet\n", full_markers=["Volzet"])
        self.assertEqual(slots, [])

    def test_neighbouring_full_day_does_not_hide_a_free_one(self):
        # The bug that mattered most: a windowed search around the date picked up
        # the previous day's "Volzet" and silently swallowed a real opening.
        text = "20/08/2026\n Volzet\n21/08/2026\n10:00\n12:00\n"
        slots = parse(text, full_markers=["Volzet"])
        self.assertEqual([s.label for s in slots], ["21/08/2026"])

    def test_a_date_is_not_matched_inside_a_longer_one(self):
        # "1/08/2026" must not match within "21/08/2026".
        slots = parse("21/08/2026\n Volzet\n", full_markers=["Volzet"])
        self.assertEqual(slots, [])
        slots = parse("31/08/2026\n09:00\n")
        self.assertEqual([s.label for s in slots], ["31/08/2026"])

    def test_past_dates_are_ignored(self):
        self.assertEqual(parse("1/11/2018\n09:00\n"), [])

    def test_start_marker_crops_boilerplate(self):
        text = "Legal notice, valid since 1/01/2030 09:00\nCALENDAR\n9/09/2026\n07:00\n"
        slots = parse(text, start_marker="CALENDAR")
        self.assertEqual([s.label for s in slots], ["9/09/2026"])

    def test_free_markers_without_times(self):
        slots = parse("9/09/2026\nAvailable\n",
                      require_times=False, free_markers=["Available"])
        self.assertEqual([s.label for s in slots], ["9/09/2026"])
        self.assertEqual(slots[0].times, ())

    def test_date_orders(self):
        self.assertEqual(parse("09/12/2026\n07:00\n", date_order="mdy")[0].day,
                         date(2026, 9, 12))
        self.assertEqual(parse("2026-09-12\n07:00\n", date_order="ymd")[0].day,
                         date(2026, 9, 12))

    def test_impossible_date_is_skipped(self):
        self.assertEqual(parse("32/13/2026\n07:00\n"), [])

    def test_hour_separator_variant(self):
        self.assertEqual(parse("9/09/2026\n07h30\n")[0].times, ("07h30",))


class TestSelection(unittest.TestCase):
    def setUp(self):
        self.slots = parse("21/08/2026\n10:00\n9/09/2026\n07:00\n10/09/2026\n08:00\n")

    def test_scope_all(self):
        watch = WatchRules.from_dict({"scope": "all"})
        self.assertEqual(len(select(self.slots, watch)), 3)

    def test_scope_month(self):
        watch = WatchRules.from_dict({"scope": "month", "year": 2026, "month": 9})
        self.assertEqual([s.label for s in select(self.slots, watch)],
                         ["9/09/2026", "10/09/2026"])

    def test_scope_days(self):
        watch = WatchRules.from_dict(
            {"scope": "days", "year": 2026, "month": 9, "days": [10]})
        self.assertEqual([s.label for s in select(self.slots, watch)], ["10/09/2026"])


class TestKeys(unittest.TestCase):
    def test_keys_are_per_time_so_a_new_hour_alerts(self):
        first = parse("9/09/2026\n07:00\n")[0].keys()
        second = parse("9/09/2026\n07:00\n08:00\n")[0].keys()
        self.assertEqual(second - first, {"9/09/2026|08:00"})


class TestInterval(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(parse_interval("30sec"), 30)
        self.assertEqual(parse_interval("5min"), 300)
        self.assertEqual(parse_interval(90), 90)

    def test_too_fast_is_refused(self):
        with self.assertRaises(ConfigError):
            parse_interval("10")

    def test_nonsense_is_refused(self):
        with self.assertRaises(ConfigError):
            parse_interval("whenever")


class TestConfigValidation(unittest.TestCase):
    def test_month_scope_needs_a_month(self):
        with self.assertRaises(ConfigError):
            WatchRules.from_dict({"scope": "month"})

    def test_unparseable_combination_is_refused(self):
        with self.assertRaises(ConfigError):
            ParseRules.from_dict({"require_times": False})


if __name__ == "__main__":
    unittest.main()
