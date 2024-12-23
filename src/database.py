from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
from src.models.user import Base
from src.config import Config
import logging

logger = logging.getLogger(__name__)

# 创建数据库引擎
engine = create_engine(Config.DATABASE_URL, echo=True)

# 创建会话工厂
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

def init_db():
    """初始化数据库"""
    Base.metadata.create_all(engine)

@contextmanager
def get_db_session():
    """获取数据库会话的上下文管理器"""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"数据库操作失败: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

def get_session():
    """获取数据库会话（不推荐直接使用，优先使用get_db_session上下文管理器）"""
    return Session() 