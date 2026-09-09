import sys
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db
from app.core.security import create_access_token

async def test_auth_and_authorisation():
    print("\n=======================================================")
    print("   AUTHENTICATION & AUTHORIZATION (RBAC) VERIFICATION  ")
    print("=======================================================\n")
    
    await init_db()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        # -------------------------------------------------------------
        # PART 1: AUTHENTICATION TESTS (401 & 400 Verification)
        # -------------------------------------------------------------
        print("--- [PART 1: AUTHENTICATION] ---")
        
        # 1. No Token on Protected Endpoint -> 401 Unauthorized
        res_no_token = await client.get("/api/v1/auth/me")
        assert res_no_token.status_code == 401, f"Expected 401, got {res_no_token.status_code}"
        print("[PASS] 1. Unauthenticated request to /auth/me correctly rejected with HTTP 401")
        
        # 2. Forged / Invalid Token on Protected Endpoint -> 401 Unauthorized
        res_bad_token = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.value"})
        assert res_bad_token.status_code == 401, f"Expected 401, got {res_bad_token.status_code}"
        print("[PASS] 2. Forged/invalid Bearer token correctly rejected with HTTP 401")
        
        # 3. Request OTP for Caregiver
        cg_phone = "+919111222333"
        await client.post("/api/v1/auth/request-otp", json={
            "identifier": cg_phone,
            "channel": "PHONE",
            "role": "CAREGIVER"
        })
        
        # 4. Register Caregiver with Password
        reg_cg_res = await client.post("/api/v1/auth/register", json={
            "full_name": "Kavitha Raman",
            "registration_type": "PHONE",
            "phone_number": cg_phone,
            "otp_code": "123456",
            "password": "CorrectPassword!2026",
            "role": "CAREGIVER",
            "relationship_to_elder": "Daughter"
        })
        if reg_cg_res.status_code == 201:
            cg_token = reg_cg_res.json()["access_token"]
            cg_id = reg_cg_res.json()["user_id"]
            print("[PASS] 3. Caregiver registered (HTTP 201 Created) with JWT token issued")
        else:
            # Login if already registered in previous run
            login_res = await client.post("/api/v1/auth/login", json={
                "identifier": cg_phone,
                "login_method": "PASSWORD",
                "password": "CorrectPassword!2026"
            })
            cg_token = login_res.json()["access_token"]
            cg_id = login_res.json()["user_id"]
            print("[PASS] 3. Caregiver logged in with password, JWT token acquired")
            
        # 5. Wrong Password Login -> 401 Unauthorized
        res_wrong_pw = await client.post("/api/v1/auth/login", json={
            "identifier": cg_phone,
            "login_method": "PASSWORD",
            "password": "WRONG_PASSWORD_HERE"
        })
        assert res_wrong_pw.status_code == 401, f"Expected 401, got {res_wrong_pw.status_code}"
        print("[PASS] 4. Incorrect password rejected with HTTP 401 Unauthorized")
        
        # 6. Invalid OTP Login -> 400 Bad Request
        res_bad_otp = await client.post("/api/v1/auth/login", json={
            "identifier": cg_phone,
            "login_method": "OTP",
            "otp_code": "000000"
        })
        assert res_bad_otp.status_code == 400, f"Expected 400, got {res_bad_otp.status_code}"
        print("[PASS] 5. Incorrect OTP code rejected with HTTP 400 Bad Request")
        
        # 7. Valid Token Authentication -> 200 OK on /auth/me
        res_me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {cg_token}"})
        assert res_me.status_code == 200, f"Expected 200, got {res_me.status_code}"
        me_data = res_me.json()
        assert me_data["role"] == "CAREGIVER"
        print(f"[PASS] 6. Authenticated /auth/me verified: {me_data['full_name']} (Role: {me_data['role']})")

        # -------------------------------------------------------------
        # PART 2: AUTHORIZATION / RBAC TESTS (403 vs 200 Verification)
        # -------------------------------------------------------------
        print("\n--- [PART 2: AUTHORIZATION / RBAC] ---")
        
        # Generate Elder Token (role: "ELDER")
        elder_token = create_access_token({
            "sub": "9999",
            "role": "ELDER",
            "phone_number": "+919888877777",
            "name": "Senior Citizen Ramanathan"
        })
        
        # 1. Elder attempts Caregiver endpoint (provision-parent) -> 403 Forbidden!
        res_forbidden = await client.post(
            "/api/v1/caregiver/create-elder",
            headers={"Authorization": f"Bearer {elder_token}"},
            json={
                "full_name": "Parent Name",
                "age": 75,
                "chronic_conditions": "Diabetes",
                "allergies": "None",
                "dietary_restrictions": "Low sodium"
            }
        )
        assert res_forbidden.status_code == 403, f"Expected 403 Forbidden, got {res_forbidden.status_code}: {res_forbidden.text}"
        print(f"[PASS] 7. Elder token attempting Caregiver action rejected with HTTP 403 Forbidden: {res_forbidden.json()['detail']}")
        
        # 2. Elder attempts Medications endpoint -> 403 Forbidden!
        res_med_forbidden = await client.post(
            "/api/v1/medications",
            headers={"Authorization": f"Bearer {elder_token}"},
            json={
                "elder_id": 9999,
                "name": "Metformin",
                "dosage_type": "TABLET",
                "strength": "500mg",
                "meal_relation": "AFTER_MEAL",
                "alarm_times": ["08:00"]
            }
        )
        assert res_med_forbidden.status_code == 403, f"Expected 403 Forbidden, got {res_med_forbidden.status_code}"
        print("[PASS] 8. Elder token attempting Medication creation rejected with HTTP 403 Forbidden")
        
        # 3. Caregiver calls Caregiver endpoint -> 200 OK (Authorized!)
        res_cg_allowed = await client.post(
            "/api/v1/caregiver/create-elder",
            headers={"Authorization": f"Bearer {cg_token}"},
            json={
                "full_name": "Ramanathan Senior",
                "age": 78,
                "chronic_conditions": "Hypertension, Type-2 Diabetes",
                "allergies": "Penicillin",
                "dietary_restrictions": "Low Sodium, Diabetic Diet",
                "pension_ppo_number": "PPO-TN-2026-99"
            }
        )
        assert res_cg_allowed.status_code == 200, f"Expected 200 OK, got {res_cg_allowed.status_code}: {res_cg_allowed.text}"
        elder_res_data = res_cg_allowed.json()
        print(f"[PASS] 9. Caregiver token authorized for parent provisioning -> Pair code: {elder_res_data['pair_code']}")
        
        # 4. Caregiver calls Caregiver elders list -> 200 OK (Authorized!)
        res_list = await client.get(
            "/api/v1/caregiver/elders",
            headers={"Authorization": f"Bearer {cg_token}"}
        )
        assert res_list.status_code == 200, f"Expected 200 OK, got {res_list.status_code}"
        print(f"[PASS] 10. Caregiver token authorized to list managed elders -> Count: {len(res_list.json())}")

    print("\n=======================================================")
    print("  ALL AUTHENTICATION & AUTHORIZATION TESTS PASSED! 100% ")
    print("=======================================================\n")

if __name__ == "__main__":
    asyncio.run(test_auth_and_authorisation())
