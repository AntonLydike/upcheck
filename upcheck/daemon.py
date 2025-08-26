import random
import sys
import time
from upcheck.model import Config, ConnCheckRes, Snapshot
from upcheck.check import check_conn
from upcheck.db import save_check, save_snapshot, with_conn
from queue import Queue
import traceback

import multiprocessing

def check_daemon(cfg: Config, host: str, out: multiprocessing.Queue):
    # sleep random interval up to 5 seconds to prevent all requests from going at the same time
    time.sleep(random.random() * 5)

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
            last_check = time.time()
        else:
            time.sleep(sleep_time)


def writer_damon(queue: Queue[ConnCheckRes]):
    while True:
        check, snap = queue.get()
        try:
            with with_conn() as conn:
                if isinstance(check, ConnCheckRes):
                    save_check(conn, check)
                    print("Got Trace")
                elif isinstance(snap, Snapshot):
                    save_snapshot(conn, snap)
                    print("Got Snapshot")
        except Exception as ex:
            print(f"Error saving document: '{ex}' - {check.json()}", file=sys.stderr)
            traceback.print_exc()


def spawn_daemons(cfg: Config):
    queue: Queue[tuple[ConnCheckRes, None | Snapshot]] = multiprocessing.Queue()

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

