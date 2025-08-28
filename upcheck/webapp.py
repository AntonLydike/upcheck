from datetime import datetime, timedelta
from math import ceil
import flask
import statistics
from upcheck.model import Config
from upcheck.db import with_conn, read_histogramm, initialize_db, all_time_stats
from upcheck.daemon import spawn_daemons

config = Config.load("upcheck.toml")

if config.secret == "s3cr3t":
    print(
        "Please change the default secret to a secure value, e.g. by running `head -c 39 /dev/urandom | base64`"
    )

initialize_db(soft=True)

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


@app.route("/")
def index():
    buckets = flask.request.args.get("buckets", 24 * 4, type=int)
    duration = flask.request.args.get(
        "duration", timedelta(days=1), type=parse_duration
    )
    end = flask.request.args.get("end", datetime.now(), datetime.fromisoformat)
    buckets = max(min(buckets, 24 * 4), 0)
    print(end)

    # align to 5 minute intervals
    alignment = 5 * 60
    # round time up to be a multiple of bucket size
    seconds = end.hour * 60 * 60 + end.minute * 60 + end.second
    roundup = int(ceil(seconds / alignment) * alignment) - seconds

    end = (end + timedelta(seconds=roundup)).replace(microsecond=0)
    with with_conn(rdonly=True) as conn:
        hist = read_histogramm(conn, buckets=buckets, end=end, timespan=duration)
        total_stats = all_time_stats(conn)

    data = {}

    for host in config.checks:
        check = config.checks[host]
        if host in hist:
            all_data = [check for bucket in hist[host] for check in bucket]
            lat_hist = [
                (
                    statistics.geometric_mean(check.duration for check in bucket)
                    if bucket
                    else float("nan")
                )
                for bucket in hist[host]
            ]
            data[host] = {
                "hist": [
                    (
                        sum([check.passed for check in bucket]) / len(bucket)
                        if bucket
                        else float("nan")
                    )
                    for bucket in hist[host]
                ],
                "hist_latency": lat_hist,
                "uptime": (
                    sum(check.passed for check in all_data) / len(all_data)
                    if all_data
                    else 0
                ),
                "total_uptime": total_stats.get(host, 0),
                "url": check.url,
                "method": check.method,
                "max_lat": max(check.duration for check in all_data),
                "max_geomean_lat": max([0.00001, *(e for e in lat_hist if e == e)]),
                "degraded_latency": check.timeout_degraded,
                "uptime_goal": 0.99,
            }
        else:
            data[host] = {
                "hist": [float("nan")] * buckets,
                "hist_latency": [float("nan")] * buckets,
                "uptime": 0,
                "total_uptime": total_stats.get(host, 0),
                "max_geomean_lat": 1,
                "max_lat": 0,
                "url": check.url,
                "method": check.method,
                "uptime_goal": 0.99,
            }

    time_buckets = [
        (end - (duration * (i + 1) / buckets)).astimezone()
        for i in range(buckets - 1, -1, -1)
    ]

    return flask.render_template(
        "base.html",
        data=data,
        start_time=(end - duration).astimezone(),
        end_time=end.astimezone(),
        duration=duration,
        time_buckets=time_buckets,
        buckets=buckets,
    )
