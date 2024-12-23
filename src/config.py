import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Config:
    """配置类"""
    
    # Bot配置
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # Blinko API配置
    BLINKO_API_URL = os.getenv("BLINKO_API_URL")
    BLINKO_API_KEY = os.getenv("BLINKO_API_KEY")
    
    # 数据库配置
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_data.db")
    
    # 代理配置
    PROXY_URL = os.getenv("PROXY_URL")  # 例如: socks5://127.0.0.1:7890
    
    # OpenAI配置
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    
    @classmethod
    def validate(cls):
        """验证必要的配置是否存在"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("未设置TELEGRAM_BOT_TOKEN环境变量")