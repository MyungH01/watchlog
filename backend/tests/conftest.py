import os

# app 모듈을 불러오기 전에 설정해야 한다. 테스트는 메모리 SQLite와 가짜 S3·SQS로 돈다.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SQS_QUEUE_URL"] = "test-queue"
os.environ.pop("STATIC_DIR", None)

import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app import api, aws, models


@pytest.fixture(autouse=True)
def database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    monkeypatch.setattr(models.SessionLocal, "kw", {**models.SessionLocal.kw, "bind": engine})
    yield
    engine.dispose()


class FakeAws:
    """S3는 {key: 로컬 파일 경로}, SQS는 리스트로 흉내 낸다."""

    def __init__(self):
        self.objects: dict[str, str] = {}
        self.queue: list[str] = []
        self.deleted: list[str] = []


@pytest.fixture(autouse=True)
def fake_aws(monkeypatch):
    fake = FakeAws()
    monkeypatch.setattr(aws, "upload_form", lambda key, ct, mx: {"url": "http://s3.test", "fields": {"key": key}})
    monkeypatch.setattr(aws, "view_url", lambda key: f"http://s3.test/{key}")
    monkeypatch.setattr(aws, "object_size", lambda key: os.path.getsize(fake.objects[key]) if key in fake.objects else None)
    monkeypatch.setattr(aws, "download", lambda key, path: shutil.copy(fake.objects[key], path))
    monkeypatch.setattr(aws, "delete_objects", lambda keys: fake.deleted.extend(keys))
    monkeypatch.setattr(aws, "enqueue", lambda mid: fake.queue.append(mid))
    return fake


@pytest.fixture
def client():
    c = TestClient(api.app)
    assert c.post("/api/session").status_code == 200
    return c


@pytest.fixture
def other_client():
    c = TestClient(api.app)
    c.post("/api/session")
    return c
