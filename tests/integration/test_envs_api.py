"""Integration tests for /api/envs."""

from __future__ import annotations

from typing import Any


async def test_envs_crud_cycle(env: Any) -> None:
    c, srv, auth = env
    r = await c.get("/api/envs", headers=auth)
    assert r.status_code == 200
    assert r.json() == []

    r = await c.put("/api/envs", headers=auth, json={"TAVILY_API_KEY": "tvly-1", "FOO": "bar"})
    assert r.status_code == 200
    body = r.json()
    assert {row["key"] for row in body} == {"FOO", "TAVILY_API_KEY"}

    env_path = srv.paths.root / "env"
    assert env_path.is_file()
    assert "TAVILY_API_KEY" in env_path.read_text(encoding="utf-8")

    r = await c.delete("/api/envs/FOO", headers=auth)
    assert r.status_code == 200
    assert {row["key"] for row in r.json()} == {"TAVILY_API_KEY"}


async def test_envs_put_unsets_removed_process_keys(env: Any) -> None:
    import os

    c, _srv, auth = env
    r = await c.put("/api/envs", headers=auth, json={"GONE": "1", "KEEP": "2"})
    assert r.status_code == 200
    assert os.environ.get("GONE") == "1"
    r = await c.put("/api/envs", headers=auth, json={"KEEP": "2"})
    assert r.status_code == 200
    assert "GONE" not in os.environ
    assert os.environ.get("KEEP") == "2"


async def test_envs_redacts_captcha_secret_and_put_keeps_sentinel(env: Any) -> None:
    c, srv, auth = env
    r = await c.put(
        "/api/envs",
        headers=auth,
        json={
            "OCTOP_CAPTCHA_SECRET": "live-secret",
            "OCTOP_CAPTCHA_CAM_SECRET_KEY": "cam-live",
            "FOO": "bar",
        },
    )
    assert r.status_code == 200
    body = r.json()
    by_key = {row["key"]: row["value"] for row in body}
    assert by_key["OCTOP_CAPTCHA_SECRET"] == "********"
    assert by_key["OCTOP_CAPTCHA_CAM_SECRET_KEY"] == "********"
    assert "live-secret" not in str(body)
    assert "cam-live" not in str(body)
    env_path = srv.paths.root / "env"
    assert "live-secret" in env_path.read_text(encoding="utf-8")
    assert "cam-live" in env_path.read_text(encoding="utf-8")

    r = await c.put(
        "/api/envs",
        headers=auth,
        json={
            "OCTOP_CAPTCHA_SECRET": "********",
            "OCTOP_CAPTCHA_CAM_SECRET_KEY": "********",
            "FOO": "bar",
        },
    )
    assert r.status_code == 200
    env_text = env_path.read_text(encoding="utf-8")
    assert "live-secret" in env_text
    assert "cam-live" in env_text
    assert "********" not in env_path.read_text(encoding="utf-8")


async def test_envs_non_admin_forbidden(env: Any) -> None:
    c, _srv, admin_auth = env
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "bob", "password": "TestPass12", "role": "user"},
    )
    bob_tok = (
        await c.post("/api/auth/login", json={"username": "bob", "password": "TestPass12"})
    ).json()["access_token"]
    r = await c.get("/api/envs", headers={"Authorization": f"Bearer {bob_tok}"})
    assert r.status_code == 403


async def test_envs_put_preserves_shell_owned_keys(env: Any) -> None:
    """Deploy env files often pin OCTOP_HOME/PORT; Admin PUT must not 400 or wipe them."""
    c, srv, auth = env
    env_path = srv.paths.root / "env"
    env_path.write_text(
        "OCTOP_HOME=/home/smc/.octop\n"
        "OCTOP_BIND_HOST=0.0.0.0\n"
        "OCTOP_PORT=8088\n"
        "OCTOP_LOG_LEVEL=info\n",
        encoding="utf-8",
    )

    listed = await c.get("/api/envs", headers=auth)
    assert listed.status_code == 200, listed.text
    listed_keys = {row["key"] for row in listed.json()}
    assert "OCTOP_LOG_LEVEL" in listed_keys
    assert "OCTOP_HOME" not in listed_keys
    assert "OCTOP_PORT" not in listed_keys
    assert "OCTOP_BIND_HOST" not in listed_keys

    # Legacy UI may still round-trip shell-owned keys from an older GET.
    saved = await c.put(
        "/api/envs",
        headers=auth,
        json={
            "OCTOP_HOME": "/tmp/wrong",
            "OCTOP_BIND_HOST": "127.0.0.1",
            "OCTOP_PORT": "9",
            "OCTOP_LOG_LEVEL": "debug",
            "DEEPSEEK_API_KEY": "sk-test",
        },
    )
    assert saved.status_code == 200, saved.text
    saved_keys = {row["key"]: row["value"] for row in saved.json()}
    assert saved_keys["DEEPSEEK_API_KEY"] == "sk-test"
    assert saved_keys["OCTOP_LOG_LEVEL"] == "debug"
    assert "OCTOP_HOME" not in saved_keys

    text = env_path.read_text(encoding="utf-8")
    assert "OCTOP_HOME=/home/smc/.octop" in text
    assert "OCTOP_BIND_HOST=0.0.0.0" in text
    assert "OCTOP_PORT=8088" in text
    assert "OCTOP_LOG_LEVEL=debug" in text
    assert "DEEPSEEK_API_KEY=sk-test" in text
    assert "/tmp/wrong" not in text
