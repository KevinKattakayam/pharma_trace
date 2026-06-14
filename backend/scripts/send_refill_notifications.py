import asyncio
import time
import os
from services.supabase import get_supabase
from pywebpush import webpush, WebPushException

async def process_refills():
    db = get_supabase()
    if not db.available:
        print("Database not available.")
        return

    print("Checking for upcoming refills...")
    
    # Query medicine cabinet for days_supply_remaining <= 3
    # This requires PostgREST filtering
    # For now, fetching all and filtering in python since it's a cron job
    try:
        medicines = await db.query("medicine_cabinet", limit=1000)
        if not medicines:
            print("No medicines found in cabinet.")
            return
            
        push_subs = await db.query("push_subscriptions", limit=1000)
        if not push_subs:
            print("No push subscriptions found.")
            return
            
        subs_by_user = {sub["user_id"]: sub for sub in push_subs}
        
        vapid_private = os.getenv("VAPID_PRIVATE_KEY")
        vapid_claims = {"sub": os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@pharmatrace.app")}
        
        if not vapid_private:
            print("VAPID_PRIVATE_KEY not set. Cannot send push notifications.")
            return

        for med in medicines:
            days_left = med.get("days_supply_remaining")
            user_id = med.get("user_id")
            
            if days_left is not None and days_left <= 3 and days_left >= 0:
                sub = subs_by_user.get(user_id)
                if sub:
                    print(f"Sending refill reminder to user {user_id} for {med['medicine_name']}")
                    try:
                        webpush(
                            subscription_info={
                                "endpoint": sub["endpoint"],
                                "keys": {
                                    "p256dh": sub["p256dh_key"],
                                    "auth": sub["auth_key"]
                                }
                            },
                            data=f"Refill Reminder: You have {days_left} days left of {med['medicine_name']}.",
                            vapid_private_key=vapid_private,
                            vapid_claims=vapid_claims
                        )
                    except WebPushException as ex:
                        print("Webpush failed:", repr(ex))
                        
    except Exception as e:
        print(f"Error processing refills: {e}")

if __name__ == "__main__":
    asyncio.run(process_refills())
