import json
from unittest.mock import Mock

import pytest
import requests

from src.equitylens.sec import SecClient, SecError, TICKERS_URL


def response(status, content=b'{"test": 1}', headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = content
    result._content_consumed = True
    result.headers.update(headers or {})
    return result


def test_retry_pacing_header_and_cache(tmp_path):
    clock = [100.0]
    delays = []

    def sleep(seconds):
        delays.append(seconds)
        clock[0] += seconds

    session = Mock()
    session.get.side_effect = [
        response(429, headers={"Retry-After": "3"}),
        response(200),
        response(200),
    ]
    client = SecClient(tmp_path, "EquityLens test", "test@example.invalid",
                       session=session, monotonic=lambda: clock[0], sleep=sleep)
    assert client.get(TICKERS_URL, "a.json", lambda value: None) == {"test": 1}
    client.get(TICKERS_URL, "b.json", lambda value: None)
    client.get(TICKERS_URL, "a.json", lambda value: None)
    assert session.get.call_count == 3
    assert max(delays) == 3
    assert delays[-1] == pytest.approx(0.6)
    assert session.get.call_args.kwargs["headers"]["User-Agent"] == "EquityLens test test@example.invalid"
    assert session.get.call_args.kwargs["timeout"] == (10, 45)
    assert client.sources[0]["sha256"] == client.sources[2]["sha256"]


def test_offline_cache_and_missing_source_need_no_email(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"test": 1}), encoding="utf-8")
    session = Mock()
    client = SecClient(tmp_path, "EquityLens", "", offline=True, session=session)
    assert client.get(TICKERS_URL, "a.json", lambda value: None)["test"] == 1
    with pytest.raises(SecError, match="Missing cached source"):
        client.get(TICKERS_URL, "missing.json", lambda value: None)
    session.get.assert_not_called()


def test_missing_private_identity_blocks_live_requests(tmp_path):
    session = Mock()
    client = SecClient(tmp_path, "EquityLens", "", session=session)
    with pytest.raises(SecError, match="SEC_CONTACT_EMAIL"):
        client.get(TICKERS_URL, "a.json", lambda value: None)
    session.get.assert_not_called()


def test_bad_refresh_preserves_prior_cache(tmp_path):
    cached = tmp_path / "a.json"
    cached.write_bytes(b'{"test": 1}')
    session = Mock()
    session.get.return_value = response(200, b"<html>Access denied</html>")
    client = SecClient(tmp_path, "EquityLens test", "test@example.invalid",
                       refresh=True, session=session)
    with pytest.raises(SecError, match="Invalid SEC JSON"):
        client.get(TICKERS_URL, "a.json", lambda value: None)
    assert cached.read_bytes() == b'{"test": 1}'


def test_access_denial_does_not_retry(tmp_path):
    session = Mock()
    session.get.return_value = response(403)
    client = SecClient(tmp_path, "EquityLens test", "test@example.invalid", session=session)
    with pytest.raises(SecError, match="HTTP 403.*sec-download"):
        client.get(TICKERS_URL, "a.json", lambda value: None)
    session.get.assert_called_once()


def test_timeout_retries_are_bounded(tmp_path):
    session = Mock()
    session.get.side_effect = requests.Timeout
    client = SecClient(tmp_path, "EquityLens test", "test@example.invalid", session=session, sleep=Mock())
    with pytest.raises(SecError, match="Timeout"):
        client.get(TICKERS_URL, "a.json", lambda value: None)
    assert session.get.call_count == 4
