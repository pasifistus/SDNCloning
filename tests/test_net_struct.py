from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import Mock, call, patch

from mininet.net import Mininet
from mininet.node import OVSSwitch

from net_struct import build


ROOT = Path(__file__).resolve().parents[1]


def compare(old, new):
    files = [StringIO(json.dumps(old)), StringIO(json.dumps(new))]
    with patch.object(Path, "open", side_effect=files), redirect_stdout(StringIO()):
        return runpy.run_path(str(ROOT / "diff.py"))["diff"]


def dpid(number):
    return f"{number:016x}"


def endpoint(switch, port):
    return {
        "dpid": dpid(switch),
        "port_no": f"{port:08x}",
        "name": f"s{switch}-eth{port}",
        "hw_addr": f"02:00:00:00:{switch:02x}:{port:02x}",
    }


def link(switch1, port1, switch2, port2):
    return {"src": endpoint(switch1, port1), "dst": endpoint(switch2, port2)}


def host(switch, port, ipv4=None):
    return {"ipv4": ipv4 or [], "port": endpoint(switch, port)}


class FakeNode:
    portBase = 0

    def __init__(self, name, **params):
        self.name, self.params = name, params
        self.intfs, self.ports, self.nameToIntf = {}, {}, {}
        self.lifecycle = Mock()
        self.stop = self.lifecycle.stop
        self.terminate = self.lifecycle.terminate
        self.configDefault = self.lifecycle.configDefault

    def newPort(self):
        return max(self.intfs, default=self.portBase - 1) + 1

    def __repr__(self):
        return self.name


class FakeSwitch(FakeNode, OVSSwitch):
    portBase = 1

    def __init__(self, name, **params):
        FakeNode.__init__(self, name, **params)
        self.dpid = params["dpid"]
        self.start = self.lifecycle.start
        self.attach = self.lifecycle.attach
        self.detach = self.lifecycle.detach
        self.vsctl = self.lifecycle.vsctl


class FakeInterface:
    def __init__(self, node, port, name, mac, link):
        self.node, self.name, self.mac, self.link = node, name, mac, link
        node.intfs[port] = self
        node.ports[self] = port
        node.nameToIntf[name] = self

    def delete(self):
        del self.node.intfs[self.node.ports.pop(self)]
        del self.node.nameToIntf[self.name]
        self.link = None


class FakeLink:
    def __init__(self, node1, node2, port1=None, port2=None, **params):
        for index, node, port in ((1, node1, port1), (2, node2, port2)):
            port = node.newPort() if port is None else port
            interface = FakeInterface(
                node, port, params.get(f"intfName{index}", f"{node.name}-eth{port}"),
                params.get(f"addr{index}"), self
            )
            setattr(self, f"intf{index}", interface)
        self.delete = Mock(side_effect=self._delete)

    def _delete(self):
        self.intf1.delete()
        self.intf2.delete()
        self.intf1 = self.intf2 = None


def initialize_network(net, *args, **kwargs):
    net.switches, net.hosts, net.links, net.nameToNode = [], [], [], {}
    net.controllers = [object()]
    net.switch, net.host, net.link, net.intf = FakeSwitch, FakeNode, FakeLink, None
    net.inNamespace = net.autoSetMacs = net.autoPinCpus = False
    net.listenPort = None
    net.nextIP, net.ipBaseNum, net.prefixLen = 1, 0x0a000000, 8


class TopologyChangesTest(unittest.TestCase):
    def setUp(self):
        for name, replacement in (("__init__", initialize_network),
                                  ("start", Mock()), ("stop", Mock())):
            patcher = patch.object(Mininet, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.old = {
            "switches": {dpid(i): {"ports": []} for i in (1, 2, 3)},
            "links": [],
            "hosts": {},
        }

    def test_build_preserves_input_and_normalizes_host_ips(self):
        self.old["links"] = [link(1, 10, 2, 11)]
        self.old["hosts"] = {
            "02:00:00:01:00:01": host(1, 12, ["10.0.0.1", "10.0.0.2"]),
            "02:00:00:01:00:02": host(3, 13),
        }
        original = deepcopy(self.old)
        net = build(self.old)
        self.assertEqual(self.old, original)
        self.assertEqual(net["ts1"].intfs[10].name, "ts1-eth10")
        self.assertEqual(net["ts2"].intfs[11].mac, self.old["links"][0]["dst"]["hw_addr"])
        self.assertEqual(net["th1"].params["ip"], "10.0.0.1")
        self.assertEqual(net["th1"].intfs[0].name, "th1-eth0")
        self.assertEqual(net["ts1"].intfs[12].name, "ts1-eth12")
        self.assertEqual(net["ts1"].intfs[12].mac,
                         self.old["hosts"]["02:00:00:01:00:01"]["port"]["hw_addr"])
        self.assertIsNone(net["th2"].params["ip"])
        net["ts1"].attach.assert_not_called()
        net["th1"].configDefault.assert_not_called()

    def test_live_additions_start_switches_and_configure_hosts(self):
        net = build(self.old)
        net.start()
        new = deepcopy(self.old)
        new["switches"][dpid(4)] = {"ports": []}
        new["links"] = [link(1, 10, 4, 11)]
        mac = "02:00:00:01:00:01"
        new["hosts"][mac] = host(4, 12, ["10.0.0.1"])
        self.assertTrue(net.modify(compare(self.old, new)))
        switch = net["ts4"]
        switch.start.assert_called_once_with(net.controllers)
        self.assertEqual(switch.lifecycle.mock_calls[0], call.start(net.controllers))
        switch.attach.assert_any_call(switch.intfs[11])
        switch.attach.assert_any_call(switch.intfs[12])
        switch.vsctl.assert_any_call("set", "Interface", "ts4-eth11", "ofport_request=11")
        net[net.mac_to_host[mac]].configDefault.assert_called_once_with()
        self.assertTrue(net._running)
        net.stop()
        self.assertFalse(net._running)

    def test_remove_first_parallel_link_and_reversed_endpoints(self):
        self.old["links"] = [link(1, 10, 2, 11), link(1, 12, 2, 13)]
        net = build(self.old)
        net.start()
        first, second = net.links
        new = deepcopy(self.old)
        new["links"].pop(0)
        changes = compare(self.old, new)
        self.assertEqual(set(changes), {"iterable_item_removed"})
        self.assertTrue(net.modify(changes))
        self.assertEqual(net.links, [second])
        first.delete.assert_called_once_with()
        second.delete.assert_not_called()
        for switch in (net["ts1"], net["ts2"]):
            switch.detach.assert_called_once()

        metadata = new["links"][0]
        removal = {"iterable_item_removed": {"root['links'][99]": {
            "src": metadata["dst"], "dst": metadata["src"],
        }}}
        net.modify(removal)
        net.modify(removal)
        self.assertEqual(net.links, [])
        second.delete.assert_called_once_with()

    def test_removal_requires_both_endpoint_ports(self):
        self.old["links"] = [link(1, 10, 2, 11), link(1, 12, 2, 13)]
        net = build(self.old)
        original = list(net.links)
        net.modify({"iterable_item_removed": {"root['links'][0]": link(1, 10, 2, 13)}})
        self.assertEqual(net.links, original)

    def test_replacement_frees_ports_before_adding_new_link(self):
        self.old["links"] = [link(1, 10, 2, 11)]
        net = build(self.old)
        net.start()
        old_link = net.links[0]
        new = deepcopy(self.old)
        new["links"] = [link(1, 10, 3, 12)]
        changes = compare(self.old, new)
        self.assertEqual(set(changes), {"iterable_item_added", "iterable_item_removed"})
        net.modify(changes)
        old_link.delete.assert_called_once_with()
        self.assertEqual(len(net.links), 1)
        self.assertIs(net["ts1"].intfs[10].link, net["ts3"].intfs[12].link)
        self.assertNotIn(11, net["ts2"].intfs)

    def test_reordering_and_nested_changes_are_ignored(self):
        self.old["links"] = [link(1, 10, 2, 11), link(1, 12, 3, 13)]
        net = build(self.old)
        original = list(net.links)
        new = deepcopy(self.old)
        new["links"].reverse()
        changes = compare(self.old, new)
        self.assertFalse(changes)
        self.assertTrue(net.modify(changes))
        self.assertTrue(net.modify({
            "dictionary_item_added": {"root['switches']['0000000000000001']['other']": {}},
            "iterable_item_added": {"root['switches']['0000000000000001']['ports'][0]": {}},
            "iterable_item_removed": {"root['hosts']['mac']['ipv4'][0]": "10.0.0.1"},
        }))
        self.assertEqual(net.links, original)

    def test_combined_removals_keep_unremoved_hosts_disconnected(self):
        self.old["links"] = [link(1, 10, 2, 11)]
        removed_mac, kept_mac = "02:00:00:01:00:01", "02:00:00:01:00:02"
        self.old["hosts"] = {removed_mac: host(2, 1), kept_mac: host(2, 2)}
        net = build(self.old)
        net.start()
        old_links = list(net.links)
        removed_host, removed_switch = net["th1"], net["ts2"]
        new = deepcopy(self.old)
        new["links"] = []
        del new["hosts"][removed_mac]
        del new["switches"][dpid(2)]
        changes = compare(self.old, new)
        net.modify(changes)
        net.modify(changes)
        self.assertNotIn(dpid(2), net.switch_obj_dpid)
        self.assertNotIn(removed_mac, net.mac_to_host)
        self.assertNotIn("ts2", net.nameToNode)
        self.assertNotIn("th1", net.nameToNode)
        self.assertEqual(net[net.mac_to_host[kept_mac]].intfs, {})
        self.assertEqual(net.links, [])
        for old_link in old_links:
            old_link.delete.assert_called_once_with()
        removed_host.stop.assert_called_once_with(deleteIntfs=True)
        removed_switch.stop.assert_called_once_with(deleteIntfs=True)

    def test_switch_removal_preserves_other_host_links(self):
        old = self.old
        old["links"] = [link(3, 2, 2, 3), link(1, 2, 2, 2)]
        old["hosts"] = {
            "02:00:00:01:00:01": host(3, 1),
            "02:00:00:01:00:02": host(2, 1),
            "02:00:00:01:00:03": host(1, 1),
        }
        new = deepcopy(old)
        del new["switches"][dpid(2)]
        new["switches"][dpid(4)] = {"ports": []}
        net = build(old)
        net.modify(compare(old, new))
        self.assertEqual(set(net.switch_obj_dpid), set(new["switches"]))
        self.assertEqual(set(net.mac_to_host), set(new["hosts"]))
        self.assertEqual(len(net.links), 2)
        for mac, metadata in new["hosts"].items():
            if metadata["port"]["dpid"] not in new["switches"]:
                self.assertEqual(net[net.mac_to_host[mac]].intfs, {})

    def test_invalid_additions_do_not_create_links_or_hosts(self):
        self.old["links"] = [link(1, 10, 2, 11)]
        net = build(self.old)
        original = list(net.links)
        for metadata, error in ((link(1, 12, 4, 13), "Unknown switch DPID"),
                                (link(1, 10, 3, 13), "already in use")):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                net.modify({"iterable_item_added": {"root['links'][1]": metadata}})
            self.assertEqual(net.links, original)
        with self.assertRaisesRegex(ValueError, "already in use"):
            net.modify({"dictionary_item_added": {"root['hosts']['mac']": host(1, 10)}})
        self.assertEqual(net.hosts, [])
        self.assertEqual(net.mac_to_host, {})

    def test_returning_switch_keeps_dpid_name(self):
        net = build(self.old)
        net.start()
        self.assertTrue(net.deleteSwitch(dpid(2)))
        self.assertFalse(net.deleteSwitch(dpid(2)))
        net.modify({"dictionary_item_added": {f"root['switches']['{dpid(2)}']": {"ports": []}}})
        self.assertEqual(net.switch_obj_dpid[dpid(2)], "ts2")
        net["ts2"].start.assert_called_once_with(net.controllers)


if __name__ == "__main__":
    unittest.main()
