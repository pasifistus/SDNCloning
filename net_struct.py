from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.cli import CLI

def build(struct: dict) -> Mininet:
    net = Mininet(controller=RemoteController)
    
    #adding switches
    switch_obj_dpid = dict
    for index, dpid in enumerate(struct["switches"].keys(), start=1):
        net.addSwitch(
            f"s{index}",
            dpid=dpid)
        switch_obj_dpid[dpid] = f"s{index}"
    
    
    #adding links
    src: dict
    dst: dict
    for src, dst in struct["links"].values():
        net.addLink(
            node1= switch_obj_dpid[src.pop("dpid", None)],
            node2= switch_obj_dpid[dst.pop("dpid", None)],
            port1= src,
            port2= dst
            )
        
    
    
       
    return net

