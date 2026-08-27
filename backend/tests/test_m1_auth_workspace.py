from conftest import auth_header, register_user
from fastapi.testclient import TestClient


def test_first_register_creates_workspace_and_admin(client: TestClient) -> None:
    data = register_user(client, "admin")

    assert data["workspace"]["name"] == "默认团队"
    assert data["membership"]["role"] == "admin"

    response = client.get(
        "/api/v1/workspaces/current",
        headers=auth_header(data["tokens"]["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["id"] == data["workspace"]["id"]


def test_non_member_cannot_access_team_resources_until_admin_adds_them(
    client: TestClient,
) -> None:
    admin = register_user(client, "admin")
    viewer = register_user(client, "viewer")

    denied = client.get(
        "/api/v1/kbs",
        headers=auth_header(viewer["tokens"]["access_token"]),
    )
    assert denied.status_code == 403

    add = client.post(
        "/api/v1/workspaces/current/members",
        headers=auth_header(admin["tokens"]["access_token"]),
        json={"username": "viewer", "role": "viewer"},
    )
    assert add.status_code == 201

    allowed = client.get(
        "/api/v1/kbs",
        headers=auth_header(viewer["tokens"]["access_token"]),
    )
    assert allowed.status_code == 200


def test_refresh_and_logout_revoke_refresh_token(client: TestClient) -> None:
    admin = register_user(client, "admin")
    refresh_token = admin["tokens"]["refresh_token"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200

    logout = client.post(
        "/api/v1/auth/logout",
        headers=auth_header(refreshed.json()["access_token"]),
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert logout.status_code == 204

    reused = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert reused.status_code == 401


def test_last_admin_cannot_be_removed_or_downgraded(client: TestClient) -> None:
    admin = register_user(client, "admin")
    admin_id = admin["user"]["id"]
    headers = auth_header(admin["tokens"]["access_token"])

    downgrade = client.patch(
        f"/api/v1/workspaces/current/members/{admin_id}",
        headers=headers,
        json={"role": "viewer"},
    )
    assert downgrade.status_code == 409

    remove = client.delete(f"/api/v1/workspaces/current/members/{admin_id}", headers=headers)
    assert remove.status_code == 409
