from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class UploadedFile(Base):
    __tablename__ = 'uploaded_files'
    id = Column(Integer, primary_key=True)
    unique_filename = Column(String(50), unique=True)
    original_filename = Column(String(200))
    file_path = Column(String(200))
    upload_time = Column(DateTime, default=datetime.utcnow)
    file_type = Column(String(50))

class Transcription(Base):
    __tablename__ = 'transcriptions'
    id = Column(Integer, primary_key=True)
    file_path = Column(String(200))
    results = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)