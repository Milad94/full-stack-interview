def test_health_endpoint(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# TODO(candidate): we care most about tests around the sync — idempotency on a
# second run, and behaviour when the external service fails mid-pagination.
# `responses` is available for stubbing the vendor HTTP calls.
