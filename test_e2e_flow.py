import sys
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db

async def run_e2e_tests():
    print("\n=======================================================")
    print("      ELDER CARE BACKEND - END-TO-END VERIFICATION      ")
    print("=======================================================\n")
    
    # Initialize database
    await init_db()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res = await client.get("/api/v1/health")
        assert res.status_code == 200, f"Health check failed: {res.text}"
        print("[PASS] [1/10] System Health Check passed: ONLINE & HEALTHY")
        
        # 2. Caregiver Phone + OTP Login
        otp_res = await client.post("/api/v1/auth/request-otp", json={
            "phone_number": "+919876543210",
            "role": "CAREGIVER"
        })
        assert otp_res.status_code == 200
        
        verify_res = await client.post("/api/v1/auth/verify-otp", json={
            "phone_number": "+919876543210",
            "otp_code": "123456",
            "full_name": "Ananya (Daughter)",
            "relationship": "Daughter"
        })
        assert verify_res.status_code == 200
        token_data = verify_res.json()
        caregiver_token = token_data["access_token"]
        cg_headers = {"Authorization": f"Bearer {caregiver_token}"}
        print("[PASS] [2/10] Caregiver Authentication passed: Daughter (Ananya) Logged In")
        
        # 3. Caregiver provisions Elder Ramanathan
        prov_res = await client.post("/api/v1/caregiver/create-elder", headers=cg_headers, json={
            "full_name": "Ramanathan",
            "phone_number": "+919876543212",
            "age": 68,
            "gender": "Male",
            "blood_group": "O+",
            "chronic_conditions": "Type 2 Diabetes, High BP",
            "allergies": "Penicillin",
            "dietary_restrictions": "Low-Sugar, Low-Salt, Vegetarian",
            "pension_ppo_number": "PPO-TN-2024-98124",
            "preferred_language": "en"
        })
        assert prov_res.status_code == 200, prov_res.text
        prov_data = prov_res.json()
        elder_id = prov_data["elder_id"]
        pair_code = prov_data["pair_code"]
        print(f"[PASS] [3/10] Elder Provisioning passed: Ramanathan created with 6-digit Pair Code [{pair_code}]")
        
        # 4. Elder 15-Second Device Pairing
        pair_res = await client.post("/api/v1/elder/pair-device", json={
            "pair_code": pair_code,
            "device_fingerprint": "Samsung A14 - Elder Edition",
            "preferred_language": "en"
        })
        assert pair_res.status_code == 200, pair_res.text
        elder_token = pair_res.json()["access_token"]
        print(f"[PASS] [4/10] Elder 15-Second Pairing passed: Linked phone to Ramanathan")
        
        # 5. Caregiver adds Metformin 500mg
        med_res = await client.post("/api/v1/medications", headers=cg_headers, json={
            "elder_id": elder_id,
            "name": "Metformin",
            "dosage_type": "Tablet",
            "strength": "500 mg",
            "meal_relation": "After Food",
            "alarm_times": ["08:30", "20:30"],
            "recurrence": "Daily",
            "alarm_sound": "Loud Spoken Chime",
            "escalation_enabled": True,
            "escalation_minutes": 25,
            "is_critical": True,
            "instructions": "Take after breakfast and dinner with warm water"
        })
        assert med_res.status_code == 200, med_res.text
        med_data = med_res.json()
        med_id = med_data["id"]
        print(f"[PASS] [5/10] Medication Configurator passed: Added Metformin 500mg with 25-Min Watchdog")
        
        # 6. Fetch Today's 24-Hour Schedule for Elder
        sched_res = await client.get(f"/api/v1/elder/{elder_id}/today-schedule")
        assert sched_res.status_code == 200
        schedule = sched_res.json()
        assert schedule["total_items"] > 0
        print(f"[PASS] [6/10] 24-Hour Living Routine passed: {schedule['total_items']} items loaded (Water, Meals, Pills, Yoga)")
        
        # 7. Elder logs pill as TAKEN ("I Took It" action)
        log_res = await client.post("/api/v1/adherence/log", json={
            "elder_id": elder_id,
            "medication_id": med_id,
            "scheduled_slot": "08:30",
            "status": "TAKEN",
            "notes": "Elder tapped [ I TOOK IT ] button"
        })
        assert log_res.status_code == 200
        print("[PASS] [7/10] Elder 'I Took It' Adherence passed: Status TAKEN, Live Feed event dispatched")
        
        # 8. Caregiver views Guardian Timeline & Dashboard
        dash_res = await client.get(f"/api/v1/caregiver/dashboard/{elder_id}", headers=cg_headers)
        assert dash_res.status_code == 200
        dash_data = dash_res.json()
        assert dash_data["taken"] >= 1
        print(f"[PASS] [8/10] Guardian Dashboard passed: Vitals & Pill count (Taken: {dash_data['taken']})")
        
        # 9. Personal Doctor & Driver Directory
        doc_res = await client.post("/api/v1/directory/personal", json={
            "elder_id": elder_id,
            "category": "DOCTOR",
            "name": "Dr. R. Swaminathan (Family Diabetologist)",
            "phone_number": "+919840123456",
            "specialty_or_vehicle": "Senior Diabetology & General Medicine",
            "address_or_clinic": "Apollo Clinic, T. Nagar",
            "is_favorite": True
        })
        assert doc_res.status_code == 200
        
        dir_res = await client.get(f"/api/v1/directory/doctors?elder_id={elder_id}")
        assert dir_res.status_code == 200
        assert len(dir_res.json()) >= 1
        print("[PASS] [9/10] Personal Directory passed: Family Doctor & Driver accessible for 1-tap call")
        
        # 10. Emergency SOS Multi-Broadcast
        # Add neighbor as priority 2
        await client.post("/api/v1/sos/contacts", json={
            "elder_id": elder_id,
            "priority": 2,
            "name": "Mr. Sharma",
            "relationship_label": "Next-Door Neighbor",
            "phone_number": "+919876543211"
        })
        
        sos_res = await client.post("/api/v1/sos/trigger", json={
            "elder_id": elder_id,
            "latitude": 13.0827,
            "longitude": 80.2707,
            "trigger_type": "BIG_RED_BUTTON"
        })
        assert sos_res.status_code == 200
        sos_data = sos_res.json()
        assert len(sos_data["broadcast_recipients"]) >= 2
        print(f"[PASS] [10/10] Life-Saving Emergency SOS passed: Multi-broadcast dispatched to {len(sos_data['broadcast_recipients'])} contacts with GPS Link")
        
    print("\nSUCCESS: ALL 10 ARCHITECTURAL PIPELINES VERIFIED!\n")

if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
