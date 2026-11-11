from mininet.net import Mininet
from mininet.node import RemoteController

import time
import urllib.request
import subprocess
import json

URL = "http://127.0.0.1:8080/v1.0/topology/switches"    

# Start a network with one switch and one host
net = Mininet(controller=RemoteController)
net.addController("c0")  # Ryu
s1 = net.addSwitch("s1")
h1 = net.addHost("h1")
net.addLink(h1, s1)
net.start()

# Add a new host while the network is running
h2 = net.addHost("h2")
link = net.addLink(h2, s1)
s1.attach(link.intf2)  # tell the running switch about the new port
h2.configDefault()     # give h2 its IP address

net.pingAll()

try:
        urllib.request.urlopen(URL, timeout=5)
        print("Pinged Ryu controller: OK")
        result = subprocess.run(
        ["curl", "-s", URL],
        capture_output=True, text=True
        )

        data = json.loads(result.stdout)
        print(json.dumps(data, indent=4))

except Exception as e:
        print("Pinged Ryu controller: FAILED", e)
net.stop()

## to run: sudo python3 add_to_mininet.py
