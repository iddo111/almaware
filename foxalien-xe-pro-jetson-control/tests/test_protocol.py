import unittest

from foxalien_control.protocol import parse_status_report


class ProtocolTests(unittest.TestCase):
    def test_parses_work_position_and_feed(self):
        status = parse_status_report("<Idle|WPos:1.000,2.000,-3.000|FS:120,0|Pn:XYZ>")
        self.assertEqual(status.state, "Idle")
        self.assertEqual(status.work_position, [1.0, 2.0, -3.0])
        self.assertEqual(status.feed, 120.0)
        self.assertEqual(status.pins, "XYZ")

    def test_computes_work_position_from_machine_and_offset(self):
        status = parse_status_report("<Run|MPos:10,20,30|WCO:1,2,3|F:100>")
        self.assertEqual(status.work_position, [9.0, 18.0, 27.0])

    def test_rejects_non_status_line(self):
        with self.assertRaises(ValueError):
            parse_status_report("ok")


if __name__ == "__main__":
    unittest.main()
