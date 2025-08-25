from datetime import datetime
import requests
import re

from upcheck.model import ConnCheckRes, ConnCheckSpec, Config

def check_conn(config: Config, check: ConnCheckSpec) -> ConnCheckRes:
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
        )

    body = res.content
    status_ok = res.status_code in check.status
    body_ok = re.compile(check.body if check.body else ".").search(body.decode()) is not None
    errors = []
    if not status_ok:
        errors.append("Status check failed")
    if not body_ok:
        errors.append("Body check failed")

    return ConnCheckRes(
        check.name,
        now,
        res.elapsed.total_seconds(),
        len(body),
        res.status_code,
        status_ok and body_ok,
        tuple(errors)
    )


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
        res = check_conn(cfg, check)
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
