import subprocess
import time
from net_struct import ModularMininet, build
from ping_ryu import fetch_state
from deepdiff import DeepDiff
from multiprocessing import Process
#from myfile import myfunction
from mininet.cli import CLI

def copy(mininet : ModularMininet, oldtopo : dict):
    while True:
            time.sleep(10)
            newtopo = fetch_state()
            diff = DeepDiff(
                oldtopo, newtopo,
                verbose_level=2,
                report_repetition=True,
                cutoff_distance_for_pairs=0,
                ignore_order_func=lambda level: level.path() == "root['links']",
            )
            mininet.modify(diff)
            oldtopo = newtopo

def main():
    oldtopo = fetch_state()
    mininet = build(oldtopo)
    mininet.start()
    
    worker = Process(
        target=copy,
        args=(mininet, oldtopo)
    )
    worker.start()
    try: 
        CLI(mininet)
    except:
        print("feil")
        
if __name__ == "__main__":
    main()

    


        

