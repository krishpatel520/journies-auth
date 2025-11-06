#!/usr/bin/env python
"""
Automated API Testing Script for Updating Users
Run this to update existing users and send UPDATE events to Redis Stream
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8001"

# Store tokens
ACCESS_TOKEN = None
REFRESH_TOKEN = None
USERS_TO_UPDATE = []  # Store users to update


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


def test_login():
    """Test 1: Login to get tokens"""
    global ACCESS_TOKEN, REFRESH_TOKEN
    
    print_section("1️⃣  LOGIN - Get Access Tokens")
    
    print("📝 Enter your login credentials:")
    email = input("Email: ").strip()
    password = input("Password (SHA256 hash): ").strip()
    
    if not email or not password:
        print("❌ Email and password are required\n")
        return False
    
    data = {
        "email": email,
        "password": password
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/users/login/", json=data)
    print_response(response, "Login Response")
    
    if response.status_code == 200:
        result = response.json()
        ACCESS_TOKEN = result.get('access_token')
        REFRESH_TOKEN = result.get('refresh_token')
        print(f"✅ Login successful!")
        print(f"📝 Access Token: {ACCESS_TOKEN[:50] if ACCESS_TOKEN else 'None'}...")
        print(f"📝 Refresh Token: {REFRESH_TOKEN[:50] if REFRESH_TOKEN else 'None'}...\n")
        return True
    return False


def test_list_users():
    """Test 2: List all users to get their IDs"""
    global USERS_TO_UPDATE
    
    print_section("2️⃣  LIST USERS - Get User IDs")
    
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/v1/users/", headers=headers)
    print_response(response, "List Users Response")
    
    if response.status_code == 200:
        result = response.json()
        users = result.get('results', []) if isinstance(result, dict) else result
        
        if users:
            print(f"✅ Found {len(users)} users\n")
            print("Available users:")
            for i, user in enumerate(users, 1):
                user_id = user.get('id') or user.get('user_id') or user.get('uuid')
                print(f"{i}. {user.get('first_name', 'N/A')} {user.get('last_name', 'N/A')}")
                print(f"   Email: {user.get('email')}")
                print(f"   ID: {user_id}\n")
            
            USERS_TO_UPDATE = users
            return True
        else:
            print("❌ No users found\n")
            return False
    return False


def test_select_and_update_users():
    """Test 3: Select users and update them"""
    print_section("3️⃣  UPDATE USERS")
    
    if not USERS_TO_UPDATE:
        print("❌ No users available to update\n")
        return False
    
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    success_count = 0
    
    print("📝 Enter user indices to update (comma-separated, e.g., 1,2,3):")
    print("   Or press Enter to update all users\n")
    
    user_indices_input = input("User indices: ").strip()
    
    if user_indices_input:
        try:
            indices = [int(x.strip()) - 1 for x in user_indices_input.split(',')]
            users_to_update = [USERS_TO_UPDATE[i] for i in indices if 0 <= i < len(USERS_TO_UPDATE)]
        except (ValueError, IndexError):
            print("❌ Invalid input\n")
            return False
    else:
        users_to_update = USERS_TO_UPDATE
    
    for i, user in enumerate(users_to_update, 1):
        user_id = user.get('id') or user.get('user_id') or user.get('uuid')
        current_first_name = user.get('first_name', '')
        current_last_name = user.get('last_name', '')
        
        print(f"\n📝 Updating User {i}/{len(users_to_update)}: {current_first_name} {current_last_name}")
        print(f"   User ID: {user_id}")
        print(f"   Current Email: {user.get('email')}")
        
        print(f"\n   Enter new first name (current: {current_first_name}):")
        new_first_name = input("   New first name: ").strip() or current_first_name
        
        print(f"\n   Enter new last name (current: {current_last_name}):")
        new_last_name = input("   New last name: ").strip() or current_last_name
        
        data = {
            "first_name": new_first_name,
            "last_name": new_last_name
        }
        
        print(f"\n   📤 Sending update request...")
        print(f"   New Name: {new_first_name} {new_last_name}")
        
        response = requests.put(
            f"{BASE_URL}/api/v1/users/{user_id}/",
            json=data,
            headers=headers
        )
        
        if response.status_code == 200:
            print(f"   ✅ Updated successfully")
            print(f"   📝 UPDATE event sent to Redis Stream")
            success_count += 1
        else:
            print(f"   ❌ Failed with status {response.status_code}")
            try:
                print(f"   Error: {response.json()}")
            except:
                print(f"   Error: {response.text}")
    
    print(f"\n✅ Total users updated: {success_count}/{len(users_to_update)}\n")
    return success_count == len(users_to_update)


def main():
    """Run update tests"""
    print("\n" + "🚀 "*20)
    print("USER UPDATE TESTING SUITE")
    print("🚀 "*20)
    
    tests = [
        ("Login", test_login),
        ("List Users", test_list_users),
        ("Update Users", test_select_and_update_users),
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
    
    print("\n" + "="*60)
    print("✅ Update tests completed!")
    print("="*60)
    print("\n📝 Redis Stream Events:")
    print("   - Stream: journies:stream:users")
    print("   - Operation: UPDATE (sent to Data-Sync)")
    print("   - Action: update_user_vector() → Qdrant (UPSERT)")
    print("\n📝 Check PgAdmin to verify updates:")
    print("   - Database: auth_service_db1")
    print("   - Table: auth_app_usermodel")
    print("\n")


if __name__ == "__main__":
    main()

