import unittest

import helpers

from ultron.memory.store import Database
from ultron.network import diagnostics, discovery, interfaces, oui
from ultron.network.inventory import NetworkInventory, infer_kind
from ultron.privacy.privacy_mode import PrivacyPolicy

ARP_WINDOWS = """
Interface: 192.168.0.12 --- 0x7
  Endereço IP           Endereço físico       Tipo
  192.168.0.1           a4-2b-b0-11-22-33     dinâmico
  192.168.0.20          b8-27-eb-aa-bb-cc     dinâmico
  192.168.0.255         ff-ff-ff-ff-ff-ff     estático
  224.0.0.22            01-00-5e-00-00-16     estático
"""
PROC_ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.0.1      0x1         0x2         a4:2b:b0:11:22:33     *        eth0
192.168.0.30     0x1         0x0         00:00:00:00:00:00     *        eth0
"""
IP_NEIGH = """192.168.0.1 dev eth0 lladdr a4:2b:b0:11:22:33 REACHABLE
192.168.0.44 dev eth0 lladdr 52:54:00:12:34:56 STALE
192.168.0.50 dev eth0  FAILED
"""


class ScopeTest(unittest.TestCase):
    def test_only_private_local_networks_are_scanned(self):
        scope = discovery.authorized_scope({"ipv4": "192.168.0.12", "subnet": "192.168.0.0/24"})
        self.assertEqual(str(scope), "192.168.0.0/24")
        with self.assertRaises(discovery.ScopeError):
            discovery.authorized_scope({"ipv4": "8.8.8.8", "subnet": "8.8.8.0/24"})
        with self.assertRaises(discovery.ScopeError):
            discovery.authorized_scope(None)

    def test_large_subnets_are_clamped(self):
        scope = discovery.authorized_scope({"ipv4": "10.1.2.3", "subnet": "10.0.0.0/8"}, max_hosts=256)
        self.assertEqual(scope.num_addresses, 256)


class ParsingTest(unittest.TestCase):
    def test_neighbor_tables(self):
        win = discovery.parse_arp_windows(ARP_WINDOWS)
        self.assertEqual(win["192.168.0.1"], "A4:2B:B0:11:22:33")
        self.assertNotIn("192.168.0.255", win, "broadcast ignorado")
        self.assertNotIn("224.0.0.22", win, "multicast ignorado")
        self.assertEqual(set(discovery.parse_proc_net_arp(PROC_ARP)), {"192.168.0.1"})
        neigh = discovery.parse_ip_neigh(IP_NEIGH)
        self.assertEqual(set(neigh), {"192.168.0.1", "192.168.0.44"})

    def test_ping_latency_parsing(self):
        self.assertAlmostEqual(discovery.parse_ping_latency("Resposta de 192.168.0.1: bytes=32 tempo=3ms TTL=64"), 3.0)
        self.assertAlmostEqual(discovery.parse_ping_latency("64 bytes from 1.1.1.1: icmp_seq=1 time=12.4 ms"), 12.4)


class InventoryTest(unittest.TestCase):
    def test_merge_new_online_offline_and_kinds(self):
        db = Database(helpers.temp_dir() / "net.sqlite3")
        inventory = NetworkInventory(db)
        first = inventory.merge_scan({"hosts": [
            {"ip": "192.168.0.1", "mac": "A4:2B:B0:11:22:33", "alive": True},
            {"ip": "192.168.0.20", "mac": "B8:27:EB:AA:BB:CC", "alive": True},
            {"ip": "192.168.0.12", "mac": "", "alive": True},
        ]}, gateway="192.168.0.1", own_ip="192.168.0.12")
        self.assertEqual(len(first["new"]), 3)
        kinds = {d.ip: d.kind for d in inventory.devices()}
        self.assertEqual(kinds["192.168.0.1"], "router")
        self.assertEqual(kinds["192.168.0.20"], "raspberry_pi")
        self.assertEqual(kinds["192.168.0.12"], "this_computer")
        second = inventory.merge_scan({"hosts": [{"ip": "192.168.0.1", "mac": "A4:2B:B0:11:22:33", "alive": True}]},
                                      gateway="192.168.0.1")
        self.assertEqual(second["new"], [])
        self.assertEqual({d.ip for d in second["offline"]}, {"192.168.0.20", "192.168.0.12"})
        db.close()

    def test_vendor_lookup(self):
        self.assertEqual(oui.vendor("B8:27:EB:00:00:01"), "Raspberry Pi")
        self.assertTrue(oui.is_locally_administered("DA:A1:19:00:00:01"))
        self.assertEqual(oui.vendor("DA:A1:19:00:00:01"), "MAC aleatório (privacidade)")
        self.assertEqual(infer_kind("10.0.0.9", "00:0C:29:00:00:01", "", "VMware"), "virtual_machine")


class DiagnosticsTest(unittest.TestCase):
    def test_local_mode_skips_external_checks_and_reports_partial(self):
        snap = {"primary": {"name": "eth0", "ipv4": "192.168.0.12"}, "gateway": None, "dns": ["1.1.1.1"]}
        report = diagnostics.run(snap, external_allowed=lambda purpose: False)
        names = {c["name"]: c["status"] for c in report["checks"]}
        self.assertEqual(names["dns"], "SKIPPED")
        self.assertEqual(names["internet"], "SKIPPED")
        self.assertIn(report["overall"], ("PARTIAL", "FAIL", "DEGRADED"))
        self.assertNotEqual(report["overall"], "OK", "verificações puladas nunca resultam em OK")

    def test_privacy_local_mode_blocks_automatic_external_connections(self):
        settings = helpers.make_settings(privacy_mode="local")
        policy = PrivacyPolicy(lambda: settings)
        self.assertFalse(policy.allow_external("teste automático").allowed)
        self.assertTrue(policy.allow_external("pedido explícito", explicit=True).allowed)
        policy.strict_block = True
        self.assertFalse(policy.allow_external("pedido explícito", explicit=True).allowed)


class InterfacesTest(unittest.TestCase):
    def test_real_snapshot_has_expected_shape(self):
        snap = interfaces.snapshot(include_dns=True, include_wifi=False)
        for key in ("interfaces", "primary", "gateway", "dns", "online"):
            self.assertIn(key, snap)
        self.assertTrue(interfaces.is_private("192.168.1.10"))
        self.assertFalse(interfaces.is_private("8.8.8.8"))
        self.assertIsInstance(interfaces.signature(snap), tuple)


if __name__ == "__main__":
    unittest.main()
