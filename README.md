# UpCheck - Uptime Checker

Simple uptime checking tool written in python+flask.

![A screenshot of the web-app screen](screenshot.png)

The dashboard shows uptime and latency for each configured host to check.


## Configuration:

```toml
[core]
# your domain where upcheck is running 
domain = "https://upcheck.your.domain.com/"
# user agent (${domain} is expanded):
user_agent = "Mozilla/5.0 (compatible; upcheck-bot; +${domain})"
# number of seconds between checks (default 5 minutes)
interval = 300
# secret for flask (head -c 39 /dev/urandom | base64)
# make sure to change this before deployment
secret = "s3cr3t"

[host.Website]
# url (required)
url = "https://antonlydike.de"

# everything else is optional (defaults are listed):
# status, either one or a list of allowed values
status = [200]
# regex that the body is checked against (default = None)
body = "hello there"
# number of seconds after which the request is considered failed
timeout = 60
# timeout after which the service is considered degraded
timeout_degraded = 2
# http method to use
method = "GET"
```

## Launching

TODO


## Notifications (coming up)

Notifications on outages (service not available), or latency thresholds.

Notification services (planned):

- e-mail
- ntfy.sh
- telegram
