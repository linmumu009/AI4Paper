import os
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from config.config import RETRY_TOTAL, RETRY_BACKOFF, REQUESTS_UA, PROXIES, RESPECT_ENV_PROXIES


def build_session(prefer_env_proxy: bool = False) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({"User-Agent": REQUESTS_UA})
    if PROXIES is not None:
        s.proxies.update(PROXIES)
    else:
        if not (RESPECT_ENV_PROXIES or prefer_env_proxy):
            for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
                os.environ.pop(k, None)
    return s
