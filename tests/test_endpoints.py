import requests
import json
import time
from pprint import pprint

BASE_URL = "http://localhost:8000"

def test_health():
    print("\n=== Testing Health Check ===")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status Code: {response.status_code}")
    print("Response:", response.json())
    assert response.status_code == 200


def test_check_surprise_box():
    print("\n=== Testing Check Surprise Box ===")
    test_data = {
        "user_id": "test_user_123",
        "date": "2024-06-09",
        "daily_metrics": {
            "login_streak": 5,
            "posts_created": 2,
            "comments_written": 3,
            "upvotes_received": 10,
            "quizzes_completed": 1,
            "buddies_messaged": 2,
            "karma_spent": 35,
            "karma_earned_today": 50
        }
    }
    response = requests.post(f"{BASE_URL}/check-surprise-box", json=test_data)
    print(f"Status Code: {response.status_code}")
    print("Response:")
    pprint(response.json())
    assert response.status_code == 200

def test_version():
    response = requests.get(f"{BASE_URL}/version")
    print(f"Status Code: {response.status_code}")
    print("Response:")
    pprint(response.json())
    data = response.json()
    assert "version" in data, "Missing 'version' in response"
    assert "modelVersion" in data, "Missing 'modelVersion' in response"
    assert "last_updated" in data, "Missing 'last_updated' in response"
    assert response.status_code == 200

def run_tests():
    tests = [
        test_health,
        test_check_surprise_box,
        test_version,
    ]
    
    print("=== Starting API Tests ===")
    results = []
    for test in tests:
        try:
            success = test()
            results.append((test.__name__, success))
        except Exception as e:
            print(f"Error in {test.__name__}: {str(e)}")
            results.append((test.__name__, False))
    
    # Print summary
    print("\n=== Test Summary ===")
    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{name}: {status}")
    
    # Check if all tests passed
    all_passed = all(success for _, success in results)
    print("\nAll tests passed!" if all_passed else "\nSome tests failed!")
    return 0 if all_passed else 1

if __name__ == "__main__":
    # Give the server a moment to start
    time.sleep(2)
    exit(run_tests())
