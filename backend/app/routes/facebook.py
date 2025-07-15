from app.service.facebook_api import fb_get, send_message, send_image_binary, send_video_binary
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from datetime import datetime
import requests
from fastapi import APIRouter, Response, Request, Depends
from sqlalchemy.orm import Session
from app.database import crud, schemas, database, models
from app.database.database import get_db
from app import config  # ✅ ใช้ config แทน app.app
from pydantic import BaseModel
from app.config import image_dir,vid_dir
from app.service.message_scheduler import message_scheduler
from datetime import datetime, timedelta
from fastapi import Query
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
import pytz

router = APIRouter()

# ================================
# 🔧 เพิ่ม Memory Storage สำหรับ Page Tokens
# ================================
# เพิ่มตัวแปรเหล่านี้ใน facebook.py เพื่อให้ตรงกับ paste.txt
page_tokens = {}  # key = page_id, value = PAGE_ACCESS_TOKEN
page_names = {}   # key = page_id, value = page_name

class SendMessageRequest(BaseModel):
    message: str
    type: Optional[str] = "text"  # "text", "image", or "video"

# Models สำหรับ API
class CustomerGroupCreate(BaseModel):
    page_id: int
    type_name: str
    keywords: List[str] = []
    rule_description: str = ""
    examples: List[str] = []
    
class CustomerGroupUpdate(BaseModel):
    type_name: Optional[str] = None
    keywords: Optional[List[str]] = None
    rule_description: Optional[str] = None
    examples: Optional[List[str]] = None
    is_active: Optional[bool] = None

@router.get("/connect", response_class=HTMLResponse)
async def connect_facebook_page():
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>เชื่อมต่อ Facebook Page</title>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                margin-top: 100px;
                background-color: #f0f2f5;
            }}
            a.button {{
                background-color: #4267B2;
                color: white;
                padding: 14px 24px;
                text-decoration: none;
                font-size: 18px;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            a.button:hover {{
                background-color: #365899;
            }}
        </style>
    </head>
    <body>
        <h1>เชื่อมต่อ Facebook Page ของคุณ</h1>
        <p>คลิกปุ่มด้านล่างเพื่อเริ่มต้นการเชื่อมต่อ</p>
        <a href="{config.OAUTH_LINK}" class="button">🔗 เชื่อมต่อ Facebook</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.get("/facebook/callback")
def facebook_callback(code: str, db: Session = Depends(get_db)):
    print(f"🔗 Facebook callback received with code: {code[:20]}...")
    
    # ดึง access token
    token_url = "https://graph.facebook.com/v14.0/oauth/access_token"
    params = {
        "client_id": config.FB_APP_ID,
        "redirect_uri": config.REDIRECT_URI,
        "client_secret": config.FB_APP_SECRET,
        "code": code
    }

    print("🔍 กำลังขอ access token...")
    res = requests.get(token_url, params=params)
    token_data = res.json()

    if "error" in token_data:
        print(f"❌ Error getting access token: {token_data['error']}")
        return JSONResponse(status_code=400, content={"error": token_data['error']})

    user_token = token_data.get("access_token")
    print("✅ ได้รับ user access token แล้ว")

    # ดึงเพจ
    pages_url = "https://graph.facebook.com/me/accounts"
    print("🔍 กำลังดึงรายการเพจ...")
    pages_res = requests.get(pages_url, params={"access_token": user_token})
    pages = pages_res.json()

    if "error" in pages:
        print(f"❌ Error getting pages: {pages['error']}")
        return JSONResponse(status_code=400, content={"error": pages['error']})

    connected_pages = []
    for page in pages.get("data", []):
        page_id = page["id"]
        access_token = page["access_token"]
        page_name = page.get("name", f"เพจ {page_id}")
        message_scheduler.set_page_tokens(page_tokens)  # ✅ เก็บ page_tokens ใน message_scheduler
        
        # ✅ ส่ง tokens ให้ auto sync service ด้วย
        from app.service.auto_sync_service import auto_sync_service
        auto_sync_service.set_page_tokens(page_tokens)

        # ✅ เก็บใน local dictionary แทน config
        page_tokens[page_id] = access_token
        page_names[page_id] = page_name

        # เก็บลงฐานข้อมูลด้วย
        existing = crud.get_page_by_page_id(db, page_id)
        if not existing:
            new_page = schemas.FacebookPageCreate(page_id=page_id, page_name=page_name)
            crud.create_page(db, new_page)

        connected_pages.append({"id": page_id, "name": page_name})
        print(f"✅ เชื่อมต่อเพจสำเร็จ: {page_name} (ID: {page_id})")

    print(f"✅ เชื่อมต่อเพจทั้งหมด {len(connected_pages)} เพจ")

    if connected_pages:
        return RedirectResponse(url=f"http://localhost:3000/?page_id={connected_pages[0]['id']}")
    else:
        return RedirectResponse(url="http://localhost:3000/?error=no_pages")

@router.get("/pages")
async def get_connected_pages():
    # ✅ ใช้ local dictionary แทน config
    pages_list = [{"id": k, "name": page_names.get(k, f"เพจ {k}")} for k in page_tokens.keys()]
    print(f"📋 รายการเพจที่เชื่อมต่อ: {len(pages_list)} เพจ")
    return {"pages": pages_list}

@router.get("/psids")
async def get_user_psids(page_id: str):
    """ดึง PSID ทั้งหมดของผู้ใช้"""
    print(f"🔍 กำลังดึง PSID สำหรับ page_id: {page_id}")
    
    # ✅ ใช้ local dictionary แทน config
    access_token = page_tokens.get(page_id)
    if not access_token:
        print(f"❌ ไม่พบ access_token สำหรับ page_id: {page_id}")
        print(f"🔍 Available page_tokens: {list(page_tokens.keys())}")  # Debug line
        return JSONResponse(
            status_code=400, 
            content={"error": f"ไม่พบ access_token สำหรับ page_id: {page_id}. กรุณาเชื่อมต่อเพจก่อน"}
        )
    
    print(f"✅ พบ access_token สำหรับ page_id: {page_id}")
    
    conversations = get_conversations_with_participants(page_id, access_token)
    if conversations:
        data = extract_psids_with_conversation_id(conversations, access_token, page_id)
        print(f"✅ ส่งข้อมูล conversations จำนวน: {len(data)}")
        return JSONResponse(content={"conversations": data, "total": len(data)})
    else:
        print("❌ ไม่สามารถดึงข้อมูล conversations ได้")
        return JSONResponse(
            status_code=500, 
            content={"error": "ไม่สามารถดึงข้อมูล conversation ได้"}
        )

def get_conversations_with_participants(page_id, access_token: str = None):
    endpoint = f"{page_id}/conversations"
    params = {
        "fields": "participants,updated_time,id",
        "limit": 100
    }
    print(f"🔍 กำลังดึงข้อมูล conversations สำหรับ page_id: {page_id}")
    result = fb_get(endpoint, params, access_token)
    if "error" in result:
        print(f"❌ Error getting conversations: {result['error']}")
        return None
    print(f"✅ พบ conversations จำนวน: {len(result.get('data', []))}")
    return result

def get_user_info_from_psid(psid, access_token):
    methods = [
        {
            "endpoint": f"{psid}",
            "params": {"fields": "name,first_name,last_name,profile_pic"}
        },
        {
            "endpoint": f"me",
            "params": {
                "fields": f"{psid}.name,{psid}.first_name,{psid}.last_name",
                "ids": psid
            }
        }
    ]

    for method in methods:
        try:
            result = fb_get(method["endpoint"], method["params"], access_token)
            if "error" not in result:
                name = result.get("name") or result.get("first_name", "")
                if name:
                    return {
                        "name": name,
                        "first_name": result.get("first_name", ""),
                        "last_name": result.get("last_name", ""),
                        "profile_pic": result.get("profile_pic", "")
                    }
        except Exception as e:
            print(f"⚠️ Method failed: {e}")
            continue

    fallback_name = f"User...{psid[-8:]}" if len(psid) > 8 else f"User {psid}"
    return {
        "name": fallback_name,
        "first_name": "Unknown",
        "last_name": "",
        "profile_pic": ""
    }

def get_name_from_messages(conversation_id, access_token, page_id):
    try:
        endpoint = f"{conversation_id}/messages"
        params = {
            "fields": "from,message",
            "limit": 10
        }
        result = fb_get(endpoint, params, access_token)
        if "data" in result:
            for message in result["data"]:
                sender = message.get("from", {})
                sender_name = sender.get("name")
                sender_id = sender.get("id")
                if sender_id != page_id and sender_name:
                    return sender_name
        return None
    except Exception as e:
        print(f"❌ Error getting name from messages: {e}")
        return None

def get_first_message_time(conversation_id, access_token):
    endpoint = f"{conversation_id}/messages"
    params = {
        "fields": "created_time",
        "limit": 1,
        "order": "chronological"
    }
    result = fb_get(endpoint, params, access_token)
    if "data" in result and result["data"]:
        return result["data"][0].get("created_time")
    return None

def extract_psids_with_conversation_id(conversations_data, access_token, page_id):
    result = []
    if not conversations_data or "data" not in conversations_data:
        print("❌ ไม่มีข้อมูล conversations")
        return result

    for convo in conversations_data.get("data", []):
        convo_id = convo.get("id")
        updated_time = convo.get("updated_time")
        participants = convo.get("participants", {}).get("data", [])
        created_time = get_first_message_time(convo_id, access_token)
        user_psids = []
        user_names = []

        for participant in participants:
            participant_id = participant.get("id")
            if participant_id and participant_id != page_id:
                user_psids.append(participant_id)
                user_name = participant.get("name") or None

                if not user_name:
                    user_info = get_user_info_from_psid(participant_id, access_token)
                    user_name = user_info.get("name")

                if not user_name or user_name.startswith("User"):
                    message_name = get_name_from_messages(convo_id, access_token, page_id)
                    if message_name:
                        user_name = message_name

                if not user_name:
                    user_name = f"User...{participant_id[-8:]}"
                user_names.append(user_name)

        if user_psids:
            result.append({
                "conversation_id": convo_id,
                "psids": user_psids,
                "names": user_names,
                "updated_time": updated_time,
                "created_time": created_time
            })
    return result

# อัพเดท endpoint ส่งข้อความให้อัพเดท interaction ด้วย
@router.post("/send/{page_id}/{psid}")
async def send_user_message_by_psid(
    page_id: str,
    psid: str,
    req: SendMessageRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    print(f"📤 กำลังส่งข้อความไปยัง PSID: {psid}")
    print(f"📤 ข้อความ: {req.message}")

    access_token = page_tokens.get(page_id)
    if not access_token:
        return {"error": "Page token not found. Please connect via /connect first."}

    if not psid or len(psid) < 10:
        return {"error": "Invalid PSID"}

    # ส่งข้อความตามปกติ
    if req.type == "image":
        image_path = f"{image_dir}/{req.message}"
        result = send_image_binary(psid, image_path, access_token)
    elif req.type == "video":
        video_path = f"{vid_dir}/{req.message}"
        result = send_video_binary(psid, video_path, access_token)
    else:
        result = send_message(psid, req.message, access_token)

    if "error" in result:
        return {"error": result["error"], "details": result}
    else:
        return {"success": True, "result": result}
    
@router.get("/customers/{page_id}")
async def get_customers(
    page_id: str, 
    skip: int = 0, 
    limit: int = 100,
    search: str = None,
    db: Session = Depends(get_db)
):
    """ดึงรายชื่อลูกค้าทั้งหมดของเพจจาก database"""
    page = crud.get_page_by_page_id(db, page_id)
    if not page:
        return JSONResponse(
            status_code=400, 
            content={"error": f"ไม่พบเพจ {page_id} ในระบบ"}
        )
    
    if search:
        customers = crud.search_customers(db, page.ID, search)
    else:
        customers = crud.get_customers_by_page(db, page.ID, skip, limit)
    
    # แปลง format
    result = []
    for customer in customers:
        result.append({
            "id": customer.id,
            "psid": customer.customer_psid,
            "name": customer.name or f"User...{customer.customer_psid[-8:]}",
            "first_interaction": customer.first_interaction_at.isoformat() if customer.first_interaction_at else None,
            "last_interaction": customer.last_interaction_at.isoformat() if customer.last_interaction_at else None,
            "customer_type": customer.customer_type_custom.type_name if customer.customer_type_custom else None
        })
    
    return {
        "customers": result,
        "total": len(result),
        "page_id": page_id
    }

@router.get("/customer/{page_id}/{psid}")
async def get_customer_detail(
    page_id: str, 
    psid: str,
    db: Session = Depends(get_db)
):
    """ดึงข้อมูลลูกค้ารายคน"""
    page = crud.get_page_by_page_id(db, page_id)
    if not page:
        return JSONResponse(
            status_code=400, 
            content={"error": f"ไม่พบเพจ {page_id} ในระบบ"}
        )
    
    customer = crud.get_customer_by_psid(db, page.ID, psid)
    if not customer:
        return JSONResponse(
            status_code=404, 
            content={"error": "ไม่พบข้อมูลลูกค้า"}
        )
    
    return {
        "id": customer.id,
        "psid": customer.customer_psid,
        "name": customer.name,
        "first_interaction": customer.first_interaction_at.isoformat() if customer.first_interaction_at else None,
        "last_interaction": customer.last_interaction_at.isoformat() if customer.last_interaction_at else None,
        "customer_type_custom": customer.customer_type_custom.type_name if customer.customer_type_custom else None,
        "customer_type_knowledge": customer.customer_type_knowledge.type_name if customer.customer_type_knowledge else None,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat()
    }

@router.put("/customer/{page_id}/{psid}")
async def update_customer(
    page_id: str, 
    psid: str,
    customer_data: dict,
    db: Session = Depends(get_db)
):
    """อัพเดทข้อมูลลูกค้า"""
    page = crud.get_page_by_page_id(db, page_id)
    if not page:
        return JSONResponse(
            status_code=400, 
            content={"error": f"ไม่พบเพจ {page_id} ในระบบ"}
        )
    
    customer = crud.get_customer_by_psid(db, page.ID, psid)
    if not customer:
        return JSONResponse(
            status_code=404, 
            content={"error": "ไม่พบข้อมูลลูกค้า"}
        )
    
    # อัพเดทข้อมูล
    if "name" in customer_data:
        customer.name = customer_data["name"]
    if "customer_type_custom_id" in customer_data:
        customer.customer_type_custom_id = customer_data["customer_type_custom_id"]
    if "customer_type_knowledge_id" in customer_data:
        customer.customer_type_knowledge_id = customer_data["customer_type_knowledge_id"]
    
    customer.updated_at = datetime.now()
    db.commit()
    db.refresh(customer)
    
    return {"status": "success", "message": "อัพเดทข้อมูลสำเร็จ"}
# ================================
# 🧪 Debug Routes - เพิ่มเพื่อช่วย Debug
# ================================

@router.get("/debug/tokens")
async def debug_tokens():
    """ดู token ที่เก็บไว้"""
    return {
        "page_tokens_count": len(page_tokens),
        "page_tokens": {k: f"{v[:20]}..." for k, v in page_tokens.items()},
        "page_names": page_names
    }

@router.get("/debug/conversations/{page_id}")
async def debug_conversations(page_id: str):
    """Debug conversations data"""
    access_token = page_tokens.get(page_id)
    if not access_token:
        return {"error": "Page token not found"}
    
    # ดึงข้อมูลดิบ
    raw_conversations = get_conversations_with_participants(page_id, access_token)
    
    return {
        "page_id": page_id,
        "has_token": bool(access_token),
        "token_preview": f"{access_token[:20]}..." if access_token else None,
        "raw_data": raw_conversations
    }
        
# เพิ่ม endpoint สำหรับดึงข้อมูลจาก Facebook โดยตรง (ใช้เฉพาะเวลาต้องการ sync)
@router.get("/conversations-from-facebook/{page_id}")
async def get_conversations_from_facebook(page_id: str):
    """ดึง conversations จาก Facebook API โดยตรง (ใช้สำหรับ sync)"""
    print(f"🔍 กำลังดึงข้อมูลจาก Facebook สำหรับ page_id: {page_id}")
    
    # ตรวจสอบ access token
    access_token = page_tokens.get(page_id)
    if not access_token:
        return JSONResponse(
            status_code=400, 
            content={"error": f"ไม่พบ access_token สำหรับ page_id: {page_id}"}
        )
    
    try:
        return {
            "conversations": [], # ข้อมูลจาก Facebook
            "total": 0,
            "source": "facebook"
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.post("/schedule/activate")
async def activate_schedule(request: Request):
    """เปิดใช้งาน schedule"""
    data = await request.json()
    page_id = data.get('page_id')
    schedule = data.get('schedule')
    
    if not page_id or not schedule:
        return {"status": "error", "message": "Missing required data"}
    
    # อัพเดท page tokens ให้ scheduler ก่อนเพิ่ม schedule
    message_scheduler.set_page_tokens(page_tokens)
    
    # Reset sent tracking สำหรับ schedule นี้
    schedule_id = str(schedule['id'])
    message_scheduler.sent_tracking[schedule_id] = set()
    
    # ตรวจสอบและแก้ไขข้อมูล schedule
    if 'pageId' not in schedule and page_id:
        schedule['pageId'] = page_id
    
    # เพิ่ม schedule เข้าระบบ
    message_scheduler.add_schedule(page_id, schedule)
    
    # ถ้าเป็นแบบส่งทันที ให้ process ทันที
    if schedule.get('type') == 'immediate':
        await message_scheduler.process_schedule(page_id, schedule)
        return {"status": "success", "message": "Immediate schedule processed"}
    
    # สำหรับ scheduled และ user-inactive จะรอให้ scheduler ทำงานตามเวลา
    return {"status": "success", "message": "Schedule activated"}

# เพิ่มฟังก์ชันสำหรับดู active schedules:
@router.get("/active-schedules/{page_id}")
async def get_active_schedules(page_id: str):
    """ดู schedules ที่กำลังทำงาน"""
    schedules = message_scheduler.get_active_schedules_for_page(page_id)
    return {
        "page_id": page_id,
        "active_schedules": schedules,
        "count": len(schedules)
    }

@router.post("/schedule/deactivate")
async def deactivate_schedule(request: Request):
    """ปิดใช้งาน schedule"""
    data = await request.json()
    page_id = data.get('page_id')
    schedule_id = data.get('schedule_id')
    
    if not page_id or schedule_id is None:
        return {"status": "error", "message": "Missing required data"}
    
    message_scheduler.remove_schedule(page_id, schedule_id)
    
    return {"status": "success", "message": "Schedule deactivated"}

@router.get("/schedule/test-inactivity/{page_id}")
async def test_user_inactivity(page_id: str, minutes: int = 1):
    """ทดสอบระบบตรวจสอบ user ที่หายไป
    
    Parameters:
    - page_id: ID ของเพจ
    - minutes: จำนวนนาทีที่ต้องการทดสอบ (default = 1)
    """
    # Mock schedule for testing
    test_schedule = {
        "id": 999,
        "type": "user-inactive",
        "inactivityPeriod": str(minutes),
        "inactivityUnit": "minutes",
        "groups": [1],
        "messages": [
            {
                "type": "text",
                "content": f"สวัสดีค่ะ คุณหายไปมา {minutes} นาทีแล้วนะคะ 😊",
                "order": 0
            },
            {
                "type": "text", 
                "content": "มีโปรโมชั่นพิเศษสำหรับคุณ! กลับมาคุยกับเราสิคะ 💝",
                "order": 1
            }
        ]
    }
    
    # Reset tracking สำหรับการทดสอบ
    message_scheduler.sent_tracking["999"] = set()
    
    # อัพเดท page tokens ก่อนทดสอบ
    message_scheduler.set_page_tokens(page_tokens)
    
    # รันการตรวจสอบ
    await message_scheduler.check_user_inactivity(page_id, test_schedule)
    
    # ดึงผลลัพธ์
    sent_users = list(message_scheduler.sent_tracking.get("999", set()))
    
    return {
        "status": "success", 
        "message": f"Checked users inactive for {minutes} minutes",
        "sent_to_users": sent_users,
        "count": len(sent_users)
    }

# เพิ่ม endpoint สำหรับ reset tracking
@router.post("/schedule/reset-tracking/{schedule_id}")
async def reset_schedule_tracking(schedule_id: str):
    """Reset tracking data ของ schedule"""
    message_scheduler.sent_tracking[schedule_id] = set()
    return {"status": "success", "message": f"Reset tracking for schedule {schedule_id}"}

@router.get("/schedule/system-status")
async def get_system_status():
    """ดูสถานะของระบบ scheduler"""
    return {
        "is_running": message_scheduler.is_running,
        "active_pages": list(message_scheduler.active_schedules.keys()),
        "total_schedules": sum(len(schedules) for schedules in message_scheduler.active_schedules.values()),
        "schedules_by_page": {
            page_id: len(schedules) 
            for page_id, schedules in message_scheduler.active_schedules.items()
        },
        "tracking_info": {
            schedule_id: len(users) 
            for schedule_id, users in message_scheduler.sent_tracking.items()
        }
    }

# เพิ่ม endpoint นี้ในไฟล์ facebook.py
@router.post("/update-user-inactivity/{page_id}")
async def update_user_inactivity(page_id: str, request: Request):
    """อัพเดทข้อมูลระยะเวลาที่หายไปของ users จาก frontend"""
    try:
        data = await request.json()
        user_data = data.get('users', [])
        
        if not user_data:
            return {"status": "error", "message": "No user data provided"}
        
        # อัพเดทข้อมูลใน scheduler
        message_scheduler.update_user_inactivity_data(page_id, user_data)
        
        return {
            "status": "success", 
            "message": f"Updated inactivity data for {len(user_data)} users",
            "updated_count": len(user_data)
        }
        
    except Exception as e:
        logger.error(f"Error updating user inactivity data: {e}")
        return {"status": "error", "message": str(e)}

# ปรับปรุงฟังก์ชัน sync-customers ให้ดึงข้อมูลแบบละเอียด
@router.post("/sync-customers/{page_id}")
async def sync_facebook_customers_enhanced(
    page_id: str, 
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Sync ข้อมูลลูกค้าจาก Facebook มาเก็บใน database พร้อมข้อมูลเวลาที่ถูกต้อง"""
    print(f"🔄 เริ่ม sync ข้อมูลลูกค้าสำหรับ page_id: {page_id}")
    print(f"📅 ช่วงเวลา: period={period}, start={start_date}, end={end_date}")

    bangkok_tz = pytz.timezone("Asia/Bangkok")
    
    # ตรวจสอบว่ามี page ใน database หรือไม่
    page = crud.get_page_by_page_id(db, page_id)
    if not page:
        return JSONResponse(
            status_code=400, 
            content={"error": f"ไม่พบเพจ {page_id} ในระบบ กรุณาเชื่อมต่อเพจก่อน"}
        )
    
    # ดึง access token
    access_token = page_tokens.get(page_id)
    print(f"Received access_token: {access_token}")  # <--- debug line

    if not access_token:
        access_token = page_tokens.get(page_id)

    if not access_token:
        return JSONResponse(status_code=400, content={"error": f"ไม่พบ access_token สำหรับ page_id: {page_id}"})
    
    try:
        # คำนวณช่วงเวลาที่ต้องการดึงข้อมูล
        filter_start_date = None
        filter_end_date = None
        
        if period:
            now = datetime.now(bangkok_tz)
            if period == 'today':
                filter_start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == 'week':
                filter_start_date = now - timedelta(days=7)
            elif period == 'month':
                filter_start_date = now - timedelta(days=30)
            elif period == '3months':
                filter_start_date = now - timedelta(days=90)
            elif period == '6months':
                filter_start_date = now - timedelta(days=180)
            elif period == 'year':
                filter_start_date = now - timedelta(days=365)
            
            filter_end_date = now
        
        elif start_date and end_date:
            filter_start_date = bangkok_tz.localize(datetime.fromisoformat(start_date))
            filter_end_date = bangkok_tz.localize(datetime.fromisoformat(end_date + 'T23:59:59'))
        
        print(f"🕒 กรองข้อมูลตั้งแต่: {filter_start_date} ถึง {filter_end_date}")
        
        # ดึง conversations จาก Facebook พร้อมข้อความ
        endpoint = f"{page_id}/conversations"
        params = {
            "fields": "participants,updated_time,id,messages.limit(100){created_time,from,message}",
            "limit": 100
        }
        
        conversations = fb_get(endpoint, params, access_token)
        if "error" in conversations:
            logger.error(f"Error getting conversations: {conversations['error']}")
            return JSONResponse(
                status_code=500,
                content={"error": "ไม่สามารถดึง conversations ได้"}
            )
        
        sync_count = 0
        error_count = 0
        filtered_count = 0
        customers_to_sync = []
        
        # วนลูปผ่านแต่ละ conversation
        for convo in conversations.get("data", []):
            convo_id = convo.get("id")
            updated_time = convo.get("updated_time")
            participants = convo.get("participants", {}).get("data", [])
            messages = convo.get("messages", {}).get("data", [])
            
            # ตรวจสอบช่วงเวลาถ้ามีการกำหนด
            if filter_start_date and updated_time:
                try:
                    convo_time = datetime.fromisoformat(updated_time.replace('Z', '+00:00')).astimezone(bangkok_tz)
                    if convo_time < filter_start_date or convo_time > filter_end_date:
                        filtered_count += 1
                        continue
                except:
                    pass
            
            # หา user participants (ไม่ใช่ page)
            for participant in participants:
                participant_id = participant.get("id")
                if participant_id and participant_id != page_id:
                    try:
                        # หาข้อความแรกและล่าสุดของ user
                        # ตรวจสอบว่า messages มีข้อมูลหรือไม่
                        if not messages:
                            print(f"⚠️ ไม่มี messages ใน conversation {convo_id}")
                            continue

                        # ดึงข้อความทั้งหมดของฝั่ง user
                        user_messages = [
                            msg for msg in messages 
                            if msg.get("from", {}).get("id") == participant_id
                        ]
                                    
                        # fallback: ถ้าไม่มีข้อความฝั่ง user ให้ใช้ข้อความแรกใน conversation แทน
                        sorted_messages = sorted(messages, key=lambda x: x.get("created_time", ""))
                        first_msg_time = None
                        last_msg_time = None

                        if user_messages:
                            user_messages.sort(key=lambda x: x.get("created_time") or "")
                            first_msg_time = user_messages[0].get("created_time")
                            last_msg_time = user_messages[-1].get("created_time")
                        elif messages:
                            sorted_messages = sorted(messages, key=lambda x: x.get("created_time") or "")
                            first_msg_time = sorted_messages[0].get("created_time")
                            last_msg_time = sorted_messages[-1].get("created_time")
                        else:
                            first_msg_time = last_msg_time = updated_time

                        # แปลงเวลาถ้ามี
                        if first_msg_time:
                            try:
                                fixed_str = fix_isoformat(first_msg_time.replace("Z", "+00:00"))
                                first_interaction = datetime.fromisoformat(fixed_str).astimezone(bangkok_tz)
                            except Exception as e:
                                print(f"⚠️ ไม่สามารถแปลง first_msg_time: {first_msg_time} - {e}")
                                first_interaction = None

                        if last_msg_time:
                            try:
                                fixed_str = fix_isoformat(last_msg_time.replace("Z", "+00:00"))
                                last_interaction = datetime.fromisoformat(fixed_str).astimezone(bangkok_tz)
                            except Exception as e:
                                print(f"⚠️ ไม่สามารถแปลง last_msg_time: {last_msg_time} - {e}")
                                last_interaction = first_interaction

                        print(f"🕓 first_msg_time: {first_msg_time}, last_msg_time: {last_msg_time}")
                        print(f"➡️ first_interaction: {first_interaction}, last_interaction: {last_interaction}")
                        
                        # ถ้าไม่มีข้อความของ user ใช้เวลาของ conversation
                        if not first_interaction:
                            try:
                                first_interaction = datetime.fromisoformat(updated_time.replace('Z', '+00:00')).astimezone(bangkok_tz)
                            except Exception as e:
                                print(f"⚠️ ไม่สามารถแปลง updated_time: {updated_time} - {e}")
                                first_interaction = None

                        if not last_interaction:
                            last_interaction = first_interaction

                        # ดึงข้อมูล user
                        user_name = participant.get("name")
                        
                        if not user_name:
                            user_info = get_user_info_from_psid(participant_id, access_token)
                            user_name = user_info.get("name")
                        
                        if not user_name or user_name.startswith("User"):
                            message_name = get_name_from_messages(convo_id, access_token, page_id)
                            if message_name:
                                user_name = message_name
                        
                        if not user_name:
                            user_name = f"User...{participant_id[-8:]}"
                        
                        # เตรียมข้อมูลสำหรับ sync
                        customer_data = {
                            'customer_psid': participant_id,
                            'name': user_name,
                            'first_interaction_at': first_interaction,
                            'last_interaction_at': last_interaction,
                        }
                        
                        customers_to_sync.append(customer_data)
                        
                    except Exception as e:
                        print(f"❌ Error processing customer {participant_id}: {e}")
                        error_count += 1
                    
        installed_at = page.created_at
        if installed_at is None:
            installed_at = datetime.now(bangkok_tz)
        elif installed_at.tzinfo is None:
            installed_at = bangkok_tz.localize(installed_at)
        else:
            installed_at = installed_at.astimezone(bangkok_tz)


        for customer_data in customers_to_sync:
            first = customer_data.get("first_interaction_at")
    
            if isinstance(first, str):
                first = datetime.fromisoformat(first.replace("Z", "+00:00")).astimezone(bangkok_tz)
    
            if not first:
                first = datetime.now(bangkok_tz)
            elif first.tzinfo is None:
                first = bangkok_tz.localize(first)
            else:
                first = first.astimezone(bangkok_tz)
            # คำนวณ source_type
            source_type = "new" if first >= installed_at else "imported"

            customer_data["first_interaction_at"] = first
            customer_data["source_type"] = source_type
        
        # Bulk sync ข้อมูลลง database
        sync_results = {"created": 0, "updated": 0, "errors": 0}  # default

        if customers_to_sync:
            sync_results = crud.bulk_create_or_update_customers(db, page.ID, customers_to_sync)
            sync_count = sync_results["created"] + sync_results["updated"]
            error_count += sync_results["errors"]

            print(f"✅ Sync เสร็จสิ้น: สร้างใหม่ {sync_results['created']} คน, อัพเดท {sync_results['updated']} คน")
        else:
            sync_count = 0
        
        return {
            "status": "success",
            "synced": sync_count,
            "errors": error_count,
            "filtered": filtered_count,
            "message": f"Sync ข้อมูลลูกค้าสำเร็จ {sync_count} คน" + 
                      (f" (กรองออก {filtered_count} conversations)" if filtered_count > 0 else ""),
            "details": {
                "created": sync_results.get("created", 0),
                "updated": sync_results.get("updated", 0)
            }
        }
        
    except Exception as e:
        print(f"❌ Error during sync: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"เกิดข้อผิดพลาดในการ sync: {str(e)}"}
        )

def fix_isoformat(dt_str: str) -> str:
    if dt_str[-5] in ['+', '-'] and dt_str[-3] != ':':
        dt_str = dt_str[:-2] + ':' + dt_str[-2:]
    return dt_str

# เพิ่ม endpoint สำหรับดึงสถิติลูกค้า
@router.get("/customer-statistics/{page_id}")
async def get_customer_statistics(
    page_id: str,
    db: Session = Depends(get_db)
):
    """ดึงสถิติลูกค้าของเพจ"""
    page = crud.get_page_by_page_id(db, page_id)
    if not page:
        return JSONResponse(
            status_code=400, 
            content={"error": f"ไม่พบเพจ {page_id} ในระบบ"}
        )
    
    stats = crud.get_customer_statistics(db, page.ID)
    
    return {
        "page_id": page_id,
        "page_name": page.page_name,
        "statistics": stats,
        "generated_at": datetime.now().isoformat()
    }

# สร้างกลุ่มลูกค้าใหม่
@router.post("/customer-groups")
async def create_customer_group(
    group_data: CustomerGroupCreate,
    db: Session = Depends(get_db)
):
    """สร้างกลุ่มลูกค้าใหม่"""
    try:
        # ใช้ crud function ที่แก้ไขแล้ว
        new_group = crud.create_customer_type_custom(
            db, 
            page_id=group_data.page_id,
            type_data={
                'type_name': group_data.type_name,
                'keywords': group_data.keywords,  # ส่งเป็น list
                'rule_description': group_data.rule_description,
                'examples': group_data.examples, #  ส่งเป็น list
                'is_active': True
            }
        )
        
        return {
            "id": new_group.id,
            "page_id": new_group.page_id,
            "type_name": new_group.type_name,
            "keywords": new_group.keywords if isinstance(new_group.keywords, list) else [],
            "rule_description": new_group.rule_description,
            "examples": new_group.examples if isinstance(new_group.examples, list) else [],
            "created_at": new_group.created_at,
            "updated_at": new_group.updated_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# ดึงกลุ่มลูกค้าทั้งหมดของเพจ
@router.get("/customer-groups/{page_id}")
async def get_customer_groups(
    page_id: int,  # เปลี่ยนจาก str เป็น int
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """ดึงกลุ่มลูกค้าทั้งหมดของเพจ"""
    # page_id ที่รับมาเป็น integer ID จาก database แล้ว
    
    query = db.query(models.CustomerTypeCustom).filter(
        models.CustomerTypeCustom.page_id == page_id
    )
    
    if not include_inactive:
        query = query.filter(models.CustomerTypeCustom.is_active == True)
    
    groups = query.order_by(models.CustomerTypeCustom.created_at.desc()).all()
    
    result = []
    for group in groups:
        result.append({
            "id": group.id,
            "page_id": group.page_id,
            "type_name": group.type_name,
            "keywords": group.keywords or [],
            "examples": group.examples or [],
            "rule_description": group.rule_description,
            "is_active": group.is_active,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
            "customer_count": len(group.customers)
        })
    
    return result

# ดึงกลุ่มลูกค้าตาม ID
@router.get("/customer-group/{group_id}")
async def get_customer_group(
    group_id: int,
    db: Session = Depends(get_db)
):
    """ดึงข้อมูลกลุ่มลูกค้าตาม ID"""
    group = db.query(models.CustomerTypeCustom).filter(
        models.CustomerTypeCustom.id == group_id
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    return {
        "id": group.id,
        "page_id": group.page_id,
        "type_name": group.type_name,
        "keywords": group.keywords.split(",") if group.keywords else [],
        "examples": group.examples.split("\n") if group.examples else [],
        "rule_description": group.rule_description,
        "is_active": group.is_active,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
        "customer_count": len(group.customers)
    }

# อัพเดทกลุ่มลูกค้า
@router.put("/customer-groups/{group_id}")
async def update_customer_group(
    group_id: int,
    group_update: CustomerGroupUpdate,
    db: Session = Depends(get_db)
):
    """อัพเดทข้อมูลกลุ่มลูกค้า"""
    group = db.query(models.CustomerTypeCustom).filter(
        models.CustomerTypeCustom.id == group_id
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    try:
        update_data = {}
        if group_update.type_name is not None:
            update_data['type_name'] = group_update.type_name
        if group_update.keywords is not None:
            update_data['keywords'] = group_update.keywords
        if group_update.rule_description is not None:
            update_data['rule_description'] = group_update.rule_description
        if group_update.examples is not None:
            update_data['examples'] = group_update.examples
        if group_update.is_active is not None:
            update_data['is_active'] = group_update.is_active
            
        # ใช้ crud function ที่แก้ไขแล้ว
        updated_group = crud.update_customer_type_custom(db, group_id, update_data)
        
        return {
            "id": updated_group.id,
            "type_name": updated_group.type_name,
            "keywords": updated_group.keywords if isinstance(updated_group.keywords, list) else [],
            "rule_description": updated_group.rule_description,
            "examples": updated_group.examples if isinstance(updated_group.examples, list) else [],
            "updated_at": updated_group.updated_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# ลบกลุ่มลูกค้า
@router.delete("/customer-groups/{group_id}")
async def delete_customer_group(
    group_id: int,
    hard_delete: bool = False,
    db: Session = Depends(get_db)
):
    """ลบกลุ่มลูกค้า"""
    group = db.query(models.CustomerTypeCustom).filter(
        models.CustomerTypeCustom.id == group_id
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    try:
        if hard_delete:
            # Hard delete - ลบจริงจาก database
            db.delete(group)
        else:
            # Soft delete - เปลี่ยน is_active เป็น False
            group.is_active = False
            group.updated_at = datetime.now()
        
        db.commit()
        
        return {"status": "success", "message": "Group deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# ตรวจสอบและจัดกลุ่มลูกค้าอัตโนมัติ
@router.post("/auto-group-customer")
async def auto_group_customer(
    page_id: str,
    customer_psid: str,
    message_text: str,
    db: Session = Depends(get_db)
):
    """ตรวจสอบข้อความและจัดกลุ่มลูกค้าอัตโนมัติ"""
    page = crud.get_page_by_page_id(db, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # ดึงกลุ่มทั้งหมดของเพจ
    groups = db.query(models.CustomerTypeCustom).filter(
        models.CustomerTypeCustom.page_id == page.ID,
        models.CustomerTypeCustom.is_active == True
    ).all()
    
    # ตรวจสอบ keywords
    detected_group = None
    message_lower = message_text.lower()
    
    for group in groups:
        if group.keywords:
            keywords = [k.strip().lower() for k in group.keywords.split(",")]
            for keyword in keywords:
                if keyword and keyword in message_lower:
                    detected_group = group
                    break
        if detected_group:
            break
    
    if detected_group:
        # อัพเดทกลุ่มของลูกค้า
        customer = crud.get_customer_by_psid(db, page.ID, customer_psid)
        if customer:
            customer.customer_type_custom_id = detected_group.id
            customer.updated_at = datetime.now()
            db.commit()
            
            return {
                "status": "success",
                "group_detected": detected_group.type_name,
                "keywords_matched": True
            }
    
    return {
        "status": "no_match",
        "message": "No keywords matched"
    }