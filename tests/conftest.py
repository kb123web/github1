import pytest

from app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("app.DATA_DIR", tmp_path)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client
