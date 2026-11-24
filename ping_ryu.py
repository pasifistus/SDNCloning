import time
import urllib.request
import subprocess
import json

URL = "http://127.0.0.1:8080/v1.0/topology/"
endpoints = ["switches", "links", "hosts"]

def get_info(endpoint):
    result = subprocess.run(
    ["curl", "-s", f"{URL}{endpoint}"], capture_output=True, text=True)
    data = json.loads(result.stdout)
    print(f"--- {endpoint} ---")
    print(json.dumps(data, indent=4))

while True:
    for endpoint in endpoints:
            try:
                get_info(endpoint)
            except Exception as e:
                print("Pinged Ryu controller: FAILED", e)
    time.sleep(60)


## to run python3 ping_ryu.py