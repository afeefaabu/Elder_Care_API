# Elder Care Production Backend API

A production-grade, asynchronous backend API built with **FastAPI**, **SQLAlchemy 2.0**, and **WebSockets**, implementing the **3-User Production Architecture** (Senior Citizen, Caregiver, and Admin).

---

## 🚀 Key Features

1. **15-Second Family Connect**: Caregiver provisions health profile (chronic conditions, allergies, diet) and generates a 6-digit code (e.g. `729140`) + QR code for instant pairing on the Elder's phone.
2. **24-Hour Daily Living Loop**: Pre-loaded schedule for hydration, diabetic meals, chair yoga, and bedtime reminders.
3. **Medication Configurator & Adherence**: Pill photo uploads, dosage rules, and 1-tap `[ 🟢 I TOOK IT ]` button.
4. **Real-Time Live Feed**: Instant WebSocket events broadcast to Caregiver's dashboard when pills are taken.
5. **25-Minute Escalation Watchdog**: Automated background engine that triggers siren push alarms and SMS if critical medications are unacknowledged after 25 minutes.
6. **Personal & City Directory**: Manage personal family doctors and local drivers directly for the elder, alongside verified city hospitals and ambulance services.
7. **Life-Saving Emergency SOS**: Big Red Button triggers simultaneous multi-channel SMS and siren push alerts with live Google Maps links to Priority 1 (Caregiver) and Priority 2 (Next-Door Neighbor).
8. **Pension & Welfare Portal**: Voice-enabled query endpoint for Direct Benefit Transfer (DBT) and PFMS pension disbursements.

---

## 🛠️ Quick Start (Local Run)

### 1. Activate Environment & Install Dependencies
```powershell
cd c:\Users\zainu\Desktop\Zainul_Abideeen_PRIVATE\PROJECTS\Flutter\elder_care_backend
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Start the API Server
```powershell
python run.py
```
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Alternative ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check**: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

---

## 🧪 Run Automated Verification Tests
```powershell
python test_e2e_flow.py
```

---

## 📡 Core API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/auth/request-otp` | Request OTP for Caregiver |
| `POST` | `/api/v1/auth/verify-otp` | Verify OTP and return JWT access token |
| `POST` | `/api/v1/caregiver/create-elder` | Provision health profile & generate 6-digit pair code |
| `GET` | `/api/v1/caregiver/elders` | List all seniors under care |
| `GET` | `/api/v1/caregiver/dashboard/{id}` | Guardian mode adherence counts & vitals |
| `POST` | `/api/v1/elder/pair-device` | 15-second pairing with 6-digit code |
| `GET` | `/api/v1/elder/{id}/today-schedule`| Full 24-hour chronological daily routine + meds |
| `POST` | `/api/v1/medications` | Add medicine with alarm times & escalation rules |
| `POST` | `/api/v1/adherence/log` | Elder taps "I TOOK IT" $\rightarrow$ triggers live WebSocket |
| `GET` | `/api/v1/adherence/timeline` | Adherence logs & timeline for caregiver |
| `POST` | `/api/v1/directory/personal` | Add personal family doctor or local driver |
| `GET` | `/api/v1/directory/doctors` | Personal doctors + city verified hospitals |
| `GET` | `/api/v1/directory/taxis` | Trusted local drivers + city taxi dispatch |
| `POST` | `/api/v1/sos/trigger` | Emergency SOS broadcast to family & neighbor |
| `GET` | `/api/v1/welfare/pension-status` | Senior citizen DBT pension status check |
| `WS` | `/api/v1/ws/adherence/{id}` | Real-time WebSocket connection for Guardian Mode |
