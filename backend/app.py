from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI()

# ================================
# 🔧 Configuration
# ================================
FB_APP_ID = ""
FB_APP_SECRET = ""
REDIRECT_URI = "https://shop-sleeping-cause-cause.trycloudflare.com/facebook/callback"
OAUTH_LINK = f"https://www.facebook.com/v14.0/dialog/oauth?client_id={FB_APP_ID}&redirect_uri={REDIRECT_URI}&scope=pages_show_list,pages_read_engagement,pages_messaging&response_type=code"

PAGE_ACCESS_TOKEN = ""
VERIFY_TOKEN = ""
PAGE_ID = ""
FB_API_URL = "https://graph.facebook.com/v14.0"

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
    params = {"access_token": access_token or PAGE_ACCESS_TOKEN}
    response = requests.post(url, params=params, json=payload)
    return response.json()

def fb_get(endpoint: str, params: dict = {}, access_token: str = None):
    params["access_token"] = access_token or PAGE_ACCESS_TOKEN
    url = f"{FB_API_URL}/{endpoint}"
    response = requests.get(url, params=params)
    return response.json()

def send_message(recipient_id: str, message_text: str, access_token: str = None):
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    return fb_post("me/messages", payload, access_token)

def send_media(recipient_id: str, media_type: str, media_url: str, access_token: str = None):
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": media_type,
                "payload": {"url": media_url, "is_reusable": True}
            }
        }
    }
    return fb_post("me/messages", payload, access_token)

def send_quick_reply(recipient_id: str, access_token: str = None):
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {
            "text": "คุณอยากทำอะไรต่อ?",
            "quick_replies": [
                {"content_type": "text", "title": "ดูสินค้า", "payload": "VIEW_PRODUCTS"},
                {"content_type": "text", "title": "ติดต่อแอดมิน", "payload": "CONTACT_ADMIN"}
            ]
        }
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
# ✅ Utility: PSID extraction
# ================================

def get_conversations_with_participants(page_id, access_token: str = None):
    url = f"{FB_API_URL}/{page_id}/conversations"
    params = {"fields": "participants,updated_time"}
    return fb_get(url.replace(f"{FB_API_URL}/", ""), params, access_token)

def get_user_name(psid, access_token):
    url = f"https://graph.facebook.com/{psid}"
    params = {"fields": "name", "access_token": access_token}
    res = requests.get(url, params=params)
    if res.status_code == 200:
        return res.json().get("name", "")
    return ""

def extract_psids_with_conversation_id(conversations_data, access_token):
    result = []
    for convo in conversations_data.get("data", []):
        convo_id = convo.get("id")
        participants = convo.get("participants", {}).get("data", [])
        updated_time = convo.get("updated_time")
        # ดึงเวลาข้อความแรก
        created_time = get_first_message_time(convo_id, access_token)

        psids = []
        names = []
        for p in participants:
            if p.get("id") and p.get("id") != PAGE_ID:
                psids.append(p.get("id"))
                names.append(p.get("name", "ไม่ทราบชื่อ"))
        
        result.append({
            "conversation_id": convo_id,
            "psids": psids,
            "names": names,
            "updated_time": updated_time,
            "created_time": created_time  # เพิ่มตรงนี้
        })
    return result

# ================================
# 🌐 Extra Routes
# ================================

@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI application!"}

@app.get("/test/{user_id}")
async def test_send(user_id: str):
    result = send_message(user_id, "1234")
    return {"message": "ส่งข้อความ 1234 แล้ว", "result": result}

@app.get("/psids")
async def get_user_psids(page_id: str):
    access_token = page_tokens.get(page_id)
    conversations = get_conversations_with_participants(page_id, access_token)
    if conversations:
        data = extract_psids_with_conversation_id(conversations, access_token)
        return JSONResponse(content={"conversations": data})
    return JSONResponse(status_code=500, content={"error": "ไม่สามารถดึงข้อมูล conversation ได้"})

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
    # 👉 ดึง access token, ดึง page list และบันทึกไว้ตามเดิม
    token_url = "https://graph.facebook.com/v14.0/oauth/access_token"
    params = {
        "client_id": FB_APP_ID,
        "redirect_uri": REDIRECT_URI,
        "client_secret": FB_APP_SECRET,
        "code": code
    }
    res = requests.get(token_url, params=params)
    token_data = res.json()
    user_token = token_data.get("access_token")

    # ดึงเพจ
    pages_url = "https://graph.facebook.com/me/accounts"
    pages_res = requests.get(pages_url, params={"access_token": user_token})
    pages = pages_res.json()

    # 👉 เก็บ page access token ลง dictionary
    for page in pages.get("data", []):
        page_id = page["id"]
        access_token = page["access_token"]
        page_name = page.get("name", f"เพจ {page_id}")
        page_tokens[page_id] = access_token
        page_names[page_id] = page_name

    # 🔁 จากนั้น redirect กลับ React พร้อมส่งข้อมูลที่จำเป็น (ถ้าต้องการ)
    return RedirectResponse(url=f"http://localhost:3000/?page_id={page_id}")

@app.get("/pages")
async def get_connected_pages():
    return {"pages": [{"id": k, "name": page_names.get(k, f"เพจ {k}")} for k in page_tokens.keys()]}

# ================================
# 📩 ดึงข้อความใน conversation
# ================================

@app.get("/messages/{page_id}/{conversation_id}")
async def get_messages(page_id: str, conversation_id: str):
    access_token = page_tokens.get(page_id)
    if not access_token:
        return {"error": "Page token not found. Please connect via /connect first."}

    url = f'{FB_API_URL}/{conversation_id}/messages'
    params = {
        'access_token': access_token,
        'fields': 'message,from,to,created_time,attachments'
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": response.json()}
    
# ================================
# 📩 ส่งข้อความไปยังผู้ใช้
# ================================

class SendMessageRequest(BaseModel):
    message: str

@app.post("/send/{page_id}/{conversation_id}")
async def send_user_message(page_id: str, conversation_id: str, req: SendMessageRequest):
    access_token = page_tokens.get(page_id)
    if not access_token:
        return {"error": "Page token not found. Please connect via /connect first."}

    # ดึง participant ใน conversation
    url = f"{FB_API_URL}/{conversation_id}"
    params = {
        "fields": "participants",
        "access_token": access_token
    }
    res = requests.get(url, params=params)
    if res.status_code != 200:
        return {"error": "Cannot fetch conversation participants", "detail": res.json()}

    data = res.json()
    participants = data.get("participants", {}).get("data", [])
    
    # หา PSID ที่ไม่ใช่เพจ (page_id)
    user_psid = None
    for p in participants:
        if p.get("id") != page_id:
            user_psid = p.get("id")
            break

    if not user_psid:
        return {"error": "User PSID not found in conversation"}

    # ส่งข้อความไปยัง PSID ที่เจอ
    result = send_message(user_psid, req.message, access_token)
    return {"result": result}

def get_first_message_time(conversation_id, access_token):
    url = f"{FB_API_URL}/{conversation_id}/messages"
    params = {
        "access_token": access_token,
        "fields": "created_time",
        "limit": 1,
        "sort": "chronological"  # ดึงข้อความแรกสุด
    }
    res = requests.get(url, params=params)
    data = res.json()
    if "data" in data and data["data"]:
        return data["data"][0].get("created_time")
    return None
