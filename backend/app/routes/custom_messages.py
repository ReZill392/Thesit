from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.models import CustomMessage
from app.database.database import get_db
from pydantic import BaseModel

router = APIRouter()

class MessageCreate(BaseModel):
    page_id: str
    message: str

@router.post("/custom_message")
def create_custom_message(data: MessageCreate, db: Session = Depends(get_db)):
    msg = CustomMessage(page_id=data.page_id, message=data.message)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "message": msg.message}

@router.get("/custom_messages/{page_id}")
def get_custom_messages(page_id: str, db: Session = Depends(get_db)):
    return db.query(CustomMessage).filter(CustomMessage.page_id == page_id).all()

@router.delete("/custom_message/{id}")
def delete_custom_message(id: int, db: Session = Depends(get_db)):
    msg = db.query(CustomMessage).get(id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
    return {"status": "deleted"}
