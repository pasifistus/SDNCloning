import time
import subprocess
import json
import os
from datetime import datetime

URL = "http://127.0.0.1:8080/v1.0/topology/"
endpoints = ["switches", "links", "hosts"]
state_json = "topology.json"


if os.path.exists(state_json):
    with open(state_json) as f:
        state = json.load(f)
else:
    state = {}

state.setdefault("timestamp", None)
state.setdefault("switches", {})
state.setdefault("links", {})
state.setdefault("hosts", {})


def get_switches(data):
    switches = {}
    for switch in data:
        switches[switch["dpid"]] = {
            "ports": [
                {
                    "port_no": port["port_no"],
                    "name": port["name"],
                    "hw_addr": port["hw_addr"],
                }
                for port in switch["ports"]
            ]
        }
    # Replace the old switches so removed switches disappear too
    state["switches"] = switches

def port_info(port):
    return {
        "dpid": port["dpid"],
        "port_no": port["port_no"],
        "hw_addr": port["hw_addr"],
        "name": port["name"],
    }


def get_links(data):
    links = []
    seen = []

    for link in data:
        src = link["src"]
        dst = link["dst"]

        this_way = (src["dpid"], src["port_no"], dst["dpid"], dst["port_no"])
        other_way = (dst["dpid"], dst["port_no"], src["dpid"], src["port_no"])

        if other_way in seen:
            continue
        seen.append(this_way)

        links.append({
            "src": port_info(src),
            "dst": port_info(dst),
        })

    state["links"] = links

def get_hosts(data):
    hosts = {}
    for host in data:
        hosts[host["mac"]] = {
            "ipv4": host["ipv4"],
            "ipv6": host["ipv6"],
            "port": port_info(host["port"]),
        }

    state["hosts"] = hosts

def save_state():
    state["timestamp"] = datetime.now().isoformat(timespec="seconds")
    with open(state_json, "w") as f:
        json.dump(state, f, indent=4)
    print(f"Saved {len(state['switches'])} switches to {state_json}")


def get_info(endpoint):
    result = subprocess.run(
        ["curl", "-s", f"{URL}{endpoint}"], capture_output=True, text=True)
    data = json.loads(result.stdout)
    print(f"--- {endpoint} ---")
    print(json.dumps(data, indent=4))
    if endpoint == "switches":
        get_switches(data)
    if endpoint == "links":
        get_links(data)
    if endpoint == "hosts":
        get_hosts(data)


while True:
    for endpoint in endpoints:
        try:
            get_info(endpoint)
        except Exception as e:
            print("Pinged Ryu controller: FAILED", e)
    save_state()
    time.sleep(60)


## to run python3 ping_ryu.py
