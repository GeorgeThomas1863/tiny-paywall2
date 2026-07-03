async def test_hello_returns_message(client):
    response = await client.get("/hello")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}
