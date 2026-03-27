import datetime
import json
import logging
import os
import ssl
import socket
import sys
from urllib.parse import quote

import urllib3


# ---------------------------------------------------------------------------
# Logging setup — colored, structured, same format in Lambda and locally
# ---------------------------------------------------------------------------

class _ColorFormatter(logging.Formatter):
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    WHITE  = "\033[37m"

    LEVEL_COLORS = {
        logging.DEBUG:    DIM + WHITE,
        logging.INFO:     CYAN,
        logging.WARNING:  YELLOW,
        logging.ERROR:    RED + BOLD,
        logging.CRITICAL: RED + BOLD,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        ts    = self.formatTime(record, "%H:%M:%S")
        level = f"{color}{record.levelname:<8}{self.RESET}"
        msg   = record.getMessage()
        return f"{self.DIM}{ts}{self.RESET} {level} {msg}"


def _setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ColorFormatter())
        root.addHandler(handler)

_setup_logging()
log = logging.getLogger(__name__)

# urllib3 floods DEBUG with its own connection lines — keep them quiet
logging.getLogger("urllib3").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def days_between(date1, date2):
    return (date2 - date1).days


def datetime_now():
    return datetime.datetime.now(datetime.timezone.utc)


def string_to_datetime(string):
    # "Aug 15 09:37:47 2022 GMT" — always UTC, make tzinfo explicit
    dt = datetime.datetime.strptime(string, '%b %d %H:%M:%S %Y %Z')
    return dt.replace(tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Certificate check
# ---------------------------------------------------------------------------

def certificate_remote_expire_get(hostname, port):
    log.debug(f"  cert  connecting to {hostname}:{port} for TLS handshake")
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port)) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        subject  = dict(x[0] for x in cert.get('subject', []))
        issuer   = dict(x[0] for x in cert.get('issuer',  []))
        not_after = cert['notAfter']
        expiry   = string_to_datetime(not_after)
        days     = days_between(datetime_now(), expiry)

        log.debug(f"  cert  subject={subject.get('commonName', '?')}  "
                  f"issuer={issuer.get('organizationName', '?')}  "
                  f"expires={not_after}  days_left={days}")
        return days

    except Exception as e:
        log.error(f"  cert  check failed for {hostname}: {type(e).__name__}: {e}")
        return 100


def certificate_remote_expire_check(vhost):
    days = certificate_remote_expire_get(vhost['domain'], vhost['port'])
    if days <= 7:
        _alert(vhost, f'certificate expires in {days} days')
    else:
        log.info(f"  cert  ✓ {vhost['domain']} — {days} days left")


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

def _alert(vhost, error_code):
    bot_chatID = os.environ.get("BOT_CHAT_ID_KIWIOPS", "dummy_id")
    message = '❌💀❌💀❌💀 [Kiwifarm] λ Error: ' + vhost['domain'] + ' => ' + str(error_code)
    log.error(f"ALERT {message}")
    _telegram_send(message, bot_chatID)


def _telegram_send(bot_message, bot_chatID):
    bot_token = os.environ.get("BOT_TOKEN", "dummy_token")
    send_text = (
        'https://api.telegram.org/bot' + bot_token +
        '/sendMessage?chat_id=' + str(bot_chatID) +
        '&text=' + quote(bot_message)
    )
    if bot_token == "dummy_token":
        log.warning(f"  telegram  [MOCK — set BOT_TOKEN to send for real]")
        log.debug(f"  telegram  url={send_text}")
        return
    try:
        log.debug(f"  telegram  sending alert to chat_id={bot_chatID}")
        http.request('GET', send_text)
        log.debug(f"  telegram  sent ok")
    except Exception as e:
        log.error(f"  telegram  send failed: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# HTTP check
# ---------------------------------------------------------------------------

def perform_request(vhost, method, url, headers=None):
    follow_redirects  = vhost.get('follow_redirects', True)
    expected_status   = vhost.get('expected_status', [200])

    if headers is None:
        headers = {}

    # vhost-level custom headers win over defaults
    headers = {**headers, **vhost.get('headers', {})}

    if 'Accept' not in headers:
        headers['Accept'] = '*/*'

    kwargs = {'headers': headers}
    if not follow_redirects:
        kwargs['retries'] = False

    log.info(f"→ {method} {url}")
    log.debug(f"  options  follow_redirects={follow_redirects}  "
              f"expected_status={expected_status}")
    log.debug(f"  req headers  " +
              "  ".join(f"{k}: {v}" for k, v in headers.items()))

    try:
        response = http.request(method, url, **kwargs)

        status_ok = response.status in expected_status
        status_sym = "✓" if status_ok else "✗"

        log.info(f"  {status_sym} HTTP {response.status}  "
                 f"{'OK' if status_ok else 'UNEXPECTED'} "
                 f"(expected {expected_status})")

        resp_headers = dict(response.headers)
        log.debug(f"  resp headers  " +
                  "  ".join(f"{k}: {v}" for k, v in resp_headers.items()))

        if not status_ok:
            error_msg = f"status = {response.status}"
            if 'Location' in response.headers:
                loc = response.headers['Location']
                error_msg += f", Location = {loc}"
                log.debug(f"  redirect  Location: {loc}")
            _alert(vhost, error_msg)

        if vhost.get('protocol') == 'https':
            certificate_remote_expire_check(vhost)

    except Exception as err:
        log.error(f"  exception  {type(err).__name__}: {err}")
        _alert(vhost, f"{type(err).__name__}: {str(err)}")


# ---------------------------------------------------------------------------
# Vhost dispatchers
# ---------------------------------------------------------------------------

def vhost_https_check_unauthenticated(vhost):
    url = f"{vhost['protocol']}://{vhost['domain']}"
    if vhost['port'] not in [80, 443]:
        url = f"{url}:{vhost['port']}"
    if vhost.get('suffix'):
        suffix = vhost['suffix']
        if not suffix.startswith('/'):
            suffix = '/' + suffix
        url = f"{url}{suffix}"

    verb = vhost.get('verb', 'HEAD')
    perform_request(vhost, verb, url)


def vhost_https_get_authenticated(vhost):
    headers = urllib3.make_headers(
        basic_auth='{}:{}'.format(vhost['username'], vhost['password'])
    )
    url = f"{vhost['protocol']}://{vhost['domain']}"
    verb = vhost.get('verb', 'HEAD')
    perform_request(vhost, verb, url, headers=headers)


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    total = (len(event.get('authenticated', [])) +
             len(event.get('unauthenticated', [])))
    log.info(f"=== starting — {total} host(s) to check ===")

    if 'authenticated' in event:
        log.info(f"--- authenticated ({len(event['authenticated'])}) ---")
        for vhost in event['authenticated']:
            vhost_https_get_authenticated(vhost)

    if 'unauthenticated' in event:
        log.info(f"--- unauthenticated ({len(event['unauthenticated'])}) ---")
        for vhost in event['unauthenticated']:
            vhost_https_check_unauthenticated(vhost)

    log.info("=== done ===")
    return {"statusCode": 200, "body": "ok"}


# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

urllib3.disable_warnings()
http = urllib3.PoolManager(
    cert_reqs=ssl.CERT_NONE,
    retries=urllib3.Retry(3, redirect=2),
    timeout=10.0
)

# ---------------------------------------------------------------------------
# Local entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path

    load_dotenv(dotenv_path=Path('.') / '.env.local', override=True)

    event_json_str = os.environ.get("EVENT_JSON", "").strip()

    if event_json_str:
        log.info("loading event from EVENT_JSON env var")
        try:
            event = json.loads(event_json_str)
        except json.JSONDecodeError as e:
            log.error(f"EVENT_JSON is not valid JSON: {e}")
            sys.exit(1)
    else:
        if len(sys.argv) > 1:
            config_file = sys.argv[1]
        elif os.path.exists('config.json'):
            config_file = 'config.json'
        else:
            config_file = 'hosts_lambda_checker.json'

        log.info(f"loading event from file: {config_file}")
        try:
            with open(config_file) as f:
                event = json.load(f)
        except FileNotFoundError:
            log.error(f"config file '{config_file}' not found")
            sys.exit(1)
        except json.JSONDecodeError as e:
            log.error(f"failed to parse '{config_file}': {e}")
            sys.exit(1)

    lambda_handler(event, {})