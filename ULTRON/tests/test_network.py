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

    def test_ipv6_neighbors_linux_and_windows(self):
        linux = discovery.parse_ip6_neigh(
            "fe80::1 dev eth0 lladdr a4:2b:b0:11:22:33 router REACHABLE\n"
            "fe80::2 dev eth0 lladdr b8:27:eb:aa:bb:cc STALE\n"
            "fe80::3 dev eth0  FAILED\n"
            "ff02::1 dev eth0 lladdr 33:33:00:00:00:01 NOARP\n")
        self.assertEqual(linux, {"A4:2B:B0:11:22:33": ["fe80::1"], "B8:27:EB:AA:BB:CC": ["fe80::2"]})
        windows = discovery.parse_netsh_ipv6_neighbors(
            "Interface 7: Wi-Fi\n\nEndereço da Internet    Endereço Físico   Tipo\n"
            "fe80::1%7               a4-2b-b0-11-22-33  Acessível (Roteador)\n"
            "fe80::9                 00-00-00-00-00-00  Inacessível\n"
            "ff02::1                 33-33-00-00-00-01  Permanente\n")
        self.assertEqual(windows, {"A4:2B:B0:11:22:33": ["fe80::1"]})

    def test_ssdp_is_restricted_to_the_same_private_ip(self):
        import ipaddress
        from ultron.network import ssdp
        net = ipaddress.IPv4Network("192.168.0.0/24")
        self.assertEqual(ssdp.safe_location("http://192.168.0.5:49152/desc.xml", "192.168.0.5", net),
                         "http://192.168.0.5:49152/desc.xml")
        self.assertIsNone(ssdp.safe_location("http://192.168.0.9/desc.xml", "192.168.0.5", net), "outro IP")
        self.assertIsNone(ssdp.safe_location("http://8.8.8.8/desc.xml", "8.8.8.8", net), "fora da rede")
        self.assertIsNone(ssdp.safe_location("https://192.168.0.5/x", "192.168.0.5", net), "só http local")
        xml = (b'<root xmlns="urn:schemas-upnp-org:device-1-0"><device><friendlyName>TV Sala</friendlyName>'
               b'<manufacturer>Samsung</manufacturer><modelName>QN55</modelName></device></root>')
        self.assertEqual(ssdp.parse_description(xml), {"friendly_name": "TV Sala", "manufacturer": "Samsung",
                                                       "model": "QN55"})
        bomb = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><root>&lol;</root>'
        self.assertEqual(ssdp.parse_description(bomb), {}, "XML com entidades é recusado")

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
        # uma varredura sem resposta NÃO prova saída da rede: fica "desconhecido", não "ausente"
        self.assertEqual({d.ip for d in second["unknown"]}, {"192.168.0.20", "192.168.0.12"})
        self.assertEqual(second["absent"], [])
        third = inventory.merge_scan({"hosts": [{"ip": "192.168.0.1", "mac": "A4:2B:B0:11:22:33", "alive": True}]},
                                     gateway="192.168.0.1")
        self.assertEqual({d.ip for d in third["absent"]}, {"192.168.0.20", "192.168.0.12"})
        self.assertEqual(inventory.count("absent"), 2)
        db.close()

    def test_passive_read_never_marks_absence_and_user_fields_survive(self):
        db = Database(helpers.temp_dir() / "net.sqlite3")
        inventory = NetworkInventory(db)
        scan = {"network": "192.168.0.0/24", "hosts": [
            {"ip": "192.168.0.20", "mac": "B8:27:EB:AA:BB:CC", "alive": True, "methods": ["icmp", "arp"]},
            {"ip": "192.168.0.30", "mac": "", "alive": True, "methods": ["icmp"]}]}
        inventory.merge_scan(scan)
        key = inventory.find("192.168.0.20").key
        inventory.update(key, alias="Servidor", notes="fica na estante", trusted=True)
        for _ in range(3):
            inventory.merge_scan({"network": "192.168.0.0/24", "passive": True, "hosts": []})
        device = inventory.get(key)
        self.assertEqual(device.status, "online", "leitura passiva não prova ausência")
        self.assertEqual((device.alias, device.notes, device.trusted), ("Servidor", "fica na estante", True))
        self.assertGreaterEqual(device.confidence, 0.9)
        # o aparelho sem MAC ganha MAC depois: o registro migra sem duplicar
        inventory.merge_scan({"network": "192.168.0.0/24", "hosts": [
            {"ip": "192.168.0.30", "mac": "11:22:33:44:55:66", "alive": True, "methods": ["icmp", "arp"]},
            {"ip": "192.168.0.20", "mac": "B8:27:EB:AA:BB:CC", "alive": True, "methods": ["icmp"]}]})
        self.assertEqual(len([d for d in inventory.devices() if d.ip == "192.168.0.30"]), 1)
        self.assertEqual(inventory.get(key).alias, "Servidor", "varredura nunca apaga dados do usuário")
        with self.assertRaises(Exception):
            inventory.update(key, notes="a senha do roteador é 1234")
        # outra rede: não observável daqui → desconhecido, nunca ausente
        inventory.merge_scan({"network": "10.0.0.0/24", "hosts": []})
        inventory.merge_scan({"network": "10.0.0.0/24", "hosts": []})
        self.assertEqual(inventory.get(key).status, "unknown")
        db.close()

    def test_unknown_fields_stay_empty_and_export(self):
        db = Database(helpers.temp_dir() / "net.sqlite3")
        inventory = NetworkInventory(db)
        inventory.merge_scan({"network": "192.168.0.0/24", "hosts": [
            {"ip": "192.168.0.40", "mac": "", "alive": True, "methods": ["icmp"]},
            {"ip": "192.168.0.41", "mac": "DA:A1:19:00:00:01", "alive": False, "methods": ["arp"]}]})
        no_mac = inventory.find("192.168.0.40")
        self.assertEqual((no_mac.mac, no_mac.vendor, no_mac.hostname), ("", "", ""), "nada é inventado")
        random_mac = inventory.find("192.168.0.41")
        self.assertEqual(random_mac.vendor_source, "local_admin")
        csv_text = inventory.export("csv")
        self.assertIn("192.168.0.40", csv_text)
        self.assertIn("ipv6", csv_text.splitlines()[0])
        md = inventory.export("md")
        self.assertIn("não identifica quem o usa", md)
        db.close()

    def test_observation_categories_gateway_and_administration(self):
        import time as _time
        from unittest import mock

        from ultron.network import inventory as inventory_module

        db = Database(helpers.temp_dir() / "net.sqlite3")
        inventory = NetworkInventory(db)
        inventory.merge_scan({"network": "192.168.0.0/24", "interface": "Wi-Fi", "hosts": [
            {"ip": "192.168.0.1", "mac": "A4:2B:B0:11:22:33", "alive": True, "methods": ["icmp", "arp"]},
            {"ip": "192.168.0.12", "mac": "", "alive": True, "methods": ["self"]},
            {"ip": "192.168.0.20", "mac": "B8:27:EB:AA:BB:CC", "alive": True, "methods": ["icmp", "arp"]},
            {"ip": "192.168.0.60", "mac": "", "alive": True, "methods": ["ssdp"],
             "extra": {"friendly_name": "TV da sala"}}]}, gateway="192.168.0.1", own_ip="192.168.0.12")
        by_ip = {d.ip: d.to_dict() for d in inventory.devices()}
        self.assertEqual(by_ip["192.168.0.12"]["observation"], "self")
        self.assertEqual(by_ip["192.168.0.20"]["observation"], "recent")
        self.assertEqual(by_ip["192.168.0.60"]["observation"], "inferred", "só anúncio SSDP: presença inferida")
        self.assertIn("MAC", by_ip["192.168.0.60"]["missing"])
        self.assertTrue(by_ip["192.168.0.1"]["is_gateway"])
        self.assertFalse(by_ip["192.168.0.20"]["is_gateway"])
        self.assertEqual(by_ip["192.168.0.20"]["interface"], "Wi-Fi")
        self.assertIn("SUAS credenciais", by_ip["192.168.0.1"]["administration"])
        self.assertIn("não acessa, não controla", by_ip["192.168.0.20"]["administration"])
        self.assertIn("Windows", by_ip["192.168.0.12"]["administration"])
        # 20 minutos sem nova observação: deixa de ser "respondeu recentemente"
        later = _time.time() + 20 * 60
        with mock.patch.object(inventory_module.time, "time", return_value=later):
            stale = inventory.find("192.168.0.20").to_dict()
        self.assertEqual(stale["observation"], "known")
        for _ in range(2):                                   # duas varreduras completas sem resposta
            inventory.merge_scan({"network": "192.168.0.0/24", "hosts": [
                {"ip": "192.168.0.1", "mac": "A4:2B:B0:11:22:33", "alive": True, "methods": ["icmp", "arp"]}]},
                gateway="192.168.0.1")
        self.assertEqual(inventory.find("192.168.0.20").to_dict()["observation"], "no_response")
        md = inventory.export("md")
        self.assertIn("Descobrir não é administrar", md)
        self.assertIn("desconhecido", md, "o que não se sabe aparece como desconhecido")
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
