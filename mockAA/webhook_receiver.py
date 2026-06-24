# webhook_receiver.py
# This is the endpoint in YOUR app that receives data from the mock AA

from fastapi import FastAPI, Request, HTTPException
from datetime import datetime
import json, uuid
from pathlib import Path

app = FastAPI(title="ClinicOS FIU Webhook Receiver")

# For local dev — save to a folder instead of ADLS
RAW_DATA_PATH = Path("./raw_data")
RAW_DATA_PATH.mkdir(exist_ok=True)

@app.post("/webhook/aa/data")
async def receive_aa_data(request: Request):
    try:
        payload = await request.json()
        clinic_id   = payload.get("clinic_id", "unknown")
        consent_handle = payload.get("ConsentHandle", "unknown")

        # Save raw payload exactly as received
        # In production this goes to ADLS Gen2
        filename = RAW_DATA_PATH / f"{clinic_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}.json"
        with open(filename, "w") as f:
            json.dump(payload, f, indent=2)

        # Extract and count transactions
        total_txns = 0
        for fi in payload.get("FI", []):
            for account in fi.get("data", []):
                txns = account.get("Transactions", {}).get("Transaction", [])
                total_txns += len(txns)

        print(f"Received {total_txns} transactions for clinic {clinic_id}")
        print(f"Saved to {filename}")

        # In production: trigger Azure Function to process the file
        # For now: call process_transactions directly
        await process_transactions(payload, clinic_id)

        return {
            "status": "received",
            "clinic_id": clinic_id,
            "transactions_received": total_txns,
            "saved_to": str(filename)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def process_transactions(payload: dict, clinic_id: str):
    """
    Extract transactions and run through categorisation.
    In production this is a separate Azure Function triggered by ADLS event.
    """
    all_transactions = []
    for fi in payload.get("FI", []):
        for account in fi.get("data", []):
            txns = account.get("Transactions", {}).get("Transaction", [])
            acc_num = account.get("maskedAccNumber", "UNKNOWN")
            for txn in txns:
                txn["clinic_id"] = clinic_id
                txn["account_number"] = acc_num
                txn["category"] = categorise(txn.get("narration", ""))
                txn["processed_at"] = datetime.now().isoformat()
            all_transactions.extend(txns)

    # Save processed transactions
    processed_file = RAW_DATA_PATH / f"{clinic_id}_processed.json"
    with open(processed_file, "w") as f:
        json.dump(all_transactions, f, indent=2)

    print(f"Processed and categorised {len(all_transactions)} transactions")

def categorise(narration: str) -> str:
    n = narration.lower()
    rules = {
        "pharma_supplies":    ["pharma", "medical", "medicine", "drug", "chemist"],
        "equipment":          ["equipment", "instruments", "surgical", "dental"],
        "consumables":        ["gloves", "disposables", "syringes", "sterimed"],
        "staff_salary":       ["salary", "wages", "staff"],
        "rent":               ["rent", "lease", "premises"],
        "utilities":          ["bescom", "bwssb", "electricity", "water", "broadband", "airtel", "billpay"],
        "insurance_receipt":  ["star health", "niva bupa", "care health", "hdfc ergo", "claim settlement"],
        "patient_collection": ["patient consult", "consultation", "treatment"],
        "loan_emi":           ["emi", "loan", "creditcard bill"],
    }
    for category, keywords in rules.items():
        if any(kw in n for kw in keywords):
            return category
    return "uncategorised"

@app.get("/transactions/{clinic_id}")
async def get_transactions(clinic_id: str):
    processed_file = RAW_DATA_PATH / f"{clinic_id}_processed.json"
    if not processed_file.exists():
        return {"error": "No data found for this clinic"}
    with open(processed_file) as f:
        data = json.load(f)
    return {
        "clinic_id": clinic_id,
        "total": len(data),
        "by_category": _group_by_category(data),
        "transactions": data[:20]  # Return first 20 as preview
    }

def _group_by_category(transactions):
    result = {}
    for txn in transactions:
        cat = txn.get("category", "uncategorised")
        if cat not in result:
            result[cat] = {"count": 0, "total_debit": 0, "total_credit": 0}
        result[cat]["count"] += 1
        if txn.get("type") == "DEBIT":
            result[cat]["total_debit"] += txn.get("amount", 0)
        else:
            result[cat]["total_credit"] += txn.get("amount", 0)
    return result