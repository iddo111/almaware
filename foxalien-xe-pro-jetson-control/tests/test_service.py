import time
import unittest

from foxalien_control.config import MachineConfig
from foxalien_control.machine import MachineError, MachineService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = MachineService(MachineConfig())
        self.service.connect()

    def tearDown(self):
        if self.service.transport.connected:
            self.service.transport.disconnect()

    def test_jog_updates_simulated_position(self):
        self.service.jog("X", 1.0, 100.0)
        self.assertEqual(self.service.snapshot()["machine"]["work_position"][0], 1.0)

    def test_jog_limit_is_enforced(self):
        with self.assertRaisesRegex(MachineError, "at most"):
            self.service.jog("X", 11.0)

    def test_unlock_and_set_work_zero(self):
        self.service.jog("X", 1.0, 100.0)
        self.service.unlock()
        self.service.set_work_zero()
        self.assertEqual(
            self.service.snapshot()["machine"]["work_position"],
            [0.0, 0.0, 0.0],
        )

    def test_job_requires_all_acknowledgements(self):
        with self.assertRaisesRegex(MachineError, "acknowledgements missing"):
            self.service.start_job("test.nc", "G21\nG90\nG1 X1 F100", {})

    def test_valid_job_streams_to_completion(self):
        approvals = {key: True for key in self.service.REQUIRED_APPROVALS}
        self.service.start_job("test.nc", "G21\nG90\nG1 X1 F100\nM5", approvals)
        deadline = time.time() + 2
        while self.service.job_state == "running" and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.service.job_state, "complete")
        self.assertEqual(self.service.job_progress, 4)


if __name__ == "__main__":
    unittest.main()
