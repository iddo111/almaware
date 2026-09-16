import unittest

from foxalien_control.gcode import normalize_line, validate_program


class GcodeTests(unittest.TestCase):
    def test_normalizes_comments_and_whitespace(self):
        self.assertEqual(normalize_line(" g1 x10 (move) y20 ; end"), "G1X10Y20")

    def test_accepts_linear_dry_motion_program(self):
        result = validate_program("G21\nG90\nG0 X10 Y10\nG1 X20 Y20 F300\nM5")
        self.assertTrue(result.valid, result.as_dict())
        self.assertEqual(result.extents["x"], [0.0, 20.0])

    def test_rejects_spindle_and_speed(self):
        result = validate_program("G21\nG90\nM3 S10000\nG1 X10 F200")
        self.assertFalse(result.valid)
        messages = " ".join(issue.message for issue in result.issues)
        self.assertIn("Spindle", messages)

    def test_rejects_arc_in_recovery_build(self):
        result = validate_program("G21\nG90\nG2 X10 Y10 I5 J0 F200")
        self.assertFalse(result.valid)
        self.assertTrue(any("Arc moves" in issue.message for issue in result.issues))

    def test_rejects_excess_travel_span(self):
        result = validate_program("G21\nG90\nG0 X0\nG1 X401 F200")
        self.assertFalse(result.valid)
        self.assertTrue(any("exceeds" in issue.message for issue in result.issues))

    def test_rejects_excess_feed(self):
        result = validate_program("G21\nG90\nG1 X10 F5001")
        self.assertFalse(result.valid)

    def test_rejects_system_command(self):
        result = validate_program("$100=250")
        self.assertFalse(result.valid)

    def test_requires_explicit_motion_and_modal_setup(self):
        result = validate_program("X10 F100")
        self.assertFalse(result.valid)
        messages = " ".join(issue.message for issue in result.issues)
        self.assertIn("explicitly include G0 or G1", messages)
        self.assertIn("Set G20 or G21", messages)

    def test_rejects_unknown_words_and_long_dwell(self):
        unknown = validate_program("G21\nG90\nG1 X1 A2 F100")
        dwell = validate_program("G21\nG90\nG4 P3")
        self.assertFalse(unknown.valid)
        self.assertFalse(dwell.valid)


if __name__ == "__main__":
    unittest.main()
