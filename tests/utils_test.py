import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from datetime import datetime, date
from utils import parse_datetime, parse_date

class TestUtils(unittest.TestCase):
    def test_parse_datetime(self):
        self.assertIsNone(parse_datetime(None))
        self.assertIsNone(parse_datetime(""))
        self.assertIsNone(parse_datetime("invalid-date"))
        
        dt = parse_datetime("2026-04-12T15:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.hour, 15)
        
        dt2 = parse_datetime("2026-04-12T15:00:00")
        self.assertEqual(dt2.year, 2026)

    def test_parse_date(self):
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("not-a-date"))
        
        d = parse_date("2026-04-12")
        self.assertIsNotNone(d)
        self.assertEqual(d.year, 2026)
        self.assertEqual(d.month, 4)
        self.assertEqual(d.day, 12)

if __name__ == '__main__':
    unittest.main()
