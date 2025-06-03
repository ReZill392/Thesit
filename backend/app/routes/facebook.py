from app.service.facebook_api import fb_get, send_message
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from datetime import datetime
import requests
from fastapi import APIRouter, Response, Request, Depends
from sqlalchemy.orm import Session
from app.database import crud, schemas, database, models
from app.database.database import get_db
from app import config  # ✅ ใช้ config แทน app.app
from app.config import page_tokens, page_names

router = APIRouter()

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

        # เก็บใน dictionary memory
        config.page_tokens[page_id] = access_token
        config.page_names[page_id] = page_name

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
    pages_list = [{"id": k, "name": config.page_names.get(k, f"เพจ {k}")} for k in config.page_tokens.keys()]
    print(f"📋 รายการเพจที่เชื่อมต่อ: {len(pages_list)} เพจ")
    return {"pages": pages_list}

@router.get("/messages/{page_id}/{conversation_id}")
async def get_messages(page_id: str, conversation_id: str):
    access_token = config.page_tokens.get(page_id)
    if not access_token:
        return {"error": "Page token not found. Please connect via /connect first."}

    endpoint = f'{conversation_id}/messages'
    params = {
        'fields': 'message,from,to,created_time,attachments',
        'limit': 50
    }

    result = fb_get(endpoint, params, access_token)

    if "error" in result:
        return {"error": result["error"]}

    return result
@router.get("/psids")
async def get_user_psids(page_id: str):
    """ดึง PSID ทั้งหมดของผู้ใช้"""
    print(f"🔍 กำลังดึง PSID สำหรับ page_id: {page_id}")
    
    access_token = page_tokens.get(page_id)
    if not access_token:
        print(f"❌ ไม่พบ access_token สำหรับ page_id: {page_id}")
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