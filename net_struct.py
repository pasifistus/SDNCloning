from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
import json
from pathlib import Path

URL = "http://127.0.0.1:8080/v1.0/topology/switches" 

def build(struct: dict) -> Mininet:
    net = Mininet(controller=RemoteController)
    
    #adding switches
    switch_obj_dpid = {}
    for index, dpid in enumerate(struct["switches"].keys(), start=1):
        net.addSwitch(
            f"s{index}",
            dpid=dpid)
        switch_obj_dpid[dpid] = f"s{index}"
    
    
    #adding links
    src: dict
    dst: dict
    for link in struct["links"]:
        src = link['src']
        dst = link['dst']
        net.addLink(
            node1= switch_obj_dpid[src.pop("dpid", None)],
            node2= switch_obj_dpid[dst.pop("dpid", None)],
            port1= int(src["port_no"]),
            port2= int(dst["port_no"]),
            intfName1=src["name"],
            intfName2=dst["name"],
            addr1=src["hw_addr"],
            addr2=dst["hw_addr"]
            )
        
        
    mac_to_host = {}
    for index, (mac, meta) in enumerate(struct["hosts"].items(), start=1):
        mac_to_host["mac"] = f"h{index}"
        hosttemp = net.addHost(
            f"h{index}",
            ip=meta["ipv4"],
            mac=mac
        )
        
        net.addLink(
            hosttemp,
            switch_obj_dpid[meta["port"]["dpid"]],
            port1=0,
            port2=int(meta["port"]["port_no"])
        )
        

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
