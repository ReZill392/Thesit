from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey, DateTime, func, Text
from database import Base
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class FacebookPage(Base):
    __tablename__ = "facebook_pages"

    ID = Column(Integer, primary_key=True, index=True)
    page_id = Column(String(50), unique=True, nullable=False)
    page_name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CustomMessage(Base):
    __tablename__ = "fb_custom_messages"

    id = Column(Integer, primary_key=True, index=True)
    page_id = Column(String, ForeignKey("facebook_pages.page_id", ondelete="CASCADE"))
    message = Column(String)
    created_at = Column(TIMESTAMP(timezone=True))