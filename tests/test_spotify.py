import pytest

from eclectolog.spotify import RateLimited, Spotify, endpoint_key


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.content = b"x"
        self.text = str(body)

    def json(self):
        return self._body


class Session:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def post(self, *a, **k):
        return Resp(200, {"access_token": "t", "expires_in": 3600})

    def request(self, method, url, **k):
        self.requests.append(url)
        return self.responses.pop(0)


def test_endpoint_key_collapses_ids():
    assert endpoint_key("https://api.spotify.com/v1/artists/7dNsHhGeGU5MV01r06O8gK/albums?limit=10") == "/artists/*/albums"
    assert endpoint_key("/search") == "/search"


def test_long_rate_limit_trips_breaker_without_more_requests():
    session = Session([Resp(429, headers={"Retry-After": "86000"})])
    client = Spotify("id", "secret", "rt", session=session, sleep=lambda s: None)
    with pytest.raises(RateLimited):
        client.get("/search", {"q": "x"})
    with pytest.raises(RateLimited):
        client.get("/search", {"q": "y"})
    assert len(session.requests) == 1
    assert client.is_blocked("/search") and not client.is_blocked("/me")


def test_short_rate_limit_is_retried():
    session = Session([Resp(429, headers={"Retry-After": "1"}), Resp(200, {"ok": True})])
    slept = []
    client = Spotify("id", "secret", "rt", session=session, sleep=slept.append)
    assert client.get("/me") == {"ok": True}
    assert slept and slept[0] >= 1


def test_read_budget_blocks_gets_but_not_writes():
    session = Session([Resp(200, {"a": 1}), Resp(200, {"b": 2})])
    client = Spotify("id", "secret", "rt", session=session, sleep=lambda s: None)
    client.max_reads = 1
    client.get("/me")
    with pytest.raises(RateLimited):
        client.get("/me")
    assert client.put("/playlists/x/items", {"uris": []}) == {"b": 2}
