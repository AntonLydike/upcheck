#!/usr/bin/env bash
set -euo pipefail

cd /srv/
git clone https://github.com/antonlydike/upcheck.git
cd upcheck

# install git and python3.13
dnf install git python3.13 -y

# download and init uv
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv -p $(which python3.13)
uv sync

# download and install caddy
# TODO: figure this out

# create config file and database
cp upcheck.sample.toml upcheck.toml
uv run python -m upcheck.webapp

# setup rights on /srv/upcheck
useradd -r -s /usr/sbin/nologin upcheck
chown upcheck:upcheck /srv/upcheck /srv/upcheck/upcheck.toml /srv/upcheck/upcheck.db

# install systemd service
ln -s $PWD/upcheck.service /etc/systemd/system/upcheck.service
systemctl daemon-reload
systemctl start upcheck

# install caddyfile
cat Caddyfile.sample > /etc/caddy/Cadddyfile
systemctl start caddy
