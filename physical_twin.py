from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI

#            s1
#         /  |  \
#       s2   s3   s4
#      / \   / \   / \
#     h1 h2 h3 h4 h5 h6

net = Mininet(controller=RemoteController, switch=OVSKernelSwitch)
net.addController("c0", ip="127.0.0.1", port=6653)  # Ryu

# Switches
s1 = net.addSwitch("s1", protocols="OpenFlow13")
s2 = net.addSwitch("s2", protocols="OpenFlow13")
s3 = net.addSwitch("s3", protocols="OpenFlow13")
s4 = net.addSwitch("s4", protocols="OpenFlow13")

# Hosts
h1 = net.addHost("h1", ip="10.0.0.1/24")
h2 = net.addHost("h2", ip="10.0.0.2/24")
h3 = net.addHost("h3", ip="10.0.0.3/24")
h4 = net.addHost("h4", ip="10.0.0.4/24")
h5 = net.addHost("h5", ip="10.0.0.5/24")
h6 = net.addHost("h6", ip="10.0.0.6/24")

# Links between switches
net.addLink(s1, s2)
net.addLink(s1, s3)
net.addLink(s1, s4)

# Links from hosts to switches
net.addLink(h1, s2)
net.addLink(h2, s2)
net.addLink(h3, s3)
net.addLink(h4, s3)
net.addLink(h5, s4)
net.addLink(h6, s4)

net.start()

# Ryu only finds hosts after they send traffic
net.pingAll()

CLI(net)
net.stop()

## to run:
## terminal 1: ryu-manager --observe-links ryu.app.rest_topology ryu.app.simple_switch_13 ryu.app.ofctl_rest
## terminal 2: sudo python3 physical_twin.py
## terminal 3: python3 ping_ryu.py
