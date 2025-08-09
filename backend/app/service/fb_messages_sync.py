from typing import List, Dict, Any, Optional
from datetime import datetime
import pytz

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.service.facebook_api import fb_get
from app.routes.facebook.conversations import get_recent_conversations  # assume available
# if not available, import or paste equivalent

bangkok_tz = pytz.timezone("Asia/Bangkok")

# helper: parse FB time like '2025-08-05T12:23:45+0000' or '...Z'
def parse_fb_time_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        s2 = s.replace("Z", "+00:00")
        # handle +0000 -> +00:00
        if len(s2) >= 5 and (s2[-5] in ["+", "-"]) and (s2[-2] != ":"):
            s2 = s2[:-2] + ":" + s2[-2:]
        dt = datetime.fromisoformat(s2)
        # normalize to aware UTC
        if dt.tzinfo is None:
            import pytz
            dt = pytz.utc.localize(dt)
        return dt.astimezone(pytz.utc)
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").astimezone(pytz.utc)
        except Exception:
            return None

def to_bkk(dt_utc: Optional[datetime]) -> Optional[datetime]:
    if not dt_utc:
        return None
    if dt_utc.tzinfo is None:
        import pytz
        dt_utc = pytz.utc.localize(dt_utc)
    return dt_utc.astimezone(bangkok_tz)

def fetch_all_messages_for_conversation(convo_id: str, access_token: str) -> List[Dict[str, Any]]:
    """
    Fetch messages for a conversation with paging.
    Returns list of message dicts.
    """
    messages = []
    endpoint = f"{convo_id}/messages"
    params = {"fields": "created_time,from,message,attachments", "limit": 50}
    page = fb_get(endpoint, params, access_token)
    if not page or "error" in page:
        print("❌ Error fetching messages for convo", convo_id, page.get("error") if page else "no result")
        return messages

    while True:
        data = page.get("data", [])
        messages.extend(data)
        paging = page.get("paging", {}) or {}
        next_url = paging.get("next")
        if not next_url:
            break
        # assuming fb_get accepts full url for paging; if not, adjust to use cursor
        page = fb_get(next_url, {}, access_token)
        if not page or "error" in page:
            print("❌ Error paging messages:", page.get("error") if page else "no page")
            break
    return messages

def lookup_customer_id(db: Session, page_db_id: int, customer_psid: str) -> Optional[int]:
    """
    Return fb_customers.id matching page_id (DB PK) and customer_psid.
    Returns None if not found.
    """
    sql = text(
        "SELECT id FROM fb_customers WHERE page_id = :page_db_id AND customer_psid = :psid LIMIT 1"
    )
    r = db.execute(sql, {"page_db_id": page_db_id, "psid": customer_psid}).fetchone()
    return r[0] if r else None

def insert_customer_messages_from_conversations(
    db: Session,
    page_id_str: str,
    access_token: str,
    since_iso: str
) -> Dict[str, int]:
    """
    Main function:
    - get recent conversations
    - for each conversation fetch messages
    - lookup customer_id by (facebook_pages.ID, psid)
    - insert into customer_messages
    Returns counts
    """
    # 1) find page DB row (facebook_pages table) to get DB PK (column "ID")
    page_row = db.execute(text("SELECT \"ID\", page_id FROM facebook_pages WHERE page_id = :pid LIMIT 1"), {"pid": page_id_str}).fetchone()
    if not page_row:
        raise RuntimeError(f"page_id {page_id_str} not found in facebook_pages")
    page_db_id = page_row[0]

    # 2) get recent conversations (expects list)
    convos = get_recent_conversations(page_id_str, access_token, since_iso)
    if not convos:
        return {"inserted_messages": 0, "skipped_existing": 0, "conversations": 0}

    inserted_messages = 0
    skipped_existing = 0
    batch_values = []

    # we'll commit in batches to reduce transaction size
    BATCH_SIZE = 200

    for convo in convos:
        convo_id = convo.get("id")
        # fetch messages
        msgs = fetch_all_messages_for_conversation(convo_id, access_token)
        if not msgs:
            continue

        # process in chronological order
        msgs_sorted = sorted(msgs, key=lambda m: m.get("created_time") or "")

        for m in msgs_sorted:
            created_raw = m.get("created_time")
            created_dt_utc = parse_fb_time_to_dt(created_raw)
            if not created_dt_utc:
                continue
            created_bkk = to_bkk(created_dt_utc)

            sender = m.get("from") or {}
            sender_id = sender.get("id")
            sender_name = sender.get("name") or None

            # detect message type
            message_text = m.get("message")
            attachments = m.get("attachments")
            if message_text:
                message_type = "text"
            elif attachments:
                message_type = "attachment"
            else:
                message_type = "unknown"

            # lookup customer_id if message from a user (not page)
            customer_id = None
            if sender_id and sender_id != page_id_str:
                customer_id = lookup_customer_id(db, page_db_id, sender_id)

            # optional dedupe check: skip if same (conversation_id, created_at, sender_id) exists
            # This avoids duplicates when running sync repeatedly
            check_sql = text("""
                SELECT 1 FROM customer_messages
                WHERE conversation_id = :convo_id
                  AND sender_id = :sender_id
                  AND created_at = :created_at
                LIMIT 1
            """)
            exists = db.execute(check_sql, {
                "convo_id": convo_id,
                "sender_id": sender_id,
                "created_at": created_bkk
            }).fetchone()
            if exists:
                skipped_existing += 1
                continue

            # prepare insert params
            batch_values.append({
                "customer_id": customer_id,
                "conversation_id": convo_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "message_text": message_text,
                "message_type": message_type,
                "created_at": created_bkk
            })

            # flush batch
            if len(batch_values) >= BATCH_SIZE:
                insert_sql = text("""
                    INSERT INTO customer_messages
                    (customer_id, conversation_id, sender_id, sender_name, message_text, message_type, created_at)
                    VALUES
                    (:customer_id, :conversation_id, :sender_id, :sender_name, :message_text, :message_type, :created_at)
                """)
                db.execute(insert_sql, batch_values)
                db.commit()
                inserted_messages += len(batch_values)
                batch_values = []

    # insert remaining
    if batch_values:
        insert_sql = text("""
            INSERT INTO customer_messages
            (customer_id, conversation_id, sender_id, sender_name, message_text, message_type, created_at)
            VALUES
            (:customer_id, :conversation_id, :sender_id, :sender_name, :message_text, :message_type, :created_at)
        """)
        db.execute(insert_sql, batch_values)
        db.commit()
        inserted_messages += len(batch_values)

    return {
        "inserted_messages": inserted_messages,
        "skipped_existing": skipped_existing,
        "conversations": len(convos)
    }
