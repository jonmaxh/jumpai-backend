import pytest


def test_list_categories_empty(authenticated_client):
    response = authenticated_client.get("/api/categories")
    assert response.status_code == 200
    assert response.json() == []


def test_list_categories(authenticated_client, test_category):
    response = authenticated_client.get("/api/categories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Category"
    assert data[0]["description"] == "A test category for emails"


def test_create_category(authenticated_client):
    response = authenticated_client.post("/api/categories", json={
        "name": "New Category",
        "description": "A new category"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Category"
    assert data["description"] == "A new category"
    assert "id" in data


def test_create_category_duplicate_name(authenticated_client, test_category):
    response = authenticated_client.post("/api/categories", json={
        "name": "Test Category",
        "description": "Duplicate"
    })
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_get_category(authenticated_client, test_category):
    response = authenticated_client.get(f"/api/categories/{test_category.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == test_category.name


def test_get_category_not_found(authenticated_client):
    response = authenticated_client.get("/api/categories/99999")
    assert response.status_code == 404


def test_update_category(authenticated_client, test_category):
    response = authenticated_client.put(f"/api/categories/{test_category.id}", json={
        "name": "Updated Category",
        "description": "Updated description"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Category"
    assert data["description"] == "Updated description"


def test_delete_category(authenticated_client, test_category):
    response = authenticated_client.delete(f"/api/categories/{test_category.id}")
    assert response.status_code == 200

    response = authenticated_client.get(f"/api/categories/{test_category.id}")
    assert response.status_code == 404


def test_categories_unauthenticated(client):
    response = client.get("/api/categories")
    assert response.status_code == 401
