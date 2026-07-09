def test_kb_text_upload_list_and_delete(app_client):
    agent_resp = app_client.post("/api/agents", json={"name": "KB CI Agent", "kb_enabled": True})
    assert agent_resp.status_code == 201, agent_resp.text
    agent_id = agent_resp.json()["id"]

    upload_resp = app_client.post(
        f"/api/agents/{agent_id}/kb",
        files=[
            (
                "files",
                (
                    "it_policy.txt",
                    b"Password reset must be handled by IT support. VPN issues need network checks.",
                    "text/plain",
                ),
            )
        ],
    )
    assert upload_resp.status_code == 201, upload_resp.text
    assert upload_resp.json()["inserted_chunks"] >= 1

    list_resp = app_client.get(f"/api/agents/{agent_id}/kb")
    assert list_resp.status_code == 200
    assert list_resp.json()["files"] == [{"filename": "it_policy.txt", "chunk_count": 1}]

    delete_resp = app_client.delete(f"/api/agents/{agent_id}/kb/it_policy.txt")
    assert delete_resp.status_code == 204

    list_after_delete = app_client.get(f"/api/agents/{agent_id}/kb")
    assert list_after_delete.status_code == 200
    assert list_after_delete.json()["files"] == []