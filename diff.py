from deepdiff import DeepDiff
from pprint import pprint
import json
from pathlib import Path


topology_path = Path(__file__).with_name("topology.json")
with topology_path.open() as file:
    old = json.load(file)

topology_path = Path(__file__).with_name("topologyMOD.json")
with topology_path.open() as file:
    new = json.load(file)


diff = DeepDiff(
    old, new,
    verbose_level=2,
    report_repetition=True,
    cutoff_distance_for_pairs=0,
    ignore_order_func=lambda level: level.path() == "root['links']",
)
pprint(diff)
