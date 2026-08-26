# JuiceWRLD API Downloader

A resumable command-line mirror for the Juice WRLD API's complete
`Compilation/` directory. It discovers every MP3 exposed by the API, preserves
the remote folder structure, and periodically downloads new or replaced files.
It is designed to run continuously as a TrueNAS SCALE Custom App.

> Use this tool only for content you are legally allowed to download. The tool
> is not affiliated with Juice WRLD or the operators of juicewrldapi.com.

## Features

- Mirrors all released, unreleased, and leak subdirectories below `Compilation/`.
- Uses the API's paginated `/files/browse/` endpoint as its source of truth.
- Saves downloads as `.part` files and atomically renames completed files.
- Resumes interrupted files using HTTP `Range` and `If-Range` requests.
- Tracks API size, modification time, and ETag in an atomic JSON manifest.
- Limits concurrency and retries transient failures with exponential backoff.
- Sends one grouped Discord webhook notification when new or replaced tracks
  are downloaded, with that run's log attached.
- Never deletes local files unless cleanup is explicitly enabled.

## Quick start with Docker Compose

```sh
# Clone or copy this repository, then enter its directory:
cd JuiceWRLD-API-DL
mkdir -p data config
docker compose up -d
docker compose logs -f juicewrld-api-dl
```

The defaults write music below `./data/Compilation/`, keep state in
`./config/manifest.json`, and check for updates once per hour.

Run one pass instead of the watcher:

```sh
docker compose run --rm juicewrld-api-dl sync
```

Compare local and remote state without downloading:

```sh
docker compose run --rm juicewrld-api-dl status
```

## TrueNAS SCALE Custom App

The application has no web interface and needs no exposed ports. It needs one
dataset for music and one small dataset for its manifest.

### 1. Create datasets

Create, for example:

- `/mnt/tank/music/juicewrld` for downloaded music
- `/mnt/tank/apps/juicewrld-api-dl` for the manifest

Grant the app identity read/write access. TrueNAS commonly uses UID/GID `568`
for apps; if your datasets use a different owner, set `PUID` and `PGID` to that
numeric identity in the Compose environment.

### 2. Install the Custom App

In **Apps → Discover Apps → Custom App → Install via YAML**, use this Compose
configuration. Change the image and both host paths as needed:

```yaml
services:
  juicewrld-api-dl:
    image: ghcr.io/jochemkuipers/juicewrld-api-dl:latest
    restart: unless-stopped
    user: "568:568"
    command: ["watch"]
    environment:
      JWI_OUT_DIR: /data
      JWI_CONFIG_DIR: /config
      JWI_POLL_INTERVAL: "3600"
      JWI_CONCURRENCY: "3"
      JWI_RETRIES: "5"
      JWI_CLEANUP: "false"
      JWI_NOTIFY_URLS: ""
    volumes:
      - /mnt/tank/music/juicewrld:/data
      - /mnt/tank/apps/juicewrld-api-dl:/config
```

The first pass downloads the complete collection and may take a long time.
Stopping or restarting the app is safe: completed files stay complete and
partial files resume on the next run.

The public image supports both `linux/amd64` and `linux/arm64`. No registry
credentials are required. Use the immutable `:0.1.2` tag instead of `:latest`
if you prefer to update the app manually.

### Notifications

Set `JWI_NOTIFY_URLS` to one or more comma-separated Discord webhook URLs:

```text
# Discord webhook
discord://WEBHOOK_ID/WEBHOOK_TOKEN
```

The original `https://discord.com/api/webhooks/ID/TOKEN` form is also accepted.
Treat webhook URLs as secrets. If multiple URLs are configured, the same grouped
update is sent to each one. The list is capped at 20 track names per message,
followed by a count of the remaining files. Each message carries the log of
that run (`<config dir>/juicewrld-api-dl.log`) as an attachment. Every run
starts a fresh log; the previous run's log is kept as
`juicewrld-api-dl.log.1` (both size-capped at 1 MiB).

## CLI usage

Install locally with [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run juicewrld-api-dl --help
```

Commands:

```text
juicewrld-api-dl sync       Run one synchronization pass
juicewrld-api-dl watch      Synchronize forever at a polling interval
juicewrld-api-dl status     Show the remote/local difference, without downloading
juicewrld-api-dl list       List paths exposed by the remote Compilation folder
juicewrld-api-dl manifest   Inspect the local manifest
```

Common examples:

```sh
# One pass using local directories
uv run juicewrld-api-dl sync --out ./data --config-dir ./config

# Poll every 30 minutes with two concurrent downloads
uv run juicewrld-api-dl watch --out ./data --config-dir ./config \
  --interval 1800 --concurrency 2

# Print all remote paths
uv run juicewrld-api-dl list --limit 0

# Delete files that no longer exist upstream (disabled by default)
uv run juicewrld-api-dl sync --cleanup
```

## Configuration

CLI flags override environment variables, which override these defaults:

| Variable | Default | Description |
|---|---:|---|
| `JWI_API_URL` | `https://juicewrldapi.com/juicewrld` | API base URL |
| `JWI_ROOT` | `Compilation` | Remote root to mirror |
| `JWI_OUT_DIR` | `/data` | Music output directory |
| `JWI_CONFIG_DIR` | `/config` | Manifest directory |
| `JWI_POLL_INTERVAL` | `3600` | Seconds between checks; minimum 60 |
| `JWI_CONCURRENCY` | `3` | Simultaneous downloads |
| `JWI_RETRIES` | `5` | Retries per file after the first attempt |
| `JWI_RETRY_DELAY` | `2` | Initial retry delay in seconds |
| `JWI_PAGE_SIZE` | `100` | Browse API page size |
| `JWI_TIMEOUT` | `120` | HTTP timeout in seconds |
| `JWI_CLEANUP` | `false` | Delete files removed upstream |
| `JWI_NOTIFY_URLS` | empty | Comma-separated Discord webhook URLs |
| `JWI_STARTUP_DELAY` | `0` | Delay before the first watcher pass |

## Synchronization behavior

The remote path is retained below the output directory. For example:

```text
Compilation/2. Unreleased Discography/Song.mp3
```

is written to:

```text
/data/Compilation/2. Unreleased Discography/Song.mp3
```

A file is downloaded when it is new, its API size or modification time changed,
or the manifest says it should exist but its local file is missing or has the
wrong size. The manifest is updated after every completed file. A failed file
does not prevent other files in the pass from downloading.

With cleanup disabled, removed upstream paths remain in both the local tree and
manifest. With cleanup enabled, they are deleted after successful discovery.

## Development and validation

```sh
uv sync --dev
uv run pytest
```

The regular tests mock the API and do not download music. An opt-in live test
lists the real collection and makes one 1 KiB range request:

```sh
JWI_RUN_LIVE_TESTS=1 uv run pytest -m live
```