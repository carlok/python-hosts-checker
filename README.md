# hosts-checker

AWS Lambda function that monitors HTTP/HTTPS endpoints and SSL certificate expiry,
sending alerts via Telegram when something is wrong.

---

## How it works

The Lambda receives an event JSON with a list of hosts to check. For each host it:

- Makes an HTTP request (`HEAD` by default, configurable) and alerts if the response is not `200`
- For HTTPS hosts, checks the SSL certificate and alerts if it expires within 7 days

Alerts are sent to a Telegram chat via bot.

---

## Event format

```json
{
  "unauthenticated": [
    {
      "domain": "example.com",
      "port": 443,
      "protocol": "https",
      "verb": "HEAD",
      "follow_redirects": true,
      "suffix": "/health"
    },
    {
      "domain": "example.com",
      "port": 80,
      "protocol": "http",
      "follow_redirects": false
    }
  ],
  "authenticated": [
    {
      "domain": "private.example.com",
      "port": 443,
      "protocol": "https",
      "verb": "GET",
      "username": "monitor",
      "password": "secret"
    }
  ]
}
```

### Host fields

| Field | Required | Default | Description |
|---|---|---|---|
| `domain` | ✅ | — | Hostname to check |
| `port` | ✅ | — | TCP port |
| `protocol` | ✅ | — | `http` or `https` |
| `verb` | | `HEAD` | HTTP method |
| `follow_redirects` | | `true` | Follow 3xx responses |
| `suffix` | | — | URL path appended after domain |
| `expected_status` | | `[200]` | List of HTTP status codes considered OK |
| `headers` | | `{}` | Extra request headers (merged over defaults, useful for SPAs that check `Accept` or `User-Agent`) |
| `username` | authenticated only | — | Basic auth username |
| `password` | authenticated only | — | Basic auth password |

---

## Lambda deployment

### Environment variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `BOT_CHAT_ID_KIWIOPS` | Telegram chat ID to send alerts to |

### Dependencies (Lambda layer / package)

```
requirements.txt
```

Only `urllib3>=2.0` — no other runtime dependency.

---

## Local development (Podman-first)

This repo’s dev workflow targets **Podman**. The same OCI image builds with `Dockerfile` or `Containerfile` (symlink); `podman compose` reads `docker-compose.yml` as usual.

### Prerequisites

- **Podman** and the **Compose** integration (`podman compose`, often via the `compose` subcommand or `podman-compose` depending on your install)
- A copy of the hosts config JSON

### Setup

```bash
# 1. Create your local-private hosts config from the example
cp hosts_lambda_checker.example.json hosts_lambda_checker.local.json
# edit hosts_lambda_checker.local.json with real hosts and credentials

# 2. Create your local env file
cp .env.example .env.local
# edit .env.local with real BOT_TOKEN and BOT_CHAT_ID_KIWIOPS

# 3. Keep private files local only (already git-ignored)
# .env.local
# hosts_lambda_checker.local.json
```

### Build the dev image (runs unit tests + coverage in the build)

```bash
podman compose build
```

The image build runs `pytest` with coverage; a failing test or install error fails the build.

### Run

```bash
podman compose run checker python /app/checker.py /app/hosts_lambda_checker.local.json
```

`checker.py` is mounted as a volume for local development. After editing code, rebuild to re-run the image build tests, or run tests locally (below).

To rebuild after changing `requirements-dev.txt`:

```bash
podman compose build
```

### Run tests locally (without building the image)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

### Install local git safety hooks

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
pre-commit install
```

The repository includes a `detect-secrets` pre-commit hook configured with
`.secrets.baseline` to block newly introduced secrets in tracked files.

### Pass a different config file

```bash
podman compose run checker python /app/checker.py /app/other_hosts.json
```

Mount the extra file first if it lives outside the project directory, or add it
to the volumes list in `docker-compose.yml`.

### Pass the event inline (useful for CI)

```bash
EVENT_JSON='{"unauthenticated":[{"domain":"example.com","port":443,"protocol":"https","verb":"HEAD"}]}' \
  podman compose up
```

`EVENT_JSON` takes priority over the config file when set and non-empty.

### Event source priority

1. `EVENT_JSON` environment variable
2. CLI argument: `python checker.py path/to/file.json`
3. `config.json` if it exists in the working directory
4. `hosts_lambda_checker.local.json` (local-private default)
5. `hosts_lambda_checker.example.json` (safe fallback template)

### Rootless Podman (Linux)

If bind mounts fail with permission errors, you may need volume relabelling (e.g. `:Z` on the mount) for your environment.

---

## Docker / Docker Compose (optional)

If you use Docker instead of Podman, the same commands work with `docker` / `docker compose`:

- `docker compose build` — builds the image (includes tests in the build)
- `docker compose run checker ...` — same as the Podman examples above

Building the image directly:

- `podman build -f Dockerfile .` or `podman build -f Containerfile .` (equivalent)

---

## Project structure

```
checker.py                        # Lambda handler + local entrypoint
requirements.txt                  # Lambda dependencies (urllib3 only)
requirements-dev.txt              # Local dev deps (dotenv, pre-commit, pytest, …)
pytest.ini                        # Pytest + coverage defaults
tests/                            # Unit tests (mocked I/O)
Dockerfile                        # Dev image; RUN pytest during build
Containerfile                     # Symlink to Dockerfile (Podman-friendly name)
docker-compose.yml                # Local dev runner — mounts code and config
hosts_lambda_checker.example.json # Example event/config file
hosts_lambda_checker.local.json   # Local-private runtime config (git-ignored)
.env.example                      # Example env file for local runs
.pre-commit-config.yaml           # Local commit hooks (format + secret scan)
.secrets.baseline                 # Secret scan baseline for tracked files
```

## Security and publishing

- Never commit real credentials or tokens.
- Keep operational secrets in local-only files:
  - `.env.local`
  - `hosts_lambda_checker.local.json`
- Commit only safe placeholders in tracked files.
