from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import tomllib
import json
from typing import Any, TextIO

def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return repr(obj)

@dataclass(kw_only=True)
class ConnCheckSpec:
    name: str
    method: str = 'GET'
    url: str
    timeout: float = 60.0
    timeout_degraded: float = 2.0
    status: Sequence[int] = (200,)
    body: str | None = None

    def __post_init__(self):
        if isinstance(self.status, int):
            self.status = (self.status,)

    @classmethod
    def from_file(cls, file: TextIO) -> list['ConnCheckSpec']:
        return [
            ConnCheckSpec(
                name=name,
                **args 
            ) for name, args in tomllib.load(file).items()
        ]

    def json(self) -> str:
        return json.dumps(
            {k: getattr(self, k) for k in self.__dir__() if k[0] != '_' and k != 'json'},
            default=_json_default
        )

@dataclass
class ConnCheckRes:
    check: str
    time: datetime
    duration: float
    size: int
    status: int
    passed: bool
    errors: Sequence[str]

    def json(self) -> str:
        return json.dumps(
            {k: getattr(self, k) for k in self.__dir__() if k[0] != '_' and k != 'json'},
            default=_json_default
        )


@dataclass
class Config:
    location: str # file location
    checks: dict[str, ConnCheckSpec]
    domain: str
    secret: str
    port: int = 8080
    user_agent: str = "Mozilla/5.0 (compatible; upcheck-bot; +${domain})"
    interval: int = 60 * 5 # every 5 minutes

    def __post_init__(self):
        self.user_agent = self.user_agent.format(domain = self.domain)

    @classmethod
    def load(cls, file: str) -> 'Config':
        with open(file, 'rb') as f:
            data = tomllib.load(f)
        checks = {
            host: ConnCheckSpec(name=host,**check) for host, check in data.pop('host').items()
        }
        return Config(
            location=file,
            checks=checks, 
            **data['core']
        )
    
@dataclass
class Snapshot:
    uuid: str
    check: str
    timestamp: datetime
    duration: float
    size: int
    status: int
    headers: str
    content: str


@dataclass
class Incident:
    check: str
    start: datetime
    end: datetime
    status: int
    snapshots: Sequence[str]
    """
    sequence of snapshot uuids
    """

if __name__ == '__main__':
    import sys
    print(repr(Config.load(sys.argv[-1])).replace(',', ',\n\t').replace('\t)', ')'))
