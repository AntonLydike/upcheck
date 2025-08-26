from datetime import datetime
import json
import requests
import re
import uuid

from upcheck.model import ConnCheckRes, ConnCheckSpec, Config, Snapshot

def check_conn(config: Config, check: ConnCheckSpec) -> tuple[ConnCheckRes, Snapshot | None]:
    now = datetime.now()
    try:
        res = requests.request(check.method, check.url, timeout=check.timeout, allow_redirects=True, headers={
            'User-Agent': config.user_agent
        })
    except requests.Timeout:
        return ConnCheckRes(
            check.name,
            now,
            check.timeout,
            0,
            408,
            False,
            ["Connection timed out"]
        ), None

    errors = []
    body_bytes = res.content
    body = body_bytes.decode()

    body_ok = True
    status_ok = True

    if not res.status_code in check.status:
        status_ok = False
        errors.append("Status check failed")

    if check.body:
        body_ok = re.compile(check.body).search(body) is not None
        errors.append("Body check failed")

    snapshot = None
    if not (status_ok and body_ok):
        # create a snapshot:
        snapshot = Snapshot(
            str(uuid.uuid4()),
            check.name,
            now,
            res.elapsed.total_seconds(),
            len(body),
            res.status_code,
            dict(res.headers),
            body,
        )

    return ConnCheckRes(
        check.name,
        now,
        res.elapsed.total_seconds(),
        len(body_bytes),
        res.status_code,
        status_ok and body_ok,
        tuple(errors)
    ), snapshot


if __name__ == '__main__':
    import sys
    file = sys.argv[-1]
    if file ==  '-':
        file = sys.stdin.buffer
    else:
        file = open(file, "rb")
    cfg = Config(":memory:", checks={}, domain="https://ci.test", secret="s3cr3t")
    for check in ConnCheckSpec.from_file(file):
        print(f"[{check.name}]")
        res, _ = check_conn(cfg, check)
        for key in res.__dir__():
            if key.startswith('__'):
                continue
            val = res.__getattribute__(key)
            print(f"{key} = ", end="")

            if isinstance(val, bool):
                print(repr(val).lower())
            elif isinstance(val, (str, int, float)):
                print(repr(val))
            elif isinstance(val, tuple):
                print(repr(list(val)))
            elif isinstance(val, datetime):
                print(val.isoformat())
            else:
                print(val)
        print()
