import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vpn_hotspot import backend  # noqa: E402


class SplitTerseTest(unittest.TestCase):
    def test_plain_fields(self):
        self.assertEqual(backend.split_terse("wlp1s0:wifi:connected"), ["wlp1s0", "wifi", "connected"])

    def test_escaped_colon_stays_in_field(self):
        self.assertEqual(backend.split_terse(r"My\:Net:wifi"), ["My:Net", "wifi"])

    def test_escaped_backslash(self):
        self.assertEqual(backend.split_terse(r"a\\b:c"), ["a\\b", "c"])


class RouteTest(unittest.TestCase):
    def test_vpn_route(self):
        out = "1.1.1.1 from 10.42.0.50 via 198.18.0.2 dev FlClash table 2022\n    cache iif wlp1s0\n"
        self.assertEqual(backend.parse_route_device(out), "FlClash")

    def test_direct_route(self):
        out = "1.1.1.1 from 10.42.0.50 via 192.168.1.1 dev eno1\n    cache iif wlp1s0\n"
        self.assertEqual(backend.parse_route_device(out), "eno1")

    def test_error_output(self):
        self.assertIsNone(backend.parse_route_device("RTNETLINK answers: Network is unreachable"))

    def test_probe_address_skips_own_ip(self):
        self.assertEqual(backend.probe_address("10.42.0.1/24"), "10.42.0.50")


class NeighborTest(unittest.TestCase):
    def test_keeps_live_devices_only(self):
        out = (
            "10.42.0.23 lladdr aa:bb:cc:dd:ee:01 REACHABLE\n"
            "10.42.0.40 lladdr aa:bb:cc:dd:ee:02 STALE\n"
            "10.42.0.41 FAILED\n"
            "10.42.0.42 lladdr aa:bb:cc:dd:ee:03 FAILED\n"
        )
        devices = backend.parse_neighbors(out)
        self.assertEqual([d.ip for d in devices], ["10.42.0.23", "10.42.0.40"])
        self.assertEqual(devices[0].mac, "aa:bb:cc:dd:ee:01")


class ValidateTest(unittest.TestCase):
    def test_ok(self):
        self.assertIsNone(backend.validate_wifi("VPN-Hotspot", "longenough"))

    def test_short_password(self):
        self.assertIn("Password", backend.validate_wifi("VPN-Hotspot", "short"))

    def test_empty_ssid(self):
        self.assertIn("name", backend.validate_wifi("", "longenough"))

    def test_generated_password_is_valid(self):
        self.assertIsNone(backend.validate_wifi("x", backend.generate_password()))


if __name__ == "__main__":
    unittest.main()
