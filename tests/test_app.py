"""
Sample tests for your Family Expense Tracker app.
You can expand these as you add more features!
"""
import pytest
from app import app

# This fixture gives us a test client for our Flask app
@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_homepage(client):
    """Test that the homepage loads successfully and contains the dashboard header."""
    response = client.get('/')
    assert response.status_code == 200
    if b"Income & Expenses Overview" not in response.data:
        print("\n==== RESPONSE BODY START ====")
        print(response.data.decode(errors='replace'))
        print("==== RESPONSE BODY END ====")
    assert b"Income & Expenses Overview" in response.data

# Add more tests here as you expand your app
