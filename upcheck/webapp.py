from datetime import datetime, timedelta
import flask
import statistics
from upcheck.model import Config
from upcheck.db import with_conn, read_histogramm, initialize_db, all_time_stats
from upcheck.daemon import spawn_daemons

config = Config.load("upcheck.toml")
initialize_db(soft=True)

spawn_daemons(config)

app = flask.Flask(__name__)
app.secret_key = config.secret
app.jinja_env.filters['zip'] = zip

@app.route('/')
def index():
    buckets = 24*4
    duration = timedelta(days=1)
    end = datetime.now()
    with with_conn(rdonly=True) as conn:
        hist = read_histogramm(conn, buckets=buckets, end=end, timespan=duration)
        total_stats = all_time_stats(conn)

    data = {}

    for host in config.checks:
        check = config.checks[host]
        if host in hist:
            all_data = [check for bucket in hist[host] for check in bucket]
            lat_hist = [
                statistics.geometric_mean(check.duration for check in bucket) if bucket else float('nan') for bucket in hist[host]
            ]
            data[host] = {
                'hist': [
                    sum([check.passed for check in bucket]) / len(bucket) if bucket else float('nan') for bucket in hist[host]
                ],
                'hist_latency':lat_hist, 
                'uptime': sum(check.passed for check in all_data) / len(all_data) if all_data else 0,
                'total_uptime': total_stats.get(host, 0),
                'url': check.url,
                'method': check.method,
                'max_lat': max(check.duration for check in all_data),
                'max_geomean_lat': max(e for e in lat_hist if e == e),
                'degraded_latency': check.timeout_degraded,
                'uptime_goal': 0.99,
            }
        else: 
            data[host] = {
                'hist': [float('nan')] * buckets,
                'hist_latency': [float('nan')] * buckets,
                'uptime': 0,
                'total_uptime': total_stats.get(host, 0),
                'max_geomean_lat': 1,
                'max_lat': 0,
                'url': check.url,
                'method': check.method,
                'uptime_goal': 0.99,

            }
    print(data)

    time_buckets = [
        end - (duration * i / buckets) for i in range(buckets-1, -1, -1)
    ]

    return flask.render_template(
        'base.html', 
        data=data,
        start_time=end - duration,
        end_time=end,
        duration=duration,
        time_buckets=time_buckets,
    )
