# Deploying the engine

The engine runs as one Docker container on the owner's Oracle Always Free VM (Ubuntu 24.04,
1 OCPU, 1 GB RAM, 2 GB swap). The VM is shared with another project, TARS on Mars, which owns
port 80 and 443 through Caddy and listens itself on 127.0.0.1:8000. CircuitMind takes
127.0.0.1:8001 and one extra site block in the same Caddyfile. Nothing of the other project is
touched.

What runs where:

| Piece | Where | Address |
|---|---|---|
| Landing page and workspace (static) | Vercel Hobby | https://circuit-mind-landing.vercel.app |
| Engine (FastAPI, arduino-cli, wokwi-cli) | Docker on the Oracle VM, container `circuitmind-engine` | https://circuitmind.80-225-202-218.sslip.io (Caddy, TLS) -> 127.0.0.1:8001 -> container port 7860 |
| Sign-in and saved designs | Supabase free tier | see web/cm.js |
| Model | Groq free tier | key in the VM's .env |
| Simulator | Wokwi free tier | token in the VM's .env |

## Building the image (on the laptop, never on the VM)

```
docker buildx build --platform linux/amd64 -t circuitmind-engine:latest --load .
docker save circuitmind-engine:latest | gzip | ssh -i ~/.ssh/tars_oracle ubuntu@80.225.202.218 'gunzip | sudo docker load'
```

The image holds arduino-cli with the ESP32 core, the libraries the tasks use, wokwi-cli and the
engine. It does not hold any secret: those live on the VM in `/home/ubuntu/circuitmind/.env`
(mode 600) and reach the container with `--env-file`.

## Running it

```
sudo docker rm -f circuitmind-engine 2>/dev/null
sudo docker run -d --name circuitmind-engine --restart unless-stopped \
  -p 127.0.0.1:8001:7860 \
  --env-file /home/ubuntu/circuitmind/.env \
  --memory 700m --memory-swap 2g --cpu-shares 512 \
  -v circuitmind-cache:/home/user/.cache/arduino \
  circuitmind-engine:latest
```

- 700 MB of memory plus swap up to 2 GB, and half the CPU weight of the other project, so TARS
  wins when both are busy.
- The `circuitmind-cache` volume keeps arduino-cli's compiled core between restarts.
- On start the container warms that cache by compiling T01's reference once
  (`circuitmind warm`), while already answering `/health`.
- Compiles run with one job (`CIRCUITMIND_COMPILE_JOBS=1`).

## Caddy

One site block added to `/etc/caddy/Caddyfile`:

```
circuitmind.80-225-202-218.sslip.io {
	reverse_proxy 127.0.0.1:8001 {
		flush_interval -1
	}
}
```

`flush_interval -1` stops Caddy buffering the progress stream (server-sent events). Apply with
`caddy validate --config /etc/caddy/Caddyfile` then `sudo systemctl reload caddy`; never restart
Caddy, the other site is on it.

## Checking

```
curl https://circuitmind.80-225-202-218.sslip.io/health
sudo docker stats --no-stream circuitmind-engine
sudo docker logs --tail 50 circuitmind-engine
```

Measured on first deployment: MEASUREMENTS

## Updating

Build a new image on the laptop, `docker save | ssh docker load` as above, then the
`docker rm -f` and `docker run` lines. The cache volume survives.
