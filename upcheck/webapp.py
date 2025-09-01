from datetime import datetime, timedelta
from math import ceil
import os
import time
import flask
import aalib.duration
from upcheck.cache import timed_cache
from upcheck.migrations import apply_migrations
from upcheck.model import Config
from upcheck.db import (
    read_histogram_new,
    with_conn,
    initialize_db,
    all_time_stats,
)
from upcheck.daemon import spawn_daemons

config = Config.load("upcheck.toml")

if config.secret == "s3cr3t":
    print(
        "Please change the default secret to a secure value, e.g. by running `head -c 39 /dev/urandom | base64`"
    )

# initialize DB but don't fail if it exists
initialize_db(soft=True)

# migrate
with with_conn() as conn:
    apply_migrations(conn)

# start background processes
spawn_daemons(config)

app = flask.Flask(__name__)
app.secret_key = config.secret
app.jinja_env.filters["zip"] = zip


@app.context_processor
def inject_ctx():
    def lat_to_color(lat, max_lat):
        if lat != lat:
            return "gray"
        if lat > 2 * max_lat:
            return "red"
        if lat > max_lat:
            return "orange"
        return "green"

    def uptime_to_color(up, goal):
        if up != up:
            return "gray"
        if up == 1:
            return "green"
        if up < goal:
            return "red"
        return "orange"

    return {
        "lat_to_color": lat_to_color,
        "uptime_to_color": uptime_to_color,
    }


app.jinja_env.filters["duration"] = aalib.duration.duration


def parse_duration(dur_str: str) -> timedelta:
    sfx = dur_str[-1]
    num = float(dur_str[:-1])
    if num != num or num < 0:
        raise ValueError(f"Invalid duration number: {num}")
    if sfx == "h":
        return timedelta(hours=num)
    elif sfx == "d":
        return timedelta(days=num)
    elif sfx == "m":
        return timedelta(minutes=num)
    else:
        raise ValueError("Invalid specifier, use h,d or m")


@timed_cache(30)
def load_template_data(buckets: int, duration: timedelta, end: datetime):
    with with_conn(rdonly=True) as conn:
        hist = read_histogram_new(conn, duration, end, buckets)
        total_stats = all_time_stats(conn)
    data2 = {}
    for host, check in config.checks.items():
        host_stats = total_stats.get(
            host,
            {
                "total_uptime": 0,
                "total_latency_geomean": 1,
            },
        )
        data2[host] = {
            **host_stats,
            "hist_uptime": [float("nan")] * buckets,
            "hist_latency": [float("nan")] * buckets,
            "latency_max": 1,
            "latency_geomean": 1,
            "latency_geomean_max": 1,
            "url": check.url,
            "latency_degraded_level": check.timeout_degraded,
            "uptime_goal": 0.99,
        }
        if host in hist:
            d = hist[host]
            data2[host].update(d)
            data2[host]["latency_geomean_max"] = max([0.00001, *d["hist_latency"]])
    return data2


@app.route("/")
def index():
    t0 = time.time()
    buckets = flask.request.args.get("buckets", 24 * 4, type=int)
    duration = flask.request.args.get(
        "duration", timedelta(days=1), type=parse_duration
    )
    end = flask.request.args.get("end", datetime.now(), datetime.fromisoformat)
    buckets = max(min(buckets, 24 * 4), 0)

    # align to 5 minute intervals
    alignment = 5 * 60
    # round time up to be a multiple of bucket size
    seconds = end.hour * 60 * 60 + end.minute * 60 + end.second
    roundup = int(ceil(seconds / alignment) * alignment) - seconds

    end = (end + timedelta(seconds=roundup)).replace(microsecond=0)

    time_buckets = [
        (end - (duration * (i + 1) / buckets)).astimezone()
        for i in range(buckets - 1, -1, -1)
    ]

    data = load_template_data(buckets, duration, end)
    dur = time.time() - t0

    if flask.request.accept_mimetypes.accept_html and not "json" in flask.request.args:
        return flask.render_template(
            "base.html",
            data=data,
            start_time=(end - duration).astimezone(),
            end_time=end.astimezone(),
            duration=duration,
            time_buckets=time_buckets,
            buckets=buckets,
            time=dur,
        )
    else:
        return flask.jsonify(
            dict(
                start_time=(end - duration).astimezone().isoformat(),
                end_time=end.astimezone().isoformat(),
                duration=duration.total_seconds(),
                buckets=buckets,
                hosts=data,
                time=dur,
            )
        )

@app.route('/favicon.svg')
def favicon():
    return flask.send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.svg', mimetype='image/svg+xml')
