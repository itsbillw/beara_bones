# Pi health dashboard

Lightweight monitoring for **DietPiServer** and **MediaPi**: CPU, memory, temperature, and disk usage. No Grafana or Prometheus.

## Components (all in this repo)

| Piece     | Where it runs                  | Module              |
| --------- | ------------------------------ | ------------------- |
| Poller    | DietPiServer (systemd timer)   | `pi_health.poller`  |
| Agent     | MediaPi (one-off manual setup) | `pi_health.agent`   |
| Dashboard | beara_bones `/health`          | Django `health` app |

Netdata (`monitor.itsbillw.eu`) stays for live 1-second graphs.

## DietPiServer setup (after `git pull`)

1. Add to repo-root `.env`:

```bash
HEALTH_DB_PATH=/var/lib/health-monitor/health.sqlite
HEALTH_SQLITE_PATH=/var/lib/health-monitor/health.sqlite
HEALTH_HOSTS=DietPiServer,MediaPi
HEALTH_LOCAL_HOSTNAME=DietPiServer
HEALTH_REMOTE_HOSTNAME=MediaPi
HEALTH_REMOTE_URL=http://192.168.68.100:9105/health
```

2. Deploy the site:

```bash
make deploy
```

3. Install the poller timer (once):

```bash
sudo mkdir -p /var/lib/health-monitor
sudo chown bill:bill /var/lib/health-monitor
make install-health-poller
```

4. Open `https://itsbillw.eu/health` as a staff user.

## Taking MediaPi offline

The dashboard and poller tolerate MediaPi being down. DietPiServer metrics keep updating.

**Option A — stop the agent on MediaPi** (pull the plug):

```bash
ssh bill@192.168.68.100
sudo systemctl stop mediapi-health-agent
```

The poller logs a warning and continues. The MediaPi card shows “offline / no data”.

**Option B — disable remote collection on DietPiServer** (no connection attempts):

```bash
# In /website/beara_bones/.env
HEALTH_REMOTE_ENABLED=false
```

No nginx changes required.

## MediaPi agent (one-off manual setup)

Copy only the `pi_health` package to MediaPi:

```bash
rsync -av pi_health/ bill@192.168.68.100:/opt/health-monitor/pi_health/
scp deploy/systemd/mediapi-health-agent.service bill@192.168.68.100:/tmp/
```

On MediaPi:

```bash
sudo cp /tmp/mediapi-health-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mediapi-health-agent
curl -s http://127.0.0.1:9105/health | python3 -m json.tool
```

Port `9105` is LAN-only — do not expose via nginx.

## Make targets

| Command                      | Description                                    |
| ---------------------------- | ---------------------------------------------- |
| `make health-poller`         | Run one poller cycle manually                  |
| `make install-health-poller` | Install + enable systemd timer on DietPiServer |

## Retention

| Tier        | Resolution | Default retention |
| ----------- | ---------- | ----------------- |
| `snapshots` | 30s        | 48 hours          |
| `rollup_5m` | 5 minutes  | 30 days           |

Override with `HEALTH_RAW_RETENTION_HOURS` and `HEALTH_ROLLUP_RETENTION_DAYS` in `.env`.
