import sqlite3

def migrate_schema(name: str, new_schema: str, new_fields_calc: str, *index_decls) -> str:
    return "\n\n".join((
        f"CREATE TABLE {name}__new {new_schema};",
        f'INSERT INTO {name}__new SELECT {new_fields_calc} FROM {name};',
        f'DROP TABLE {name};',
        f'ALTER TABLE {name}__new RENAME TO {name};',
        *index_decls
    ))

class Migration:
    def __init__(self, *codes):
        self.code = codes
        
    def apply(self, conn: sqlite3.Connection):
        conn.executescript("\n".join(self.code))

MIGRATIONS: list[Migration] = [
    Migration(
        migrate_schema(
            'checks', 
            '''(
                check_name TEXT NOT NULL,
                timestamp REAL NOT NULL,
                duration REAL,
                size INTEGER,
                status INTEGER,
                passed BOOL NOT NULL,
                errors TEXT NOT NULL,
                PRIMARY KEY (check_name, timestamp)
            )''', 
            "check_name, strftime('%s', timestamp) AS timestamp, duration, size, status, passed, errors",
        ),
        migrate_schema(
            'snapshots', 
            '''(
                uuid TEXT NOT NULL,
                check_name TEXT NOT NULL,
                timestamp REAL NOT NULL,
                duration REAL NOT NULL,
                size INT NOT NULL,
                status INT NOT NULL,
                headers TEXT NOT NULL,
                content TEXT NOT NULL,
                PRIMARY KEY (uuid)
            )''', 
            "uuid, check_name, strftime('%s', timestamp) AS timestamp, duration, size, status, headers, content",
            "CREATE INDEX snapshots_name ON snapshots (check_name, timestamp);",
        ),
    )
]

def apply_migrations(conn: sqlite3.Connection):
    # get database version
    version, = conn.execute("PRAGMA user_version;").fetchone()
    # default i to version
    for i, migration in enumerate(MIGRATIONS, start=1):
        if i > version:
            print(f"updating db to version {i}...")
            migration.apply(conn)

    # cannot use parameters here, so we have to use interprolation
    # this should be safe
    conn.execute(f'PRAGMA user_version = {i}')
    conn.commit()
