"""End-to-end integration test for Browser Pool Service.

Prerequisites: docker compose up -d (all services running)
Run: pytest tests/test_e2e.py -v
"""
import asyncio
import httpx
import pytest

MASTER_URL = "http://localhost:9000"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=MASTER_URL, timeout=30)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["role"] == "master"


def test_nodes_registered(client):
    """Wait for at least one node to register via heartbeat."""
    import time
    for _ in range(12):
        r = client.get("/api/nodes")
        if r.status_code == 200 and len(r.json()) > 0:
            nodes = r.json()
            assert any(n["online"] for n in nodes)
            return
        time.sleep(5)
    pytest.fail("No nodes registered after 60s")


def test_acquire_and_release(client):
    """Full acquire → verify CDP → release → re-acquire cycle."""
    # Acquire
    r = client.post("/api/pool/acquire", json={
        "consumer_id": "e2e-consumer-1",
        "owner": "e2e-worker",
        "ttl": 120,
        "timezone": "America/New_York",
    })
    assert r.status_code == 200, f"Acquire failed: {r.text}"
    data = r.json()
    assert "cdp_url" in data
    assert "view_url" in data
    assert "session_id" in data
    session_id = data["session_id"]
    print(f"Acquired: session={session_id}, cdp={data['cdp_url']}")

    # Verify session shows in list
    r = client.get("/api/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert any(s["session_id"] == session_id for s in sessions)

    # Release
    r = client.post("/api/pool/release", json={
        "session_id": session_id,
        "owner": "e2e-worker",
    })
    assert r.status_code == 200
    print("Released successfully")

    # Re-acquire same consumer → same profile_id
    r = client.post("/api/pool/acquire", json={
        "consumer_id": "e2e-consumer-1",
        "owner": "e2e-worker",
        "ttl": 60,
    })
    assert r.status_code == 200
    data2 = r.json()
    assert data2["profile_id"] == data["profile_id"], "Same consumer should get same profile"
    print(f"Re-acquired: same profile_id={data2['profile_id']}")

    # Cleanup
    client.post("/api/pool/release", json={"session_id": data2["session_id"], "owner": "e2e-worker"})


def test_different_consumers_different_profiles(client):
    """Different consumer_ids get different profiles."""
    r1 = client.post("/api/pool/acquire", json={"consumer_id": "e2e-A", "owner": "w", "ttl": 60})
    r2 = client.post("/api/pool/acquire", json={"consumer_id": "e2e-B", "owner": "w", "ttl": 60})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["profile_id"] != r2.json()["profile_id"]
    # Cleanup
    client.post("/api/pool/release", json={"session_id": r1.json()["session_id"], "owner": "w"})
    client.post("/api/pool/release", json={"session_id": r2.json()["session_id"], "owner": "w"})


def test_duplicate_acquire_rejected(client):
    """Same consumer can't acquire twice simultaneously."""
    r1 = client.post("/api/pool/acquire", json={"consumer_id": "e2e-dup", "owner": "w", "ttl": 60})
    assert r1.status_code == 200
    r2 = client.post("/api/pool/acquire", json={"consumer_id": "e2e-dup", "owner": "w", "ttl": 60})
    assert r2.status_code == 409
    # Cleanup
    client.post("/api/pool/release", json={"session_id": r1.json()["session_id"], "owner": "w"})


def test_renew(client):
    """Renew extends TTL."""
    r = client.post("/api/pool/acquire", json={"consumer_id": "e2e-renew", "owner": "w", "ttl": 60})
    assert r.status_code == 200
    session_id = r.json()["session_id"]

    r = client.post("/api/pool/renew", json={"session_id": session_id, "owner": "w"})
    assert r.status_code == 200
    assert "expires_at" in r.json()

    client.post("/api/pool/release", json={"session_id": session_id, "owner": "w"})


def test_reset(client):
    """Reset creates fresh profile on next acquire."""
    r = client.post("/api/pool/acquire", json={"consumer_id": "e2e-reset", "owner": "w", "ttl": 60})
    assert r.status_code == 200
    old_profile = r.json()["profile_id"]
    client.post("/api/pool/release", json={"session_id": r.json()["session_id"], "owner": "w"})

    r = client.post("/api/pool/reset", json={"consumer_id": "e2e-reset"})
    assert r.status_code == 200

    r = client.post("/api/pool/acquire", json={"consumer_id": "e2e-reset", "owner": "w", "ttl": 60})
    assert r.status_code == 200
    assert r.json()["profile_id"] != old_profile
    client.post("/api/pool/release", json={"session_id": r.json()["session_id"], "owner": "w"})


def test_view_url_token(client):
    """View URL requires valid token."""
    r = client.post("/api/pool/acquire", json={"consumer_id": "e2e-view", "owner": "w", "ttl": 60})
    assert r.status_code == 200
    view_url = r.json()["view_url"]
    session_id = r.json()["session_id"]

    # Valid token
    r = client.get(view_url.replace(MASTER_URL, ""))
    assert r.status_code == 200

    # Invalid token
    r = client.get(f"/view/{session_id}?token=invalid")
    assert r.status_code == 403

    client.post("/api/pool/release", json={"session_id": session_id, "owner": "w"})
