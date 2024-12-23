from sqlalchemy import Column, String, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    telegram_id = Column(String, primary_key=True)
    username = Column(String)
    _settings = Column('settings', JSON, default=dict)
    is_active = Column(Boolean, default=False)

    def __init__(self, telegram_id: str, username: str = None):
        self.telegram_id = telegram_id
        self.username = username
        self._settings = {
            'blinko_token': None,
            'blinko_url': None,
            'jina_key': None,
            'ai_config': {
                'api_key': None,
                'api_endpoint': 'https://api.openai.com/v1',
                'model': 'gpt-3.5-turbo'
            },
            'prompts': {
                'tag_prompt': None,
                'summary_prompt': None
            }
        }

    @property
    def settings(self):
        return self._settings

    def is_configured(self) -> bool:
        """检查是否已完成基本配置"""
        return bool(
            self._settings.get('blinko_token') and
            self._settings.get('blinko_url')
        )

    def get_ai_config(self) -> dict:
        """获取AI配置"""
        ai_config = self._settings.get('ai_config', {})
        
        # 如果没有配置AI，尝试从Blinko配置中获取
        if not ai_config.get('api_key'):
            ai_config['api_key'] = self._settings.get('blinko_token')
        
        # 确保有默认值
        if not ai_config.get('api_endpoint'):
            ai_config['api_endpoint'] = 'https://api.openai.com/v1'
        if not ai_config.get('model'):
            ai_config['model'] = 'gpt-3.5-turbo'
            
        return ai_config

    def get_prompts(self) -> dict:
        """获取提示词配置"""
        return self._settings.get('prompts', {})

    def __repr__(self):
        return f"<User {self.telegram_id}>"