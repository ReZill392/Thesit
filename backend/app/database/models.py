from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey, DateTime, func, Text
from app.database.database import Base
from sqlalchemy.orm import relationship

class FacebookPage(Base):
    __tablename__ = "facebook_pages"

    ID = Column(Integer, primary_key=True, index=True)
    page_id = Column(String(50), unique=True, nullable=False)
    page_name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 🔁 Relationship กลับไปยัง CustomMessage
    messages = relationship("CustomMessage", back_populates="page", cascade="all, delete-orphan")

class CustomMessage(Base):
    __tablename__ = "fb_custom_messages"

    id = Column(Integer, primary_key=True, index=True)
    page_id = Column(String, ForeignKey("facebook_pages.page_id", ondelete="CASCADE"), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    # 🔁 Relationship ไปยัง FacebookPage
    page = relationship("FacebookPage", back_populates="messages")