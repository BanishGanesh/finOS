# mock_aa_server.py
# Run with: uvicorn mock_aa_server:app --port 8001 --reload

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uuid, httpx, asyncio, random
from datetime import datetime, timedelta
import json

app = FastAPI(title="Mock AA Server")

# Store consents in memory
consents = {}

# ── Realistic Indian clinic transaction generator ──────────────────────────
PHARMA_VENDORS = [
    "SUNSHINE PHARMA DISTRIBUTORS",
    "MEDLINE PHARMA DIST PVT LTD",
    "SRI VENKATESHWARA MEDICALS",
    "VIJAYA DRUG HOUSE",
    "APOLLO PHARMACY DIST"
]
EQUIPMENT_VENDORS = [
    "DENTAL EQUIPMENT SOLUTIONS",
    "DR INSTRUMENTS PVT LTD",
    "MEDITECH SUPPLIES BLR",
    "SURGICAL HOUSE BANGALORE"
]
CONSUMABLES = [
    "GLOVES PLUS MEDICAL SUPPLIES",
    "DISPOSABLES INDIA PVT LTD",
    "STERIMED MEDICAL DEVICES"
]
INSURANCE = [
    "STAR HEALTH AND ALLIED INS",
    "NIVA BUPA HEALTH INS",
    "CARE HEALTH INSURANCE",
    "HDFC ERGO HEALTH INS"
]
STAFF = ["SALARY RECEPTIONIST", "SALARY DENTAL ASST", "SALARY NURSE"]
UTILITIES = ["BESCOM ELECTRICITY BILL", "BWSSB WATER CHARGES", "AIRTEL BROADBAND"]

def generate_months_transactions(clinic_id: str, months: int = 3):
    transactions = []
    start = datetime.now() - timedelta(days=30 * months)

    for m in range(months):
        month_start = start + timedelta(days=30 * m)

        # Revenue — UPI collections daily
        for day in range(1, 28):
            if random.random() > 0.25:
                txn_date = month_start + timedelta(days=day,
                    hours=random.randint(9, 18))
                transactions.append({
                    "txnId": str(uuid.uuid4()),
                    "type": "CREDIT",
                    "mode": random.choice(["UPI", "UPI", "UPI", "CASH_DEPOSIT"]),
                    "amount": round(random.uniform(500, 8000), 2),
                    "currentBalance": round(random.uniform(50000, 400000), 2),
                    "transactionTimestamp": txn_date.isoformat() + "Z",
                    "valueDate": txn_date.strftime("%Y-%m-%d"),
                    "narration": f"UPI/GPAY/{random.randint(9000000000,9999999999)}/PATIENT CONSULT",
                    "reference": str(uuid.uuid4())[:8].upper()
                })

        # Insurance reimbursement — delayed 60-90 days
        if m >= 2:
            ins_date = month_start + timedelta(days=random.randint(60, 90))
            transactions.append({
                "txnId": str(uuid.uuid4()),
                "type": "CREDIT",
                "mode": "NEFT",
                "amount": round(random.uniform(15000, 85000), 2),
                "currentBalance": round(random.uniform(80000, 500000), 2),
                "transactionTimestamp": ins_date.isoformat() + "Z",
                "valueDate": ins_date.strftime("%Y-%m-%d"),
                "narration": f"NEFT/{random.choice(INSURANCE)}/CLAIM SETTLEMENT",
                "reference": str(uuid.uuid4())[:8].upper()
            })

        # Pharma payments — 3-6 per month
        for _ in range(random.randint(3, 6)):
            d = month_start + timedelta(days=random.randint(1, 27))
            transactions.append({
                "txnId": str(uuid.uuid4()),
                "type": "DEBIT",
                "mode": random.choice(["NEFT", "UPI"]),
                "amount": round(random.uniform(5000, 45000), 2),
                "currentBalance": round(random.uniform(30000, 350000), 2),
                "transactionTimestamp": d.isoformat() + "Z",
                "valueDate": d.strftime("%Y-%m-%d"),
                "narration": f"NEFT/{random.choice(PHARMA_VENDORS)}",
                "reference": str(uuid.uuid4())[:8].upper()
            })

        # Equipment and consumables — 2-4 per month
        for _ in range(random.randint(2, 4)):
            d = month_start + timedelta(days=random.randint(1, 27))
            vendor = random.choice(EQUIPMENT_VENDORS + CONSUMABLES)
            transactions.append({
                "txnId": str(uuid.uuid4()),
                "type": "DEBIT",
                "mode": random.choice(["UPI", "NEFT", "CASH"]),
                "amount": round(random.uniform(1500, 35000), 2),
                "currentBalance": round(random.uniform(20000, 300000), 2),
                "transactionTimestamp": d.isoformat() + "Z",
                "valueDate": d.strftime("%Y-%m-%d"),
                "narration": f"UPI/GPAY/{vendor.replace(' ','')[:15].upper()}",
                "reference": str(uuid.uuid4())[:8].upper()
            })

        # Staff salaries — 1st-5th of month
        for staff in STAFF:
            d = month_start + timedelta(days=random.randint(1, 5))
            transactions.append({
                "txnId": str(uuid.uuid4()),
                "type": "DEBIT",
                "mode": "NEFT",
                "amount": round(random.uniform(12000, 32000), 2),
                "currentBalance": round(random.uniform(10000, 280000), 2),
                "transactionTimestamp": d.isoformat() + "Z",
                "valueDate": d.strftime("%Y-%m-%d"),
                "narration": f"IMPS/{staff}/MONTH {m+1}",
                "reference": str(uuid.uuid4())[:8].upper()
            })

        # Rent — 1st of month
        d = month_start + timedelta(days=1)
        transactions.append({
            "txnId": str(uuid.uuid4()),
            "type": "DEBIT",
            "mode": "NEFT",
            "amount": round(random.uniform(20000, 75000), 2),
            "currentBalance": round(random.uniform(10000, 250000), 2),
            "transactionTimestamp": d.isoformat() + "Z",
            "valueDate": d.strftime("%Y-%m-%d"),
            "narration": "RENT/CLINIC PREMISES/OWNER",
            "reference": str(uuid.uuid4())[:8].upper()
        })

        # Utilities — random days
        for util in UTILITIES:
            d = month_start + timedelta(days=random.randint(5, 25))
            transactions.append({
                "txnId": str(uuid.uuid4()),
                "type": "DEBIT",
                "mode": "UPI",
                "amount": round(random.uniform(800, 8000), 2),
                "currentBalance": round(random.uniform(10000, 250000), 2),
                "transactionTimestamp": d.isoformat() + "Z",
                "valueDate": d.strftime("%Y-%m-%d"),
                "narration": f"UPI/BILLPAY/{util.replace(' ','')}",
                "reference": str(uuid.uuid4())[:8].upper()
            })

        # Business credit card payment — sometimes
        if random.random() > 0.5:
            d = month_start + timedelta(days=random.randint(10, 20))
            transactions.append({
                "txnId": str(uuid.uuid4()),
                "type": "DEBIT",
                "mode": "NEFT",
                "amount": round(random.uniform(5000, 40000), 2),
                "currentBalance": round(random.uniform(10000, 250000), 2),
                "transactionTimestamp": d.isoformat() + "Z",
                "valueDate": d.strftime("%Y-%m-%d"),
                "narration": "HDFC CREDITCARD BILL PAYMENT",
                "reference": str(uuid.uuid4())[:8].upper()
            })

    return sorted(transactions, key=lambda x: x["transactionTimestamp"])


# ── AA API endpoints ────────────────────────────────────────────────────────

class ConsentRequest(BaseModel):
    clinic_id: str
    fiu_webhook_url: str
    months_of_data: int = 3

@app.post("/v1/consent/request")
async def create_consent(req: ConsentRequest, background_tasks: BackgroundTasks):
    consent_handle = str(uuid.uuid4())
    consents[consent_handle] = {
        "status": "PENDING",
        "clinic_id": req.clinic_id,
        "fiu_webhook_url": req.fiu_webhook_url,
        "months": req.months_of_data,
        "created_at": datetime.now().isoformat()
    }
    # Auto-approve after 2 seconds and deliver data
    background_tasks.add_task(auto_approve_and_deliver, consent_handle)
    return {
        "ver": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "txnid": str(uuid.uuid4()),
        "ConsentHandle": consent_handle,
        "status": "PENDING"
    }

@app.get("/v1/consent/{consent_handle}/status")
async def consent_status(consent_handle: str):
    consent = consents.get(consent_handle, {})
    return {
        "ConsentHandle": consent_handle,
        "ConsentStatus": {
            "id": consent_handle,
            "status": consent.get("status", "NOT_FOUND")
        }
    }

@app.get("/v1/consents")
async def list_consents():
    return {"consents": consents}

async def auto_approve_and_deliver(consent_handle: str):
    await asyncio.sleep(2)  # Simulate user approving on their banking app
    consent = consents.get(consent_handle)
    if not consent:
        return
    consents[consent_handle]["status"] = "ACTIVE"

    # Generate transactions for this clinic
    transactions = generate_months_transactions(
        consent["clinic_id"],
        consent["months"]
    )

    # Deliver to FIU webhook
    payload = {
        "ver": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "txnid": str(uuid.uuid4()),
        "ConsentHandle": consent_handle,
        "clinic_id": consent["clinic_id"],
        "FI": [{
            "fipID": "MOCK-HDFC-FIP",
            "data": [{
                "linkRefNumber": str(uuid.uuid4()),
                "maskedAccNumber": "XXXX" + str(random.randint(1000, 9999)),
                "Profile": {
                    "Holders": {"Holder": [{
                        "name": "Dr. Test Clinic Owner",
                        "dob": "1985-06-15",
                        "mobile": "9876543210"
                    }]}
                },
                "Summary": {
                    "currentBalance": str(round(random.uniform(50000, 400000), 2)),
                    "currency": "INR",
                    "exchgeRate": "",
                    "balanceDateTime": datetime.now().isoformat(),
                    "type": "CURRENT",
                    "branch": "Indiranagar Bangalore",
                    "facility": "OD",
                    "ifscCode": "HDFC0001234",
                    "micrCode": "560240132",
                    "openingDate": "2018-04-01",
                    "currentODLimit": "0",
                    "drawingLimit": "0",
                    "status": "ACTIVE"
                },
                "Transactions": {
                    "StartDate": (datetime.now() - timedelta(
                        days=30 * consent["months"])).strftime("%Y-%m-%d"),
                    "EndDate": datetime.now().strftime("%Y-%m-%d"),
                    "Transaction": transactions
                }
            }]
        }]
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                consent["fiu_webhook_url"],
                json=payload,
                timeout=10.0
            )
            print(f"Delivered {len(transactions)} transactions to webhook")
        except Exception as e:
            print(f"Webhook delivery failed: {e}")
            consents[consent_handle]["webhook_error"] = str(e)

@app.get("/health")
async def health():
    return {"status": "ok", "consents_in_memory": len(consents)}