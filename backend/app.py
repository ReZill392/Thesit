from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from dotenv import load_dotenv
import os

app = FastAPI()
load_dotenv()

# ================================
# 🔧 Configuration
# ================================
FB_APP_ID = os.getenv("FB_APP_ID")
FB_APP_SECRET = os.getenv("FB_APP_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
FB_API_URL = os.getenv("FB_API_URL")

OAUTH_LINK = (
    f"https://www.facebook.com/v14.0/dialog/oauth?client_id={FB_APP_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&scope=pages_show_list,pages_read_engagement,pages_messaging&response_type=code"
)

page_tokens = {}  # key = page_id, value = PAGE_ACCESS_TOKEN
page_names = {}   # key = page_id, value = page_name

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================
# 🔧 Facebook API Helpers
# ================================

def fb_post(endpoint: str, payload: dict, access_token: str = None):
    url = f"{FB_API_URL}/{endpoint}"
    params = {"access_token": access_token}
    print(f"🔍 POST to: {url}")
    print(f"🔍 Payload: {payload}")
    response = requests.post(url, params=params, json=payload)
    print(f"🔍 Response Status: {response.status_code}")
    print(f"🔍 Response: {response.text}")
    return response.json()

def fb_get(endpoint: str, params: dict = {}, access_token: str = None):
    params["access_token"] = access_token
    url = f"{FB_API_URL}/{endpoint}"
    print(f"🔍 GET from: {url}")
    print(f"🔍 Params: {params}")
    response = requests.get(url, params=params)
    print(f"🔍 Response Status: {response.status_code}")
    print(f"🔍 Response: {response.text}")
    return response.json()

def send_message(recipient_id: str, message_text: str, access_token: str = None):
    payload = {
        "messaging_type": "MESSAGE_TAG",  # เปลี่ยนจาก RESPONSE เป็น MESSAGE_TAG
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "tag": "CONFIRMED_EVENT_UPDATE"  # เพิ่ม tag เพื่อให้ส่งได้นอกเวลา 24 ชม.
    }
    return fb_post("me/messages", payload, access_token)

def send_media(recipient_id: str, media_type: str, media_url: str, access_token: str = None):
    payload = {
        "messaging_type": "MESSAGE_TAG",
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": media_type,
                "payload": {"url": media_url, "is_reusable": True}
            }
        },
        "tag": "CONFIRMED_EVENT_UPDATE"
    }
    return fb_post("me/messages", payload, access_token)

def send_quick_reply(recipient_id: str, access_token: str = None):
    payload = {
        "messaging_type": "MESSAGE_TAG",
        "recipient": {"id": recipient_id},
        "message": {
            "text": "คุณอยากทำอะไรต่อ?",
            "quick_replies": [
                {"content_type": "text", "title": "ดูสินค้า", "payload": "VIEW_PRODUCTS"},
                {"content_type": "text", "title": "ติดต่อแอดมิน", "payload": "CONTACT_ADMIN"}
            ]
        },
        "tag": "CONFIRMED_EVENT_UPDATE"
    }
    return fb_post("me/messages", payload, access_token)

# ================================
# 📬 Webhook Routes
# ================================

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified with Facebook!")
        return PlainTextResponse(content=challenge, status_code=200)

    print("❌ Webhook verification failed")
    return PlainTextResponse(content="Verification failed", status_code=403)

@app.post("/webhook")
async def webhook_post(request: Request):
    body = await request.json()
    print("📩 ข้อมูล webhook:", body)

    for entry in body.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event["sender"]["id"]

            if "message" in messaging_event:
                msg = messaging_event["message"]

                if "text" in msg:
                    text = msg["text"]
                    print(f"💬 ข้อความ: {text}")
                    send_message(sender_id, f"คุณพิมพ์ว่า: {text}")

                elif "attachments" in msg:
                    for attachment in msg["attachments"]:
                        atype = attachment["type"]
                        url = attachment["payload"]["url"]
                        print(f"📎 ไฟล์แนบ: {atype}, URL: {url}")
                        send_message(sender_id, f"คุณส่ง {atype} มาให้เรา! 🙌")

    return PlainTextResponse("EVENT_RECEIVED", status_code=200)

# ================================
# ✅ Utility: PSID extraction - แก้ไขใหม่
# ================================

def get_conversations_with_participants(page_id, access_token: str = None):
    """ดึงข้อมูล conversations พร้อม participants"""
    endpoint = f"{page_id}/conversations"
    params = {
        "fields": "participants,updated_time,id",
        "limit": 100  # เพิ่ม limit
    }
    
    print(f"🔍 กำลังดึงข้อมูล conversations สำหรับ page_id: {page_id}")
    result = fb_get(endpoint, params, access_token)
    
    if "error" in result:
        print(f"❌ Error getting conversations: {result['error']}")
        return None
    
    print(f"✅ พบ conversations จำนวน: {len(result.get('data', []))}")
    return result

def get_user_info_from_psid(psid, access_token):
    """ดึงข้อมูลผู้ใช้จาก PSID - แก้ไขแล้ว"""
    try:
        # ลองหลายวิธีในการดึงข้อมูล
        methods = [
            # วิธีที่ 1: ดึงข้อมูลผ่าน PSID โดยตรง
            {
                "endpoint": f"{psid}",
                "params": {"fields": "name,first_name,last_name,profile_pic"}
            },
            # วิธีที่ 2: ใช้ page-scoped endpoint
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
                print(f"🔍 Trying method: {method['endpoint']}")
                print(f"🔍 Result: {result}")
                
                if "error" not in result:
                    # ตรวจสอบว่ามีข้อมูลชื่อหรือไม่
                    name = result.get("name") or result.get("first_name", "")
                    if name and name != "":
                        print(f"✅ พบชื่อ: {name}")
                        return {
                            "name": name,
                            "first_name": result.get("first_name", ""),
                            "last_name": result.get("last_name", ""),
                            "profile_pic": result.get("profile_pic", "")
                        }
                        
            except Exception as e:
                print(f"⚠️ Method failed: {e}")
                continue
        
        # ถ้าไม่สามารถดึงข้อมูลได้ ใช้ PSID ตัวสุดท้าย 8 หลัก
        fallback_name = f"User...{psid[-8:]}" if len(psid) > 8 else f"User {psid}"
        print(f"⚠️ ใช้ชื่อสำรอง: {fallback_name}")
        
        return {
            "name": fallback_name,
            "first_name": "Unknown",
            "last_name": "",
            "profile_pic": ""
        }
        
    except Exception as e:
        print(f"❌ Exception getting user info: {e}")
        fallback_name = f"User...{psid[-8:]}" if len(psid) > 8 else f"User {psid}"
        return {
            "name": fallback_name,
            "first_name": "Unknown", 
            "last_name": "",
            "profile_pic": ""
        }

def get_name_from_messages(conversation_id, access_token, page_id):
    """ดึงชื่อผู้ส่งจากข้อความล่าสุด"""
    try:
        endpoint = f"{conversation_id}/messages"
        params = {
            "fields": "from,message",
            "limit": 10  # ดึง 10 ข้อความล่าสุด
        }
        
        result = fb_get(endpoint, params, access_token)
        
        if "data" in result:
            for message in result["data"]:
                sender = message.get("from", {})
                sender_name = sender.get("name")
                sender_id = sender.get("id")
                
                # ถ้าผู้ส่งไม่ใช่เพจ และมีชื่อ
                if sender_id != page_id and sender_name:
                    print(f"✅ พบชื่อจากข้อความ: {sender_name}")
                    return sender_name
                    
        return None
        
    except Exception as e:
        print(f"❌ Error getting name from messages: {e}")
        return None

def extract_psids_with_conversation_id(conversations_data, access_token, page_id):
    """แยก PSID จากข้อมูล conversations พร้อมดึงข้อมูลผู้ใช้ - แก้ไขแล้ว"""
    result = []
    
    if not conversations_data or "data" not in conversations_data:
        print("❌ ไม่มีข้อมูล conversations")
        return result
    
    for convo in conversations_data.get("data", []):
        convo_id = convo.get("id")
        updated_time = convo.get("updated_time")
        participants = convo.get("participants", {}).get("data", [])
        
        print(f"🔍 Processing conversation: {convo_id}")
        
        # ดึงเวลาข้อความแรก
        created_time = get_first_message_time(convo_id, access_token)
        
        # หา PSID ที่ไม่ใช่ PAGE_ID
        user_psids = []
        user_names = []
        
        for participant in participants:
            participant_id = participant.get("id")
            if participant_id and participant_id != page_id:
                user_psids.append(participant_id)
                
                # ลองหลายวิธีในการดึงชื่อ
                user_name = None
                
                # วิธีที่ 1: ดึงจาก participant data โดยตรง
                if participant.get("name"):
                    user_name = participant.get("name")
                    print(f"✅ ได้ชื่อจาก participant: {user_name}")
                
                # วิธีที่ 2: ดึงจาก API
                if not user_name:
                    user_info = get_user_info_from_psid(participant_id, access_token)
                    user_name = user_info.get("name")
                    
                # วิธีที่ 3: ดึงจากข้อความในการสนทนา
                if not user_name or user_name.startswith("User"):
                    message_name = get_name_from_messages(convo_id, access_token)
                    if message_name:
                        user_name = message_name
                        print(f"✅ ใช้ชื่อจากข้อความ: {user_name}")
                
                # ถ้ายังไม่ได้ชื่อ ใช้ค่าเริ่มต้น
                if not user_name:
                    user_name = f"User...{participant_id[-8:]}"
                
                user_names.append(user_name)
                print(f"✅ Final name: {user_name} (PSID: {participant_id})")
        
        if user_psids:
            result.append({
                "conversation_id": convo_id,
                "psids": user_psids,
                "names": user_names,
                "updated_time": updated_time,
                "created_time": created_time
            })
    
    print(f"✅ รวมพบ conversations ที่มี PSID: {len(result)}")
    return result

# ================================
# 🌐 Extra Routes
# ================================

@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI application!"}

@app.get("/psids")
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

# ================================
# 🟦 Facebook OAuth & Page Connect
# ================================

@app.get("/connect", response_class=HTMLResponse)
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
        <a href="{OAUTH_LINK}" class="button">🔗 เชื่อมต่อ Facebook</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/facebook/callback")
def facebook_callback(code: str):
    """Callback จาก Facebook OAuth"""
    print(f"🔗 Facebook callback received with code: {code[:20]}...")
    
    # ดึง access token
    token_url = "https://graph.facebook.com/v14.0/oauth/access_token"
    params = {
        "client_id": FB_APP_ID,
        "redirect_uri": REDIRECT_URI,
        "client_secret": FB_APP_SECRET,
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

    # เก็บ page access token ลง dictionary
    connected_pages = []
    for page in pages.get("data", []):
        page_id = page["id"]
        access_token = page["access_token"]
        page_name = page.get("name", f"เพจ {page_id}")
        
        page_tokens[page_id] = access_token
        page_names[page_id] = page_name
        connected_pages.append({"id": page_id, "name": page_name})
        
        print(f"✅ เชื่อมต่อเพจสำเร็จ: {page_name} (ID: {page_id})")

    print(f"✅ เชื่อมต่อเพจทั้งหมด {len(connected_pages)} เพจ")
    
    # Redirect กลับ React
    if connected_pages:
        return RedirectResponse(url=f"http://localhost:3000/?page_id={connected_pages[0]['id']}")
    else:
        return RedirectResponse(url="http://localhost:3000/?error=no_pages")

@app.get("/pages")
async def get_connected_pages():
    """ดึงรายการเพจที่เชื่อมต่อแล้ว"""
    pages_list = [{"id": k, "name": page_names.get(k, f"เพจ {k}")} for k in page_tokens.keys()]
    print(f"📋 รายการเพจที่เชื่อมต่อ: {len(pages_list)} เพจ")
    return {"pages": pages_list}

# ================================
# 📩 ดึงข้อความใน conversation
# ================================

@app.get("/messages/{page_id}/{conversation_id}")
async def get_messages(page_id: str, conversation_id: str):
    """ดึงข้อความในการสนทนา"""
    access_token = page_tokens.get(page_id)
    if not access_token:
        return {"error": "Page token not found. Please connect via /connect first."}

    endpoint = f'{conversation_id}/messages'
    params = {
        'fields': 'message,from,to,created_time,attachments',
        'limit': 50  # จำกัดจำนวนข้อความ
    }

    result = fb_get(endpoint, params, access_token)
    
    if "error" in result:
        return {"error": result["error"]}
    
    return result
    
# ================================
# 📩 ส่งข้อความไปยังผู้ใช้ - แก้ไขใหม่
# ================================

class SendMessageRequest(BaseModel):
    message: str

@app.post("/send/{page_id}/{psid}")
async def send_user_message_by_psid(page_id: str, psid: str, req: SendMessageRequest):
    """ส่งข้อความไปยังผู้ใช้ผ่าน PSID"""
    print(f"📤 กำลังส่งข้อความไปยัง PSID: {psid}")
    print(f"📤 ข้อความ: {req.message}")
    
    access_token = page_tokens.get(page_id)
    if not access_token:
        print(f"❌ ไม่พบ access_token สำหรับ page_id: {page_id}")
        return {"error": "Page token not found. Please connect via /connect first."}

    # ตรวจสอบ PSID
    if not psid or len(psid) < 10:
        print(f"❌ PSID ไม่ถูกต้อง: {psid}")
        return {"error": "Invalid PSID"}
    
    # ส่งข้อความ
    result = send_message(psid, req.message, access_token)
    
    if "error" in result:
        print(f"❌ เกิดข้อผิดพลาดในการส่งข้อความ: {result['error']}")
        return {"error": result["error"], "details": result}
    else:
        print(f"✅ ส่งข้อความสำเร็จ")
        return {"success": True, "result": result}

def get_first_message_time(conversation_id, access_token):
    """ดึงเวลาของข้อความแรกในการสนทนา"""
    endpoint = f"{conversation_id}/messages"
    params = {
        "fields": "created_time",
        "limit": 1,
        "order": "chronological"  # เรียงตามเวลา
    }
    
    result = fb_get(endpoint, params, access_token)
    
    if "data" in result and result["data"]:
        return result["data"][0].get("created_time")
    return None

# ================================
# 🧪 Debug Routes
# ================================

@app.get("/debug/tokens")
async def debug_tokens():
    """ดู token ที่เก็บไว้"""
    return {
        "page_tokens": {k: f"{v[:20]}..." for k, v in page_tokens.items()},
        "page_names": page_names
    }

@app.get("/debug/conversations/{page_id}")
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