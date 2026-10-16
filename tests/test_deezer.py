import pytest

from eclectolog.deezer import Deezer, DeezerError, name_key


class Resp:
    def __init__(self, body, status=200):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        return self._body


class Session:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def get(self, url, params=None, timeout=None):
        self.requests.append(url)
        return self.responses.pop(0)


def client(*responses, **kw):
    session = Session(responses)
    return Deezer(session=session, sleep=lambda s: None, **kw), session


def test_name_key_matches_across_catalogs():
    assert name_key("Beyoncé") == name_key("BEYONCE") == "beyonce"
    assert name_key("The Beatles") == name_key("Beatles")
    assert name_key("Σtella") == "σtella"


def test_find_artist_takes_the_exact_match_with_most_fans():
    dz, _ = client(Resp({"data": [
        {"id": 1, "name": "Childish Gambino & Khruangbin", "nb_fan": 999999},
        {"id": 2, "name": "Khruangbin", "nb_fan": 0},
        {"id": 3, "name": "Khruangbin", "nb_fan": 98828},
    ]}))
    assert dz.find_artist("khruangbin").id == 3


def test_quota_errors_retry_and_answers_are_cached():
    dz, session = client(Resp({"error": {"code": 4, "message": "Quota limit exceeded"}}), Resp({"isrc": "USX1"}))
    assert dz.isrc(7) == "USX1"
    assert dz.isrc(7) == "USX1"
    assert len(session.requests) == 2


def test_unknown_ids_are_empty_and_other_errors_raise():
    dz, _ = client(Resp({"error": {"code": 800, "message": "no data"}}), Resp({"error": {"code": 100, "message": "boom"}}))
    assert dz.related(0) == []
    with pytest.raises(DeezerError, match="boom"):
        dz.top_tracks(1)


def test_call_budget():
    dz, _ = client(Resp({"data": []}), max_calls=1)
    dz.related(1)
    with pytest.raises(DeezerError, match="budget"):
        dz.related(2)
