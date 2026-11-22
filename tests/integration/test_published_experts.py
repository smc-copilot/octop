"""Published expert HTTP API integration coverage."""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests.support.auth import create_user

posix_only = pytest.mark.skipif(
    os.name != "posix", reason="local_shell backend workspace file ops unsupported on Windows"
)


async def _owner_and_peer(
    env: tuple[Any, Any, dict[str, str]],
) -> tuple[Any, Any, dict[str, str], dict[str, str], str]:
    client, server, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="publish_owner")
    peer_auth = await create_user(client, admin_auth, username="publish_peer")
    created = await client.post(
        "/api/agents/from-expert/default",
        headers=owner_auth,
        json={"name": "publish-source"},
    )
    assert created.status_code == 201, created.text
    return client, server, owner_auth, peer_auth, created.json()["agent_id"]


async def test_publish_list_install_and_unpublish_preserves_installed_fork(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Published default", "description": "A private forkable expert"},
    )
    assert published.status_code == 201, published.text
    expert = published.json()
    expert_id = expert["id"]
    assert expert["creator_username"] == "publish_owner"
    assert isinstance(expert["skill_count"], int)

    listed = await client.get("/api/experts/published", headers=peer_auth)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [expert_id]

    detail = await client.get(f"/api/experts/published/{expert_id}", headers=peer_auth)
    assert detail.status_code == 200, detail.text
    assert "manifest.json" in detail.json()["files"]

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        json={"name": "Peer installed expert", "description": "Peer copy"},
    )
    assert installed.status_code == 201, installed.text
    assert installed.json()["state"] == "starting"
    assert installed.json()["bootstrap_pending"] is True
    installed_agent_id = installed.json()["agent_id"]
    assert installed.json()["user_id"] != expert["created_by"]

    denied = await client.delete(f"/api/experts/published/{expert_id}", headers=peer_auth)
    assert denied.status_code == 403, denied.text

    unpublished = await client.delete(f"/api/experts/published/{expert_id}", headers=owner_auth)
    assert unpublished.status_code == 204, unpublished.text
    assert (await client.get("/api/experts/published", headers=peer_auth)).json() == []

    fork = await client.get(f"/api/agents/{installed_agent_id}", headers=peer_auth)
    assert fork.status_code == 200, fork.text
    assert fork.json()["name"] == "Peer installed expert"


@posix_only
async def test_install_published_expert_accepts_create_options(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Parametric published", "description": "source"},
    )
    assert published.status_code == 201, published.text
    expert_id = published.json()["id"]

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        json={
            "name": "Installed with options",
            "description": "fork with options",
            "default_model": "openai/gpt-4o-mini",
            "max_iters": 12,
            "backend": {"type": "local_shell"},
        },
    )
    assert installed.status_code == 201, installed.text
    agent_id = installed.json()["agent_id"]

    detail = await client.get(f"/api/agents/{agent_id}", headers=peer_auth)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["name"] == "Installed with options"
    assert body["default_model"] == "openai/gpt-4o-mini"
    assert body.get("max_iters") == 12
    config = body.get("config") or {}
    assert (config.get("backend") or {}).get("type") == "local_shell"


async def test_install_published_expert_does_not_copy_source_composer_defaults(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)
    source = (await client.get(f"/api/agents/{source_agent_id}", headers=owner_auth)).json()
    owner_kb = server.services.knowledge_repo.create_base(
        owner_user_id=source["user_id"], name="Publisher KB"
    )
    owner_connector = await client.post(
        "/api/connector-instances",
        headers=owner_auth,
        json={
            "kind": "tencent-docs",
            "display_name": "Publisher docs",
            "credentials": {"token": "owner-token"},
        },
    )
    assert owner_connector.status_code == 201, owner_connector.text
    patched = await client.patch(
        f"/api/agents/{source_agent_id}",
        headers=owner_auth,
        json={
            "knowledge_base_ids": [owner_kb.id],
            "mcp_servers": [owner_connector.json()["mcp_server_name"]],
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["knowledge_base_ids"] == [owner_kb.id]

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Published without composer defaults"},
    )
    assert published.status_code == 201, published.text
    expert_id = published.json()["id"]
    listed = await client.get("/api/experts/published", headers=peer_auth)
    assert listed.status_code == 200, listed.text
    card = next(row for row in listed.json() if row["id"] == expert_id)
    assert "knowledge_base_ids" not in card
    assert "mcp_servers" not in card
    detail = await client.get(f"/api/experts/published/{expert_id}", headers=peer_auth)
    assert detail.status_code == 200, detail.text
    assert "knowledge_base_ids" not in detail.json()
    assert "mcp_servers" not in detail.json()

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        json={"name": "Fork without inherited defaults"},
    )
    assert installed.status_code == 201, installed.text
    fork = (
        await client.get(f"/api/agents/{installed.json()['agent_id']}", headers=peer_auth)
    ).json()
    assert fork["knowledge_base_ids"] == []
    assert fork["mcp_servers"] == []

    peer_kb = server.services.knowledge_repo.create_base(
        owner_user_id=fork["user_id"], name="Installer KB"
    )
    peer_connector = await client.post(
        "/api/connector-instances",
        headers=peer_auth,
        json={
            "kind": "tencent-docs",
            "display_name": "Installer docs",
            "credentials": {"token": "peer-token"},
        },
    )
    assert peer_connector.status_code == 201, peer_connector.text
    mcp_name = peer_connector.json()["mcp_server_name"]
    picked = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        json={
            "name": "Fork with installer picks",
            "knowledge_base_ids": [peer_kb.id],
            "mcp_servers": [mcp_name],
        },
    )
    assert picked.status_code == 201, picked.text
    chosen = (
        await client.get(f"/api/agents/{picked.json()['agent_id']}", headers=peer_auth)
    ).json()
    assert chosen["knowledge_base_ids"] == [peer_kb.id]
    assert chosen["mcp_servers"] == [mcp_name]
    assert owner_kb.id not in chosen["knowledge_base_ids"]
    assert owner_connector.json()["mcp_server_name"] not in chosen["mcp_servers"]


@posix_only
async def test_install_keeps_source_quick_prompts_when_publish_body_omits_them(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="quickcard_owner")
    peer_auth = await create_user(client, admin_auth, username="quickcard_peer")
    created = await client.post(
        "/api/agents/from-expert/default",
        headers=owner_auth,
        json={"name": "quickcard-source"},
    )
    assert created.status_code == 201, created.text
    source_agent_id = created.json()["agent_id"]

    source_welcome = await client.get(
        f"/api/agents/{source_agent_id}/chat/welcome",
        headers=owner_auth,
    )
    assert source_welcome.status_code == 200, source_welcome.text
    source_prompts = source_welcome.json()["quick_prompts"]
    assert source_prompts

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={
            "name": "Quick card expert",
            "welcome_message": {"zh": "开始写代码吧", "en": "Let's write code"},
        },
    )
    assert published.status_code == 201, published.text

    installed = await client.post(
        f"/api/experts/published/{published.json()['id']}/install",
        headers=peer_auth,
        json={"name": "Quick card fork"},
    )
    assert installed.status_code == 201, installed.text

    unpublished = await client.delete(
        f"/api/experts/published/{published.json()['id']}",
        headers=owner_auth,
    )
    assert unpublished.status_code == 204, unpublished.text

    fork_welcome = await client.get(
        f"/api/agents/{installed.json()['agent_id']}/chat/welcome",
        headers=peer_auth,
    )
    assert fork_welcome.status_code == 200, fork_welcome.text
    assert fork_welcome.json()["quick_prompts"] == source_prompts


@posix_only
async def test_install_keeps_source_task_examples_when_publish_body_omits_them(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="taskex_owner")
    peer_auth = await create_user(client, admin_auth, username="taskex_peer")
    created = await client.post(
        "/api/agents/from-expert/default",
        headers=owner_auth,
        json={"name": "taskex-source"},
    )
    assert created.status_code == 201, created.text
    source_agent_id = created.json()["agent_id"]

    source_examples = await client.get(
        f"/api/agents/{source_agent_id}/cron/examples",
        headers=owner_auth,
    )
    assert source_examples.status_code == 200, source_examples.text
    source_payload = source_examples.json()["task_examples"]
    assert source_payload and source_payload["zh"] and source_payload["en"]

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Task example expert"},
    )
    assert published.status_code == 201, published.text

    installed = await client.post(
        f"/api/experts/published/{published.json()['id']}/install",
        headers=peer_auth,
        json={"name": "Task example fork"},
    )
    assert installed.status_code == 201, installed.text

    unpublished = await client.delete(
        f"/api/experts/published/{published.json()['id']}",
        headers=owner_auth,
    )
    assert unpublished.status_code == 204, unpublished.text

    fork_examples = await client.get(
        f"/api/agents/{installed.json()['agent_id']}/cron/examples",
        headers=peer_auth,
    )
    assert fork_examples.status_code == 200, fork_examples.text
    assert fork_examples.json()["task_examples"] == source_payload


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


async def test_published_list_exposes_snapshot_avatar(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)

    uploaded = await client.post(
        f"/api/agents/{source_agent_id}/avatar",
        headers=owner_auth,
        files={"file": ("face.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Avatar published"},
    )
    assert published.status_code == 201, published.text
    expert_id = published.json()["id"]
    icon_url = published.json().get("icon_url")
    assert isinstance(icon_url, str)
    assert icon_url.startswith(f"/api/experts/published/{expert_id}/avatar")
    assert "v=" in icon_url

    listed = await client.get("/api/experts/published", headers=peer_auth)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["id"] == expert_id)
    assert row["icon_url"] == icon_url

    got = await client.get(icon_url, headers=peer_auth)
    assert got.status_code == 200, got.text
    assert got.content == PNG
    assert got.headers["content-type"].startswith("image/png")


async def test_published_list_keeps_public_portrait_without_upload(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)
    portrait = "/experts/avatars/scene-healthcare.svg"
    server.services.agent_repo.update_config(source_agent_id, icon_url=portrait)

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Portrait published"},
    )
    assert published.status_code == 201, published.text
    assert published.json()["icon_url"] == portrait

    listed = await client.get("/api/experts/published", headers=peer_auth)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["id"] == published.json()["id"])
    assert row["icon_url"] == portrait


async def test_creator_can_refresh_published_expert(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Refreshable expert"},
    )
    assert published.status_code == 201, published.text
    before = published.json()["updated_at"]

    refreshed = await client.post(
        f"/api/experts/published/{published.json()['id']}/refresh",
        headers=owner_auth,
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["id"] == published.json()["id"]
    assert refreshed.json()["updated_at"] >= before


async def test_second_publish_of_same_source_is_rejected(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    first = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "First publish"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Duplicate publish"},
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "PUBLISHED_EXPERT_ALREADY_EXISTS"


async def test_admin_cannot_publish_another_users_agent(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="private_agent_owner")
    created = await client.post(
        "/api/agents/from-expert/default",
        headers=owner_auth,
        json={"name": "private source"},
    )
    assert created.status_code == 201, created.text

    published = await client.post(
        f"/api/agents/{created.json()['agent_id']}/publish-expert",
        headers=admin_auth,
        json={"name": "Admin must not publish"},
    )
    assert published.status_code == 403, published.text


async def _publish_expert(
    client: Any,
    owner_auth: dict[str, str],
    source_agent_id: str,
    *,
    name: str,
) -> str:
    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": name},
    )
    assert published.status_code == 201, published.text
    return published.json()["id"]


async def test_admin_installs_published_expert_as_user(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    """A-ASU-003/004/011: admin installs for employee; owner and response fields are correct."""
    from tests.support.auth import resolve_user_id

    client, server, admin_auth = env
    client, server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)
    expert_id = await _publish_expert(
        client, owner_auth, source_agent_id, name="Admin as_user target"
    )
    peer_id = await resolve_user_id(client, admin_auth, "publish_peer")

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=admin_auth,
        params={"as_user": peer_id},
        json={"name": "Employee expert", "description": "installed by admin"},
    )
    assert installed.status_code == 201, installed.text
    body = installed.json()
    assert body["user_id"] == peer_id
    assert body["published_expert_id"] == expert_id
    assert body["state"] == "starting"
    assert body["bootstrap_pending"] is True
    assert body["agent_id"]

    row = server.app_runtime.agent_registry.get_row(body["agent_id"])
    assert row is not None
    assert row.user_id == peer_id

    visible = await client.get(f"/api/agents/{body['agent_id']}", headers=peer_auth)
    assert visible.status_code == 200, visible.text
    assert visible.json()["user_id"] == peer_id
    assert visible.json()["name"] == "Employee expert"


async def test_install_as_user_forbidden_for_non_admin(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    """A-ASU-005: normal user cannot install for another user."""
    from tests.support.auth import resolve_user_id

    client, server, admin_auth = env
    client, server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)
    expert_id = await _publish_expert(client, owner_auth, source_agent_id, name="Forbidden as_user")
    owner_id = await resolve_user_id(client, admin_auth, "publish_owner")
    peer_id = await resolve_user_id(client, admin_auth, "publish_peer")
    before = {
        row.agent_id
        for row in server.app_runtime.agent_registry.list_rows()
        if row.user_id == peer_id
    }

    denied = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        params={"as_user": owner_id},
        json={"name": "Should not create"},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    after = {
        row.agent_id
        for row in server.app_runtime.agent_registry.list_rows()
        if row.user_id == peer_id
    }
    assert after == before


async def test_install_as_user_missing_target_returns_404(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    """A-ASU-010: admin targeting a missing user gets 404 and creates no agent."""
    client, server, admin_auth = env
    client, server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    expert_id = await _publish_expert(client, owner_auth, source_agent_id, name="Missing as_user")
    before = {row.agent_id for row in server.app_runtime.agent_registry.list_rows()}

    missing = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=admin_auth,
        params={"as_user": 999_999_999},
        json={"name": "Missing target"},
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    after = {row.agent_id for row in server.app_runtime.agent_registry.list_rows()}
    assert after == before


async def test_install_as_user_self_id_allowed(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    """A-ASU-009: user may pass as_user equal to their own id."""
    from tests.support.auth import resolve_user_id

    client, _server, admin_auth = env
    client, server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)
    expert_id = await _publish_expert(client, owner_auth, source_agent_id, name="Self as_user")
    peer_id = await resolve_user_id(client, admin_auth, "publish_peer")

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        params={"as_user": peer_id},
        json={"name": "Self installed"},
    )
    assert installed.status_code == 201, installed.text
    assert installed.json()["user_id"] == peer_id
    row = server.app_runtime.agent_registry.get_row(installed.json()["agent_id"])
    assert row is not None
    assert row.user_id == peer_id


async def test_install_as_user_respects_target_quota(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    """A-ASU-008: target user's max_agents quota is enforced, not the admin's."""
    from tests.support.auth import resolve_user_id

    client, server, admin_auth = env
    client, server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    expert_id = await _publish_expert(client, owner_auth, source_agent_id, name="Quota as_user")
    peer_id = await resolve_user_id(client, admin_auth, "publish_peer")
    before = {row.agent_id for row in server.app_runtime.agent_registry.list_rows()}

    patched = await client.patch(
        f"/api/users/{peer_id}",
        headers=admin_auth,
        json={"max_agents": 0},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["max_agents"] == 0

    denied = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=admin_auth,
        params={"as_user": peer_id},
        json={"name": "Over quota"},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "AGENT_QUOTA_EXCEEDED"
    after = {row.agent_id for row in server.app_runtime.agent_registry.list_rows()}
    assert after == before


async def test_install_as_user_validates_kb_for_target(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    """A-ASU-007: KB visibility is checked for the target user, not the admin actor."""
    from tests.support.auth import resolve_user_id

    client, server, admin_auth = env
    client, server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    expert_id = await _publish_expert(client, owner_auth, source_agent_id, name="KB as_user")
    peer_id = await resolve_user_id(client, admin_auth, "publish_peer")
    admin_id = await resolve_user_id(client, admin_auth, "admin")
    admin_kb = server.services.knowledge_repo.create_base(
        owner_user_id=admin_id, name="Admin-only KB"
    )
    before = {row.agent_id for row in server.app_runtime.agent_registry.list_rows()}

    denied = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=admin_auth,
        params={"as_user": peer_id},
        json={
            "name": "Should reject admin KB",
            "knowledge_base_ids": [admin_kb.id],
        },
    )
    assert denied.status_code == 404, denied.text
    assert denied.json()["error"]["code"] == "KNOWLEDGE_NOT_FOUND"
    after = {row.agent_id for row in server.app_runtime.agent_registry.list_rows()}
    assert after == before
