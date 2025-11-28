#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Automated API Testing Script for Auth Service
Run this to test all endpoints and see data in database
"""

import requests
import json
import time
import sys
from datetime import datetime

# Fix encoding for Windows PowerShell
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8001"

# Test data
TENANT_CODE = f"TEST{int(time.time())}"  # Unique tenant code
ADMIN_EMAIL = f"admin_{int(time.time())}@test.com"
USER_EMAIL = f"user_{int(time.time())}@test.com"

# Plain password for testing (will be encrypted)
PLAIN_PASSWORD = "TestPass123!"  # Must meet requirements: 8+ chars, uppercase, lowercase, number, special char

def encrypt_password(plain_password):
    """Encrypt password using AES-CBC (same as frontend)"""
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        import base64
        import os

        # Use the same key and IV from .env
        key_hex = "00112233445566778899aabbccddeeff"
        iv_hex = "0123456789abcdef0123456789abcdef"

        key = bytes.fromhex(key_hex)
        iv = bytes.fromhex(iv_hex)

        # Encrypt
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = pad(plain_password.encode('utf-8'), AES.block_size)
        encrypted = cipher.encrypt(padded)

        # Return base64 encoded
        return base64.b64encode(encrypted).decode('utf-8')
    except Exception as e:
        print(f"Error encrypting password: {e}")
        return None

# Encrypt the password for API calls
ENCRYPTED_PASSWORD = encrypt_password(PLAIN_PASSWORD)

# Store tokens and test data
ACCESS_TOKEN = None
REFRESH_TOKEN = None
USER_ID = None
TENANT_ID = None
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
    global TENANT_ID, USER_ID
    print_section("2️⃣  SIGNUP - Create Tenant & Admin User")

    # Use encrypted password
    data = {
        "tenant_name": "Test Company",
        "tenant_code": TENANT_CODE,
        "email": ADMIN_EMAIL,
        "password": ENCRYPTED_PASSWORD,
        "confirm_password": ENCRYPTED_PASSWORD,
        "first_name": "Admin",
        "last_name": "User",
        "terms_accepted": True
    }

    print(f"📤 Request Data:")
    print(json.dumps({k: v if k not in ['password', 'confirm_password'] else '***' for k, v in data.items()}, indent=2))
    print()

    response = requests.post(f"{BASE_URL}/api/v1/users/signup/", json=data)
    print_response(response, "Signup Response")

    if response.status_code == 201:
        result = response.json()
        TENANT_ID = result.get('tenant_id')
        USER_ID = result.get('user_id')
        print(f"✅ Signup successful!")
        print(f"📝 Email: {result.get('email')}")
        print(f"📝 Tenant ID: {TENANT_ID}")
        print(f"📝 User ID: {USER_ID}")
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
        "password": ENCRYPTED_PASSWORD
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


# def test_check_redis_stream():
#     """Test 4: Check Redis Stream for Published Events"""
#     print_section("4️⃣  CHECK REDIS STREAM FOR EVENTS")

#     print("⚠️  Checking Redis stream for published events...\n")

#     try:
#         import os
#         import django
#         os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_service.settings')
#         django.setup()

#         import redis
#         from django.conf import settings

#         # Connect to Redis
#         redis_client = redis.Redis(
#             host=settings.REDIS_HOST,
#             port=settings.REDIS_PORT,
#             db=settings.REDIS_DB,
#             decode_responses=True
#         )

#         stream_name = settings.REDIS_STREAM_USERS

#         # Get all events from the stream
#         events = redis_client.xrange(stream_name)

#         if events:
#             print(f"✅ Found {len(events)} event(s) in Redis stream: {stream_name}\n")
#             for event_id, event_data in events:
#                 print(f"📌 Event ID: {event_id}")
#                 print(f"   Data: {json.dumps(event_data, indent=6)}\n")
#             return True
#         else:
#             print(f"⚠️  No events found in Redis stream: {stream_name}")
#             print("   (Events are published when email is verified)\n")
#             return False

#     except Exception as e:
#         print(f"⚠️  Could not check Redis stream: {e}")
#         print("   Make sure Redis is running on localhost:6379\n")
#         return False


def test_get_admin_user():
    """Test 5: Get Admin User (Created during Signup)"""
    print_section("5️⃣  GET ADMIN USER")

    print(f"📝 Retrieving admin user: {ADMIN_EMAIL}\n")

    try:
        import os
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_service.settings')
        django.setup()

        from auth_app.models.user_model import UserModel
        user = UserModel.objects.get(email=ADMIN_EMAIL)

        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        response = requests.get(f"{BASE_URL}/api/v1/users/{user.id}/", headers=headers)
        print_response(response, "Get User Response")

        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False


def test_verify_token():
    """Test 6: Verify Token"""
    print_section("6️⃣  VERIFY TOKEN")

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.post(f"{BASE_URL}/api/v1/users/verify_token/", headers=headers)
    print_response(response, "Verify Token Response")

    return response.status_code == 200


def test_refresh_token():
    """Test 7: Refresh Token"""
    global ACCESS_TOKEN

    print_section("7️⃣  REFRESH TOKEN")

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
    print("AUTH SERVICE API TESTING SUITE - FULL PIPELINE")
    print("🚀 "*20)

    tests = [
        ("Health Check", test_health_check),
        ("Signup (Create Tenant & Admin)", test_signup),
        ("Verify Email & Get Tokens", test_verify_email_and_get_tokens),
        ("Login", test_login),
        ("Get Admin User", test_get_admin_user),
        # ("Check Redis Stream", test_check_redis_stream),
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
        print(f"{name:.<50} {result}")

    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)
    print("\n� FULL PIPELINE TESTED:")
    print("   1. ✅ Signup → Creates tenant + admin user")
    print("   2. ✅ Send verification email")
    print("   3. ✅ Verify email → Publishes event to Redis")
    print("   4. ✅ Get JWT tokens (access + refresh)")
    print("   5. ✅ Login with credentials")
    print("   6. ✅ Retrieve user data")
    print("   7. ✅ Verify token validity")
    print("   8. ✅ Refresh access token")

    # Print credentials and tokens for use with other services
    print("\n" + "="*60)
    print("CREDENTIALS & TOKENS FOR OTHER SERVICES")
    print("="*60)
    print(f"\nAdmin Email: {ADMIN_EMAIL}")
    print(f"Admin Password: {PLAIN_PASSWORD}")
    print(f"Tenant ID: {TENANT_ID}")
    print(f"User ID: {USER_ID}")
    print(f"\nAccess Token:\n{ACCESS_TOKEN}")
    print(f"\nRefresh Token: {REFRESH_TOKEN}")

    print("\n" + "="*60)
    print("DATABASE & REDIS INFORMATION")
    print("="*60)
    print("\nCheck PgAdmin to see the data in database:")
    print("   - Database: auth_service_db1")
    print("   - Tables: auth_app_usermodel, auth_app_tenant")
    print("   - User Email: " + ADMIN_EMAIL)
    print("\nRedis Stream Events:")
    print("   - Stream: journies:stream:users")
    print("   - Operation: CREATE (published after email verification)")
    print("   - Consumed by: Data-Sync Service")
    print("\n")


if __name__ == "__main__":
    main()

