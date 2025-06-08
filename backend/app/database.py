from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# 获取当前目录和上级目录
app_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(app_dir)

# 创建数据库引擎
engine = create_engine(f'sqlite:///{os.path.join(backend_dir, "transcriptions.db")}', pool_pre_ping=True)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()