from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from src.models.user import Base
from src.config import Config

# 创建数据库引擎
engine = create_engine(Config.DATABASE_URL, echo=True)

# 创建会话工厂
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

def init_db():
    """初始化数据库"""
    Base.metadata.create_all(engine)

def get_session():
    """获取数据库会话"""
    return Session() 