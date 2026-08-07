import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class TrackerAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        self.addCleanup(os.chdir, self.original_cwd)

    def test_weight_gate_and_balance_logic(self):
        app.ensure_data_file()
        app.save_data({
            "current_balance": 0.0,
            "total_earned_lifetime": 0.0,
            "last_activity_id": "",
            "weight_history": [
                {"date": "2026-07-25", "weight": 220.0},
                {"date": "2026-07-26", "weight": 218.0},
                {"date": "2026-07-27", "weight": 215.0},
                {"date": "2026-07-28", "weight": 213.0},
                {"date": "2026-07-29", "weight": 210.0},
                {"date": "2026-07-30", "weight": 208.0},
                {"date": "2026-07-31", "weight": 206.0},
            ],
            "redeemed_count": 0,
            "collectibles_list": [
                {"id": 1, "name": "Coffee Mug", "cost": 25.0, "status": "locked"},
            ],
        })

        result = app.handle_weight_data({"date": "2026-08-01", "weight": 204.0})
        self.assertEqual(round(result["rolling_average"], 2), 206.29)
        self.assertEqual(result["next_gate"], 205.0)
        self.assertEqual(result["redeemable"], True)
        self.assertEqual(result["current_balance"], 0.0)

    def test_activity_earning_and_budget(self):
        app.ensure_data_file()
        app.save_data({
            "current_balance": 0.0,
            "total_earned_lifetime": 0.0,
            "last_activity_id": "",
            "weight_history": [],
            "redeemed_count": 0,
            "collectibles_list": [],
        })

        result = app.handle_activity_data({
            "type": "ride",
            "distance": 5.0,
            "start_latlng": [1.0, 2.0],
            "end_latlng": [3.0, 4.0],
            "name": "Lunch Ride"
        })

        self.assertEqual(round(result["earnings"], 2), 4.05)
        self.assertEqual(result["budget_a_remaining"], 195.95)
        self.assertEqual(result["budget_b_unlocked"], True)

    def test_build_telegram_payload(self):
        payload = app.build_telegram_payload("hello", "123456")
        self.assertEqual(payload["chat_id"], "123456")
        self.assertEqual(payload["text"], "hello")
        self.assertEqual(payload["parse_mode"], "HTML")


if __name__ == "__main__":
    unittest.main()
