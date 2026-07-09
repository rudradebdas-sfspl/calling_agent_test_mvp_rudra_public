def test_agent_crud_and_sip_default(app_client):
    create_resp = app_client.post("/api/agents", json={"name": "CI Agent", "vad_mode": "normal"})
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    agent_id = created["id"]

    list_resp = app_client.get("/api/agents")
    assert list_resp.status_code == 200
    assert any(row["id"] == agent_id for row in list_resp.json())

    update_payload = {k: v for k, v in created.items() if k != "id"}
    update_payload["name"] = "CI Agent Updated"
    update_resp = app_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["name"] == "CI Agent Updated"

    default_resp = app_client.post(f"/api/agents/{agent_id}/set-sip-default")
    assert default_resp.status_code == 200, default_resp.text
    assert default_resp.json()["is_sip_default"] is True

    delete_resp = app_client.delete(f"/api/agents/{agent_id}")
    assert delete_resp.status_code == 204

    missing_resp = app_client.get(f"/api/agents/{agent_id}")
    assert missing_resp.status_code == 404