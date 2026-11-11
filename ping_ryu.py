import time
import urllib.request
import subprocess
import json

URL = "http://127.0.0.1:8080/v1.0/topology/switches"

while True:
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
    time.sleep(60)


## to run python3 ping_ryu.py