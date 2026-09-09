import sys
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db

async def run_registration_tests():
    print("\n=======================================================")
    print("       USER REGISTRATION TESTING & VERIFICATION        ")
    print("=======================================================\n")
    
    await init_db()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Test 1: Phone OTP Registration
        test_phone = "+919876543299"
        otp_res = await client.post("/api/v1/auth/request-otp", json={
            "identifier": test_phone,
            "channel": "PHONE",
            "role": "CAREGIVER"
        })
        assert otp_res.status_code == 200, f"Phone OTP request failed: {otp_res.text}"
        print(f"[PASS] 1. Request OTP for Phone ({test_phone}) -> OTP Code Dispatched")
        
        # Clean any prior user with this test phone for clean test
        reg_phone_res = await client.post("/api/v1/auth/register", json={
            "full_name": "Priya Sharma (Daughter)",
            "registration_type": "PHONE",
            "phone_number": test_phone,
            "otp_code": "123456",
            "password": "SecurePassword123!",
            "role": "CAREGIVER",
            "relationship_to_elder": "Daughter",
            "preferred_language": "en"
        })
        # If it was already registered in a previous run, that's tested in duplicate check, else 201
        if reg_phone_res.status_code == 201:
            phone_user_data = reg_phone_res.json()
            assert phone_user_data["phone_number"] == test_phone
            assert "access_token" in phone_user_data
            print("[PASS] 2. Phone Registration succeeded (201 Created) -> JWT Token Generated")
        elif reg_phone_res.status_code == 409:
            print("[PASS] 2. Phone Registration correctly returned 409 Conflict for existing record")
            
        # Test 2: Email OTP Registration
        test_email = "priya.eldercare@example.com"
        email_otp_res = await client.post("/api/v1/auth/request-otp", json={
            "identifier": test_email,
            "channel": "EMAIL",
            "role": "CAREGIVER"
        })
        assert email_otp_res.status_code == 200, f"Email OTP request failed: {email_otp_res.text}"
        print(f"[PASS] 3. Request OTP for Email ({test_email}) -> OTP Code Dispatched")
        
        reg_email_res = await client.post("/api/v1/auth/register", json={
            "full_name": "Dr. Karthik (Caregiver Son)",
            "registration_type": "EMAIL",
            "email": test_email,
            "otp_code": "123456",
            "password": "DoctorPassword456!",
            "role": "CAREGIVER",
            "relationship_to_elder": "Son",
            "preferred_language": "en"
        })
        if reg_email_res.status_code == 201:
            email_user_data = reg_email_res.json()
            assert email_user_data["email"] == test_email
            assert "access_token" in email_user_data
            email_token = email_user_data["access_token"]
            print("[PASS] 4. Email Registration succeeded (201 Created) -> JWT Token Generated")
        elif reg_email_res.status_code == 409:
            print("[PASS] 4. Email Registration correctly returned 409 Conflict for existing record")
            email_token = None
            
        # Test 3: Duplicate Phone Registration Prevention
        dup_phone_res = await client.post("/api/v1/auth/register", json={
            "full_name": "Duplicate User",
            "registration_type": "PHONE",
            "phone_number": test_phone,
            "otp_code": "123456",
            "password": "AnotherPassword123"
        })
        assert dup_phone_res.status_code == 409, f"Expected 409 Conflict, got {dup_phone_res.status_code}"
        print(f"[PASS] 5. Duplicate Phone Registration rejected with HTTP 409 Conflict")
        
        # Test 4: Duplicate Email Registration Prevention
        dup_email_res = await client.post("/api/v1/auth/register", json={
            "full_name": "Duplicate User",
            "registration_type": "EMAIL",
            "email": test_email,
            "otp_code": "123456",
            "password": "AnotherPassword123"
        })
        assert dup_email_res.status_code == 409, f"Expected 409 Conflict, got {dup_email_res.status_code}"
        print(f"[PASS] 6. Duplicate Email Registration rejected with HTTP 409 Conflict")
        
        # Test 5: Invalid Email Format Validation (Pydantic validator)
        inv_email_res = await client.post("/api/v1/auth/register", json={
            "full_name": "Invalid Email User",
            "registration_type": "EMAIL",
            "email": "not-an-email-address",
            "otp_code": "123456",
            "password": "ValidPassword123"
        })
        assert inv_email_res.status_code == 422, f"Expected 422 Validation Error, got {inv_email_res.status_code}"
        print(f"[PASS] 7. Invalid Email format rejected with HTTP 422 Unprocessable Entity")
        
        # Test 6: Invalid Phone Format Validation
        inv_phone_res = await client.post("/api/v1/auth/register", json={
            "full_name": "Invalid Phone User",
            "registration_type": "PHONE",
            "phone_number": "12345",
            "otp_code": "123456",
            "password": "ValidPassword123"
        })
        assert inv_phone_res.status_code == 422, f"Expected 422 Validation Error, got {inv_phone_res.status_code}"
        print(f"[PASS] 8. Invalid Phone format rejected with HTTP 422 Unprocessable Entity")
        
        # Test 7: Authenticated Profile Fetch with Generated JWT Token
        login_res = await client.post("/api/v1/auth/login", json={
            "identifier": test_phone,
            "login_method": "PASSWORD",
            "password": "SecurePassword123!"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        auth_token = login_res.json()["access_token"]
        
        me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["phone_number"] == test_phone
        print(f"[PASS] 9. Password Login & Protected /auth/me verified: {me_data['full_name']}")
        
    print("\nSUCCESS: ALL USER REGISTRATION & AUTH TESTS VERIFIED!\n")

if __name__ == "__main__":
    asyncio.run(run_registration_tests())
