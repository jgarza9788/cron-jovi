import requests

from ..action_api import ActionError, Duration, action


@action("http", title="HTTP Request", blurb="GET or POST to a URL",
        category="Web", icon="arrow-right", color="blue")
def http(
    ctx,
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    json: dict | None = None,
    body: str | None = None,
    timeout: Duration = Duration(30),
) -> str:
    method = method.upper()
    ctx.summary = f"{method} {url}"
    try:
        response = requests.request(
            method, url, headers=headers, json=json, data=body, timeout=timeout
        )
    except requests.RequestException as err:
        raise ActionError(f"{method} {url}: {err}") from None
    ctx.summary = f"{method} {url} ({response.status_code})"
    if not response.ok:
        raise ActionError(f"{method} {url} returned {response.status_code}")
    return response.text
