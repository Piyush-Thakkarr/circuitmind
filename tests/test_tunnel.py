"""The share link and the cloudflared log parsing, without starting cloudflared."""

from circuitmind.tunnel import share_link, tunnel_url_from_log

LOG = """2026-11-14T15:02:11Z INF Requesting new quick Tunnel on trycloudflare.com...
2026-11-14T15:02:13Z INF +--------------------------------------------------------------+
2026-11-14T15:02:13Z INF |  https://quiet-otter-radio-leaf.trycloudflare.com            |
2026-11-14T15:02:13Z INF +--------------------------------------------------------------+
"""


def test_url_is_read_from_the_cloudflared_banner():
    assert tunnel_url_from_log(LOG) == "https://quiet-otter-radio-leaf.trycloudflare.com"


def test_no_url_yet_gives_none():
    assert tunnel_url_from_log("INF Requesting new quick Tunnel on trycloudflare.com...") is None


def test_share_link_points_the_web_app_at_the_engine():
    link = share_link("https://quiet-otter-radio-leaf.trycloudflare.com")
    assert link.endswith("/app.html?engine=https://quiet-otter-radio-leaf.trycloudflare.com")
    assert link.startswith("https://")
