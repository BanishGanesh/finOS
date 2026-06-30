# webhook_receiver.py — updated with PostgreSQL storage

from fastapi import FastAPI, Request, HTTPException
from datetime import datetime , date
import json, uuid, asyncpg, os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

# Database connection pool
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL",
            "postgresql://banishmg:admin@localhost:5433/clinicos")
    )
    yield
    await db_pool.close()


app = FastAPI(title="ClinicOS FIU Webhook", lifespan=lifespan)

def parse_date(date_str: str):
        """Convert date string to Python date object for asyncpg"""
        if not date_str:
            return None
        try:
            # Handle both date formats AA might send
            # Format 1: "2026-04-01"
            #Format 2: "2026-04-01T00:00:00Z"
            return datetime.strptime(
            date_str.split('T')[0], "%Y-%m-%d"
            ).date()
        except Exception:
            return None

@app.post("/webhook/aa/data")
async def receive_aa_data(request: Request):
    print("=== WEBHOOK CALLED ===")
    try:
        payload = await request.json()
        clinic_id      = payload.get("clinic_id")
        consent_handle = payload.get("ConsentHandle")

        if not clinic_id or not consent_handle:
            raise HTTPException(status_code=400,
                detail="Missing clinic_id or ConsentHandle")

        # Count transactions in payload
        total_txns = 0
        date_from  = None
        date_to    = None
        for fi in payload.get("FI", []):
            for account in fi.get("data", []):
                txns = account.get("Transactions", {}).get("Transaction", [])
                total_txns += len(txns)
                if txns:
                    date_from = account["Transactions"].get("StartDate")
                    date_to   = account["Transactions"].get("EndDate")

        # ── Step 1: Store raw payload as source of truth ──────────────
        async with db_pool.acquire() as conn:
            raw_id = await conn.fetchval(
                """
                insert into raw_aa_payloads
                    (clinic_id, consent_handle, raw_json,
                     transaction_count, date_from, date_to, received_at)
                values ($1, $2, $3, $4, $5, $6, now())
                returning id
                """,
                clinic_id,
                consent_handle,
                json.dumps(payload),    # entire payload stored as-is
                total_txns,
                date_from,
                date_to     
            )
            print(f"=== INSERT SUCCEEDED, raw_id: {raw_id} ===")

        print(f"Stored raw payload {raw_id} — {total_txns} transactions")

        # ── Step 2: Return 200 immediately ────────────────────────────
        # Don't make the AA operator wait for processing
        import asyncio
        asyncio.create_task(
            process_and_store_transactions(clinic_id, consent_handle, payload)
        )

        return {
            "status": "received",
            "clinic_id": clinic_id,
            "raw_payload_id": str(raw_id),
            "transaction_count": total_txns
        }

    except Exception as e:
        print(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_and_store_transactions(
    clinic_id: str,
    consent_handle: str,
    payload: dict
    
):
    
    """
    Runs in background after webhook returns 200.
    Extracts transactions and stores each row to transactions table.
    """

        
    transactions = []

    for fi in payload.get("FI", []):
        for account in fi.get("data", []):
            masked_acc = account.get("maskedAccNumber", "UNKNOWN")
            txns = account.get("Transactions", {}).get("Transaction", [])

            for txn in txns:
                category    = categorise(txn.get("narration", ""))
                gst_eligible = is_gst_eligible(category)

                transactions.append({
                    "txn_id":        txn.get("txnId"),
                    "clinic_id":     clinic_id,
                    "account_number":masked_acc,
                    "txn_date":      parse_date(txn.get("valueDate")),
                    "txn_type":      txn.get("type"),       # DEBIT or CREDIT
                    "mode":          txn.get("mode"),        # UPI, NEFT etc.
                    "amount":        float(txn.get("amount", 0)),
                    "balance_after": float(txn.get("currentBalance", 0)),
                    "narration":     txn.get("narration", ""),
                    "reference":     txn.get("reference", ""),
                    "category":      category,
                    "gst_eligible":  gst_eligible,
                    "source":        "aa_framework"
                })

    if not transactions:
        print("No transactions to store")
        return

    # ── Store all transactions — upsert to avoid duplicates ──────────
    async with db_pool.acquire() as conn:
        # Use executemany for bulk insert
        await conn.executemany(
            """
            insert into transactions
                (txn_id, clinic_id, account_number, txn_date,
                 txn_type, mode, amount, balance_after,
                 narration, reference, category, gst_eligible,
                 source, created_at)
            values
                ($1, $2, $3, $4, $5, $6, $7, $8,
                 $9, $10, $11, $12, $13, now())
            on conflict (txn_id) do nothing
            """,
            [
                (
                    t["txn_id"], t["clinic_id"], t["account_number"],
                    t["txn_date"], t["txn_type"], t["mode"],
                    t["amount"], t["balance_after"], t["narration"],
                    t["reference"], t["category"], t["gst_eligible"],
                    t["source"]
                )
                for t in transactions
            ]
        )

        # Mark raw payload as processed
        await conn.execute(
            """
            update raw_aa_payloads
            set is_processed = true, processed_at = now()
            where consent_handle = $1
            """,
            consent_handle
        )

    print(f"Stored {len(transactions)} transactions for clinic {clinic_id}")

    # Print summary by category
    from collections import defaultdict
    summary = defaultdict(lambda: {"count": 0, "debit": 0.0, "credit": 0.0})
    for t in transactions:
        cat = t["category"]
        summary[cat]["count"] += 1
        if t["txn_type"] == "DEBIT":
            summary[cat]["debit"] += t["amount"]
        else:
            summary[cat]["credit"] += t["amount"]

    print("\nCategory summary:")
    for cat, stats in sorted(summary.items()):
        print(f"  {cat}: {stats['count']} txns | "
              f"debit ₹{stats['debit']:,.0f} | "
              f"credit ₹{stats['credit']:,.0f}")


def categorise(narration: str) -> str:
    n = narration.lower()
    rules = {
        "pharma_supplies":    ["pharma", "medical", "medicine", "drug", "chemist"],
        "equipment":          ["equipment", "instruments", "surgical", "dental"],
        "consumables":        ["gloves", "disposables", "syringes", "sterimed"],
        "staff_salary":       ["salary", "wages", "staff", "imps"],
        "rent":               ["rent", "lease", "premises"],
        "utilities":          ["bescom", "bwssb", "electricity", "water",
                               "broadband", "airtel", "billpay"],
        "insurance_receipt":  ["star health", "niva bupa", "care health",
                               "hdfc ergo", "claim settlement"],
        "patient_collection": ["patient", "consult", "gpay", "upi"],
        "loan_emi":           ["emi", "loan", "creditcard"],
    }
    for category, keywords in rules.items():
        if any(kw in n for kw in keywords):
            return category
    return "uncategorised"


def is_gst_eligible(category: str) -> bool:
    return category in {"equipment", "consumables", "pharma_supplies"}


# Query endpoint — verify data landed correctly
@app.get("/transactions/{clinic_id}")
async def get_transactions(clinic_id: str, limit: int = 20):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select txn_id, txn_date, txn_type, mode,
                   amount, category, narration
            from transactions
            where clinic_id = $1
            order by txn_date desc
            limit $2
            """,
            clinic_id, limit
        )

        summary = await conn.fetch(
            """
            select
                category,
                count(*)                    as txn_count,
                sum(case when txn_type = 'DEBIT'
                    then amount else 0 end) as total_debit,
                sum(case when txn_type = 'CREDIT'
                    then amount else 0 end) as total_credit
            from transactions
            where clinic_id = $1
            group by category
            order by total_debit desc
            """,
            clinic_id
        )

    return {
        "clinic_id": clinic_id,
        "total_transactions": len(rows),
        "recent_transactions": [dict(r) for r in rows],
        "category_summary": [dict(r) for r in summary]
    }