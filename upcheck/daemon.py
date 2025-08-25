import sys
import time
from upcheck.model import Config, ConnCheckRes
from upcheck.check import check_conn
from upcheck.db import save_check
from queue import Queue
import traceback

import multiprocessing

def check_daemon(cfg: Config, host: str, out: multiprocessing.Queue):
    check = cfg.checks[host]

    # initialize with next interval being over now:
    last_check = time.time() - cfg.interval
    while True:
        if last_check + cfg.interval < time.time():
            # do check
            last_check += cfg.interval
            out.put(check_conn(cfg, check))
            
        # sleep until the next check is due:
        sleep_time = (last_check + cfg.interval) - time.time()
        if sleep_time < 1:
            print(f"Negative sleep time on {check.name}: ({sleep_time}s)", file=sys.stderr)
        else:
            time.sleep(sleep_time)

def writer_damon(queue: Queue[ConnCheckRes]):
    while True:
        elem = queue.get()
        try:
            save_check(elem)
            print("Got Trace")
        except Exception as ex:
            print(f"Error saving document: '{ex}' - {elem.json()}", file=sys.stderr)
            traceback.print_exc()
        


def spawn_daemons(cfg: Config):
    queue: Queue[ConnCheckRes] = multiprocessing.Queue()

    for host in cfg.checks:
        multiprocessing.Process(
            target=check_daemon,
            args=(cfg, host, queue),
            daemon=True
        ).start()

    multiprocessing.Process(
        target=writer_damon,
        args=(queue,),
        daemon=True,
    ).start()
    print("All processes started successfully")

