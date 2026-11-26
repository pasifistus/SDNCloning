from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
import json
import re
from pathlib import Path
from typing import Tuple
#from deepdiff import DeepDiff

URL = "http://127.0.0.1:8080/v1.0/topology/switches" 

class ModularMininet(Mininet):
    def __init__(self, *args, **kwargs):
        self._running = False
        super().__init__(*args, **kwargs)
        self.switch_obj_dpid = {}
        self.mac_to_host = {}

    def start(self):
        super().start()
        self._running = True

    def stop(self):
        self._running = False
        super().stop()

    def addLink(self, node1, node2, port1=None, port2=None, cls=None, **params):
        node1 = self[node1] if isinstance(node1, str) else node1
        node2 = self[node2] if isinstance(node2, str) else node2
        for node, port in ((node1, port1), (node2, port2)):
            if port is not None and port in node.intfs:
                raise ValueError(f"Port {port} on {node.name} is already in use")
        if node1 is node2 and port1 is not None and port1 == port2:
            raise ValueError("A link must connect two different ports")

        link = super().addLink(node1, node2, port1=port1, port2=port2,
                               cls=cls, **params)
        if self._running:
            for interface in (link.intf1, link.intf2):
                switch = interface.node
                if switch in self.switches:
                    switch.attach(interface)
                    if isinstance(switch, OVSSwitch):
                        switch.vsctl("set", "Interface", interface.name,
                                     f"ofport_request={switch.ports[interface]}")
        return link

    def delLink(self, link):
        if link not in self.links:
            return
        if self._running:
            for interface in (link.intf1, link.intf2):
                if interface.node in self.switches:
                    interface.node.detach(interface)
        super().delLink(link)

    def _delete_node_links(self, node):
        for link in list(self.links):
            if node in (link.intf1.node, link.intf2.node):
                self.delLink(link)

    def deleteSwitch(self, dpid) -> bool:
        name = self.switch_obj_dpid.get(dpid)
        switch = self.nameToNode.get(name)
        if switch is None:
            self.switch_obj_dpid.pop(dpid, None)
            return False
        self._delete_node_links(switch)
        self.delSwitch(switch)
        self.switch_obj_dpid.pop(dpid, None)
        return True

    def deleteHost(self, mac) -> bool:
        name = self.mac_to_host.get(mac)
        host = self.nameToNode.get(name)
        if host is None:
            self.mac_to_host.pop(mac, None)
            return False
        self._delete_node_links(host)
        self.delHost(host)
        self.mac_to_host.pop(mac, None)
        return True

    def deleteLinkAtPort(self, switch_name: str, port: int) -> None:
        switch = self.nameToNode.get(switch_name)
        interface = switch.intfs.get(port) if switch is not None else None
        if interface is not None and interface.link is not None:
            self.delLink(interface.link)

    def _switch_for_dpid(self, dpid):
        switch = self.nameToNode.get(self.switch_obj_dpid.get(dpid))
        if switch is None:
            raise ValueError(f"Unknown switch DPID: {dpid}")
        return switch

    def _add_topology_switch(self, dpid):
        name = f"s{int(dpid, 16)}"
        if name in self.nameToNode:
            raise ValueError(f"Switch {name} already exists")
        switch = self.addSwitch(name, dpid=dpid)
        self.switch_obj_dpid[dpid] = name
        if self._running:
            switch.start(self.controllers)
        return switch

    def _add_topology_link(self, metadata):
        src, dst = metadata["src"], metadata["dst"]
        return self.addLink(
            self._switch_for_dpid(src["dpid"]),
            self._switch_for_dpid(dst["dpid"]),
            port1=int(src["port_no"], 16),
            port2=int(dst["port_no"], 16),
            intfName1=src["name"],
            intfName2=dst["name"],
            addr1=src["hw_addr"],
            addr2=dst["hw_addr"]
        )

    def _remove_topology_link(self, metadata):
        src, dst = metadata["src"], metadata["dst"]
        node1 = self.nameToNode.get(self.switch_obj_dpid.get(src["dpid"]))
        node2 = self.nameToNode.get(self.switch_obj_dpid.get(dst["dpid"]))
        if node1 is None or node2 is None:
            return
        interface = node1.intfs.get(int(src["port_no"], 16))
        if interface is None or interface.link is None:
            return
        link = interface.link
        peer = link.intf2 if link.intf1 is interface else link.intf1
        if peer.node is node2 and node2.ports.get(peer) == int(dst["port_no"], 16):
            self.delLink(link)

    def _add_topology_host(self, mac, metadata):
        switch = self._switch_for_dpid(metadata["port"]["dpid"])
        port = int(metadata["port"]["port_no"], 16)
        if port in switch.intfs:
            raise ValueError(f"Port {port} on {switch.name} is already in use")
        index = len(self.hosts) + 1
        while f"h{index}" in self.nameToNode:
            index += 1
        name = f"h{index}"
        ipv4 = metadata["ipv4"]
        host = self.addHost(name, ip=ipv4[0] if ipv4 else None, mac=mac)
        self.mac_to_host[mac] = name
        self.addLink(host, switch, port1=0, port2=port,
                     intfName2=metadata["port"]["name"], addr1=mac,
                     addr2=metadata["port"]["hw_addr"])
        if self._running:
            host.configDefault()
        return host

    def modify(self, changes: dict) -> bool:
        """Apply a verbose DeepDiff using the link-comparison settings in diff.py."""
        additions = {"switches": {}, "hosts": {}}
        removals = {"switches": {}, "hosts": {}}
        for change, items in (("dictionary_item_added", additions),
                              ("dictionary_item_removed", removals)):
            for path, metadata in changes.get(change, {}).items():
                match = re.fullmatch(r"root\['(switches|hosts)'\]\['([^']+)'\]", path)
                if match:
                    section, key = match.groups()
                    items[section][key] = metadata

        for path, metadata in changes.get("iterable_item_removed", {}).items():
            if re.fullmatch(r"root\['links'\]\[\d+\]", path):
                self._remove_topology_link(metadata)
        for mac in removals["hosts"]:
            self.deleteHost(mac)
        for dpid in removals["switches"]:
            self.deleteSwitch(dpid)

        for dpid in additions["switches"]:
            self._add_topology_switch(dpid)
        for path, metadata in changes.get("iterable_item_added", {}).items():
            if re.fullmatch(r"root\['links'\]\[\d+\]", path):
                self._add_topology_link(metadata)
        for mac, metadata in additions["hosts"].items():
            self._add_topology_host(mac, metadata)
        return True


def build(struct: dict) -> ModularMininet:
    net = ModularMininet(controller=RemoteController)

    for dpid in struct["switches"]:
        net._add_topology_switch(dpid)
    for link in struct["links"]:
        net._add_topology_link(link)
    for mac, metadata in struct["hosts"].items():
        net._add_topology_host(mac, metadata)
    return net


def main():
    topology_path = Path(__file__).with_name("topology.json")
    with topology_path.open() as file:
        struct = json.load(file)

    net = build(struct)
    try:
        net.addController(controller=RemoteController)
        net.start()
        CLI(net)
    finally:
        net.stop()



if __name__ == "__main__":
    main()
