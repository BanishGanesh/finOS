# test_full_flow.py
# Run this to test the complete flow end to end

import httpx, asyncio, json

MOCK_AA_URL    = "http://localhost:8001"
YOUR_APP_URL   = "http://localhost:8000"
YOUR_WEBHOOK   = "http://localhost:8000/webhook/aa/data"

TEST_CLINICS = [
    {"id": "11111111-1111-1111-1111-111111111111", "name": "Dr. Sharma Dental Clinic"},
    {"id": "22222222-2222-2222-2222-222222222222", "name": "Bengaluru Skin Clinic"},
    {"id": "33333333-3333-3333-3333-333333333333", "name": "City Family Practice"},
]

async def test_full_flow():
    async with httpx.AsyncClient() as client:
        for clinic in TEST_CLINICS:
            print(f"\nTesting: {clinic['name']}")
            print("-" * 50)

            # Step 1 — Request consent
            consent_resp = await client.post(
                f"{MOCK_AA_URL}/v1/consent/request",
                json={
                    "clinic_id": clinic["id"],
                    "fiu_webhook_url": YOUR_WEBHOOK,
                    "months_of_data": 3
                }
            )
            consent = consent_resp.json()
            print(f"Consent requested: {consent['ConsentHandle']}")
            print(f"Status: {consent['status']}")

            # Step 2 — Wait for auto-approval and data delivery
            print("Waiting for auto-approval and data delivery...")
            await asyncio.sleep(4)

            # Step 3 — Check consent status
            status_resp = await client.get(
                f"{MOCK_AA_URL}/v1/consent/{consent['ConsentHandle']}/status"
            )
            print(f"Consent status: {status_resp.json()['ConsentStatus']['status']}")

            # Step 4 — Check your app received the data
            txn_resp = await client.get(
                f"{YOUR_APP_URL}/transactions/{clinic['id']}"
            )
            result = txn_resp.json()
            print(f"Transactions received: {result.get('total', 0)}")
            print("By category:")
            for cat, stats in result.get("by_category", {}).items():
                print(f"  {cat}: {stats['count']} txns, "
                      f"debit Rs.{stats['total_debit']:,.0f}, "
                      f"credit Rs.{stats['total_credit']:,.0f}")

asyncio.run(test_full_flow())