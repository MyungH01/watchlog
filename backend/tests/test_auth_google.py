from urllib.parse import parse_qs, urlparse

import pytest

from app import auth_google, config


@pytest.fixture(autouse=True)
def google(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "secret")
    # 구글 응답 흉내: 인증 코드가 곧 구글 사용자 ID
    monkeypatch.setattr(auth_google, "exchange_code", lambda code: {"sub": code, "email": f"{code}@example.com"})


def login(client, sub, state=None):
    start = client.get("/api/auth/google/login", follow_redirects=False)
    real_state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return client.get("/api/auth/google/callback", params={"code": sub, "state": state or real_state},
                      follow_redirects=False)


def names(client):
    return sorted(w["name"] for w in client.get("/api/watches").json())


def test_link_keeps_my_watches(client):
    client.post("/api/watches", json={"name": "A"})
    assert client.get("/api/me").json()["anonymous"] is True
    assert login(client, "alice").status_code == 303
    assert client.get("/api/me").json() == {"anonymous": False, "email": "alice@example.com", "google_enabled": True}
    assert names(client) == ["A"]


def test_same_account_on_another_browser_sees_the_collection(client, other_client):
    client.post("/api/watches", json={"name": "A"})
    login(client, "alice")
    login(other_client, "alice")
    assert names(other_client) == ["A"]
    assert names(client) == ["A"]            # 먼저 로그인한 브라우저의 세션도 그대로 유효하다


def test_anonymous_watches_are_merged_into_existing_account(client, other_client):
    client.post("/api/watches", json={"name": "A"})
    login(client, "alice")
    other_client.post("/api/watches", json={"name": "B"})
    login(other_client, "alice")
    assert names(other_client) == ["A", "B"]


def test_wrong_state_is_rejected(client):
    assert login(client, "alice", state="forged").status_code == 400
    assert client.get("/api/me").json()["anonymous"] is True


def test_logout_only_for_linked_accounts(client):
    assert client.post("/api/auth/logout").status_code == 400
    login(client, "alice")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/watches").status_code == 401


def test_disabled_without_credentials(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "")
    assert client.get("/api/auth/google/login", follow_redirects=False).status_code == 404
    assert client.get("/api/me").json()["google_enabled"] is False
