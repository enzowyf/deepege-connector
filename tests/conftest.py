from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.mock_core.app import create_app
from tests.mock_core.store import Clock, Store

ALICE = "sk-test-alice"
BOB = "sk-test-bob"
BROKE = "sk-test-broke"
READONLY = "sk-test-readonly"


@pytest.fixture
def clock() -> Clock:
    return Clock(frozen=True)


@pytest.fixture
def store(clock: Clock) -> Store:
    return Store(clock=clock)


@pytest.fixture
def client(store: Store) -> TestClient:
    return TestClient(create_app(store))


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def idem(key: str, token: str = ALICE) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}
