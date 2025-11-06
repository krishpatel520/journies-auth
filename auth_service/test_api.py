#!/usr/bin/env python
"""
Automated API Testing Script for Auth Service
Run this to test all endpoints and see data in database
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8001"

# Test data
TENANT_CODE = f"TEST{int(time.time())}"  # Unique tenant code
ADMIN_EMAIL = f"admin_{int(time.time())}@test.com"
USER_EMAIL = f"user_{int(time.time())}@test.com"
PASSWORD = "88eb2eccfd54329091049ca50a9b804879a54021117a5ef7e5883a1d61bc18cd"  # SHA256 hash

# Store tokens
ACCESS_TOKEN = None
REFRESH_TOKEN = None
USER_ID = None
VERIFICATION_TOKEN = None
CREATED_USERS = []  # Store all created users for updates


def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_response(response, title="Response"):
    """Pretty print API response"""
    print(f"📌 {title}")
    print(f"Status Code: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")
    print()


def test_health_check():
    """Test 1: Health Check"""
    print_section("1️⃣  HEALTH CHECK")
    response = requests.get(f"{BASE_URL}/health/")
    print_response(response, "Health Check")
    return response.status_code == 200


def test_signup():
    """Test 2: Signup (Create Tenant & Admin)"""
    print_section("2️⃣  SIGNUP - Create Tenant & Admin User")

    data = {
        "tenant_name": "Test Company",
        "tenant_code": TENANT_CODE,
        "email": ADMIN_EMAIL,
        "password": PASSWORD,
        "first_name": "Admin",
        "last_name": "User"
    }

    print(f"📤 Request Data:")
    print(json.dumps(data, indent=2))
    print()

    response = requests.post(f"{BASE_URL}/api/v1/users/signup/", json=data)
    print_response(response, "Signup Response")

    if response.status_code == 201:
        result = response.json()
        print(f"✅ Signup successful!")
        print(f"📝 Email: {result.get('email')}")
        print(f"📝 Verification Required: {result.get('verification_required')}")
        print(f"📝 Message: {result.get('message')}\n")
        return True
    return False


def test_verify_email_and_get_tokens():
    """Test 2B: Verify Email to Get Tokens"""
    global ACCESS_TOKEN, REFRESH_TOKEN, VERIFICATION_TOKEN

    print_section("2️⃣ B️⃣  VERIFY EMAIL & GET TOKENS")

    print("⚠️  Retrieving verification token from database for testing...\n")

    try:
        import os
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_service.settings')
        django.setup()

        from auth_app.models.user_model import UserModel
        user = UserModel.objects.get(email=ADMIN_EMAIL)
        VERIFICATION_TOKEN = user.email_verification_token

        if VERIFICATION_TOKEN:
            print(f"📝 Verification token retrieved: {VERIFICATION_TOKEN[:20]}...\n")

            data = {"token": VERIFICATION_TOKEN}
            response = requests.post(f"{BASE_URL}/api/v1/users/verify_email/", json=data)
            print_response(response, "Email Verification Response")

            if response.status_code == 200:
                result = response.json()
                ACCESS_TOKEN = result.get('access_token')
                REFRESH_TOKEN = result.get('refresh_token')
                print(f"✅ Email verified successfully!")
                print(f"📝 Access Token: {ACCESS_TOKEN[:50] if ACCESS_TOKEN else 'None'}...")
                print(f"📝 Refresh Token: {REFRESH_TOKEN[:50] if REFRESH_TOKEN else 'None'}...\n")
                return True
        else:
            print("❌ Could not retrieve verification token\n")
            return False

    except Exception as e:
        print(f"❌ Error during email verification: {e}\n")
        return False


def test_login():
    """Test 3: Login"""
    global ACCESS_TOKEN, REFRESH_TOKEN
    
    print_section("3️⃣  LOGIN")
    
    data = {
        "email": ADMIN_EMAIL,
        "password": PASSWORD
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/users/login/", json=data)
    print_response(response, "Login Response")
    
    if response.status_code == 200:
        result = response.json()
        ACCESS_TOKEN = result.get('access_token')
        REFRESH_TOKEN = result.get('refresh_token')
        print(f"✅ Login successful!\n")
        return True
    return False


def test_list_users():
    """Test 4: List Users"""
    print_section("4️⃣  LIST USERS")
    
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/v1/users/", headers=headers)
    print_response(response, "List Users Response")
    
    return response.status_code == 200


def test_create_three_users():
    """Test 5: Create 3 New Users"""
    global CREATED_USERS

    print_section("5️⃣  CREATE 3 NEW USERS")

    users_data = [
        {"first_name": "Alice", "last_name": "Johnson", "email_prefix": "alice"},
        {"first_name": "Bob", "last_name": "Smith", "email_prefix": "bob"},
        {"first_name": "Charlie", "last_name": "Brown", "email_prefix": "charlie"}
    ]

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    for i, user_info in enumerate(users_data, 1):
        email = f"{user_info['email_prefix']}_{int(time.time())}_{i}@test.com"

        data = {
            "email": email,
            "password": PASSWORD,
            "first_name": user_info['first_name'],
            "last_name": user_info['last_name']
        }

        print(f"\n📤 Creating User {i}/3: {user_info['first_name']} {user_info['last_name']}")
        print(f"   Email: {email}")

        response = requests.post(f"{BASE_URL}/api/v1/users/", json=data, headers=headers)

        if response.status_code == 201:
            result = response.json()
            user_id = result.get('id') or result.get('user_id') or result.get('uuid')
            CREATED_USERS.append({
                'id': user_id,
                'email': email,
                'first_name': user_info['first_name'],
                'last_name': user_info['last_name']
            })
            print(f"   ✅ Created with ID: {user_id}")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
            try:
                print(f"   Error: {response.json()}")
            except:
                print(f"   Error: {response.text}")

    print(f"\n✅ Total users created: {len(CREATED_USERS)}\n")
    return len(CREATED_USERS) == 3


def test_get_user():
    """Test 6: Get Single User"""
    print_section("6️⃣  GET SINGLE USER")

    print(f"📝 Using USER_ID: {USER_ID}\n")

    if not USER_ID:
        print("❌ USER_ID is None or empty! Cannot test Get User.\n")
        return False

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/v1/users/{USER_ID}/", headers=headers)
    print_response(response, "Get User Response")

    return response.status_code == 200


def test_verify_token():
    """Test 7: Verify Token"""
    print_section("7️⃣  VERIFY TOKEN")
    
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.post(f"{BASE_URL}/api/v1/users/verify_token/", headers=headers)
    print_response(response, "Verify Token Response")
    
    return response.status_code == 200


def test_refresh_token():
    """Test 8: Refresh Token"""
    global ACCESS_TOKEN
    
    print_section("8️⃣  REFRESH TOKEN")
    
    data = {"refresh_token": REFRESH_TOKEN}
    response = requests.post(f"{BASE_URL}/api/v1/users/refresh_token/", json=data)
    print_response(response, "Refresh Token Response")
    
    if response.status_code == 200:
        ACCESS_TOKEN = response.json().get('access_token')
        print(f"✅ Token refreshed!\n")
        return True
    return False


def main():
    """Run all tests"""
    print("\n" + "🚀 "*20)
    print("AUTH SERVICE API TESTING SUITE")
    print("🚀 "*20)
    
    tests = [
        ("Health Check", test_health_check),
        ("Signup", test_signup),
        ("Verify Email & Get Tokens", test_verify_email_and_get_tokens),
        ("Login", test_login),
        ("List Users", test_list_users),
        ("Create 3 Users", test_create_three_users),
        ("Get User", test_get_user),
        ("Verify Token", test_verify_token),
        ("Refresh Token", test_refresh_token),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, "✅ PASS" if result else "❌ FAIL"))
        except Exception as e:
            print(f"❌ Error: {e}\n")
            results.append((name, f"❌ ERROR: {str(e)}"))
    
    # Print summary
    print_section("📊 TEST SUMMARY")
    for name, result in results:
        print(f"{name:.<40} {result}")

    # Print created users summary
    if CREATED_USERS:
        print_section("👥 CREATED USERS SUMMARY")
        print(f"Total users created: {len(CREATED_USERS)}\n")
        for i, user in enumerate(CREATED_USERS, 1):
            print(f"{i}. {user['first_name']} {user['last_name']}")
            print(f"   Email: {user['email']}")
            print(f"   ID: {user['id']}\n")

    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)
    print("\n📝 Check PgAdmin to see the data in database:")
    print("   - Database: auth_service_db1")
    print("   - Tables: auth_app_usermodel, auth_app_tenant")
    print("\n📝 Redis Stream Events:")
    print("   - Stream: journies:stream:users")
    print("   - Operation: CREATE (sent to Data-Sync)")
    print("\n📝 To update users, run: python test_update.py")
    print("\n")


if __name__ == "__main__":
    main()

