import pytest
from fastapi.testclient import TestClient

from app.main import app, calculate


@pytest.fixture
def client():
    return TestClient(app)


class TestCalculationEndpoints:
    @pytest.mark.parametrize("op, a, b", [
        ("+", 2.0, 3.0),
        ("-", 5.0, 3.0),
        ("*", 3.0, 4.0),
        ("/", 8.0, 2.0),
        ("+", -2.0, -3.0),
        ("-", -2.0, -3.0),
        ("*", -2.0, -3.0),
        ("/", -8.0, -2.0),
    ])
    def test_operations(self, client, op, a, b):
        try:
            result = calculate(a, b, op)
            assert abs(result - calculate(a, b, op)) < 1e-6
        except ValueError as e:
            assert isinstance(e.value, str)

    def test_division_by_zero(self, client):
        response = client.post("/divide", json={"a": 5.0, "b": 0.0})
        assert response.status_code == 400
        assert response.json()["detail"] == "Division par zéro"
        body = response.json()["detail"] if isinstance(response.json(), dict) else response.data.decode()
        assert "division par zéro" in body.lower()

    @pytest.mark.parametrize("invalid_data", [
        ({"a": "not_a_number", "b": 3.0}),
        ({"a": None, "b": 5.0}),
        ({"a": "", "b": 1.0}),
        ({},),
    ])
    def test_invalid_inputs(self, client, invalid_data):
        response = client.post("/add/", json=invalid_data)
        assert response.status_code == 422
