from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from config import get_settings
from pywebpush import webpush, WebPushException

router = APIRouter(prefix="/push", tags=["push"])

class PushSubscription(BaseModel):
    endpoint: str
    keys: dict
    user_id: str = "demo-user-123"

@router.get("/public-key")
async def get_public_key():
    settings = get_settings()
    return {"public_key": settings.vapid_public_key}

@router.post("/subscribe")
async def subscribe(sub: PushSubscription):
    """Save a push subscription to Supabase."""
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        return {"status": "Database not configured"}
        
    try:
        await db.insert("push_subscriptions", {
            "user_id": sub.user_id,
            "endpoint": sub.endpoint,
            "p256dh_key": sub.keys.get("p256dh", ""),
            "auth_key": sub.keys.get("auth", "")
        })
        return {"status": "subscribed"}
    except Exception as e:
        # Ignore duplicate endpoints
        if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
            return {"status": "already_subscribed"}
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/notify-refill")
async def notify_refill(background_tasks: BackgroundTasks):
    """Trigger refill notifications via CRON."""
    settings = get_settings()
    if not settings.vapid_private_key:
        return {"status": "VAPID keys not configured"}

    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        return {"status": "Database not configured"}

    # Calculate refill dates grouped by user and NDC
    scan_history = await db.query("scan_history")
    
    # Simple grouping
    user_ndc_scans = {}
    for scan in scan_history:
        uid = scan.get("user_id", "demo-user-123")
        ndc = scan.get("ndc")
        if not ndc: continue
        key = (uid, ndc)
        if key not in user_ndc_scans:
            user_ndc_scans[key] = []
        user_ndc_scans[key].append(scan.get("created_at"))
        
    notifications_sent = 0
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    
    for (uid, ndc), dates in user_ndc_scans.items():
        if len(dates) < 3: continue
        # Parse dates and sort
        from dateutil.parser import parse
        parsed_dates = sorted([parse(d) for d in dates])
        
        intervals = []
        for i in range(1, len(parsed_dates)):
            diff = (parsed_dates[i] - parsed_dates[i-1]).days
            if diff > 0: intervals.append(diff)
            
        if not intervals: continue
        avg_interval = sum(intervals) / len(intervals)
        
        last_scan = parsed_dates[-1]
        next_refill = last_scan + datetime.timedelta(days=avg_interval)
        days_until = (next_refill - now).days
        
        # 3-day lookahead filter
        if 0 <= days_until <= 3:
            # Find sub
            subs = await db.query("push_subscriptions")
            user_subs = [s for s in subs if s.get("user_id") == uid]
            
            payload = f'{{"title": "Refill Reminder", "body": "Your prescription for {ndc} is running low based on your scan history. Tap to reorder.", "url": "/cabinet"}}'

            def send_push(sub, pld):
                try:
                    sub_info = {
                        "endpoint": sub["endpoint"],
                        "keys": {
                            "p256dh": sub["p256dh_key"],
                            "auth": sub["auth_key"]
                        }
                    }
                    webpush(
                        subscription_info=sub_info,
                        data=pld,
                        vapid_private_key=settings.vapid_private_key,
                        vapid_claims={"sub": settings.vapid_claims_email}
                    )
                except WebPushException as ex:
                    print("WebPush Error:", repr(ex))

            for sub in user_subs:
                background_tasks.add_task(send_push, sub, payload)
                notifications_sent += 1

    return {"status": "success", "notifications_queued": notifications_sent}
