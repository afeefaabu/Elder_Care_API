# Project Architectural Directives & Vibe Coding Guidelines

> [!IMPORTANT]
> **MANDATORY ARCHITECTURE REFERENCES**:
> Any coding, vibe coding, UI/UX design, state management, or backend integration in this project MUST strictly follow the two foundational architecture specifications located in the project root:
> 1. `caregiver_complete_working_flow_architecture.md` (Caregiver / Family Member Complete Working Flow Architecture & Actions)
> 2. `elder_complete_working_flow_architecture.md` (Senior Citizen / Elder Complete Working Flow Architecture & Actions)

---

## 1. System Overview: 3-User Operating Model
This application is built around a unified **3-User Production Architecture**:
- **Senior Citizen (Elder)**: Voice-first, high-contrast, oversized touch targets (min 64x64 dp), 1-tap telephony, 400ms tremor debounce, zero deep navigation.
- **Caregiver (Son / Daughter / Nurse)**: "Guardian Mode", remote peace of mind, zero-effort parent provisioning, directory management for personal doctors/drivers, real-time adherence live feed, 25-minute fail-safe watchdog escalation.
- **Admin**: City-wide directory verification and system governance.

---

## 2. Core Pillars & Specifications

### Elder Client (`elder_complete_working_flow_architecture.md`)
- **Typography**: Minimum 24pt - 32pt high-legibility sans-serif text.
- **Touch Target**: Minimum 64 x 64 dp for every interactive element.
- **Palette**: Pure Black (`#000000`), Pure White (`#FFFFFF`), Emergency Red (`#D32F2F`), Confirm Green (`#2E7D32`), Alert Amber (`#F57F17`).
- **Feedback**: Audio readouts on button touch, 400ms tremor debounce.
- **Core 6 Actions**:
  1. 24-Hour Living Routine (Hydration, Meals, Mobility, Alarms)
  2. Medication Alarms & Adherence (Photo verification, Loud voice, "I Took It", Escalation)
  3. 1-Tap Doctor Calling & Request (Direct clinic line / SMS)
  4. 1-Tap Taxi & Transport Booking (Direct call / GPS SMS dispatch)
  5. Pension & Welfare Portal (Voice status check & direct DBT status)
  6. Emergency SOS (Big Red Button, physical trigger, loud siren, multi-channel alert)

### Caregiver Client (`caregiver_complete_working_flow_architecture.md`)
- **Guardian Dashboard**: At-a-glance status of meals, pills, vitals, and battery levels.
- **Zero-Effort Parent Provisioning**: Caregiver handles all complex data entry (chronic conditions, allergies, diet plans).
- **Personal Directory Management**: Manage trusted family doctors and local drivers directly for the elder.
- **Fail-Safe Watchdog**: 25-minute automatic escalation with push alarms and SMS if critical meds are missed.
- **Multi-Elder Support**: Seamless toggle between multiple seniors under care.

---

## 3. Directives for AI Agents & Developers
- Always consult the corresponding architectural flowchart and screen lifecycle before writing or refactoring code.
- Ensure all Flutter widgets respect ergonomic constraints (font sizing, button heights, contrast ratios).
- Maintain end-to-end alignment between Elder actions and Caregiver real-time tracking feeds.
