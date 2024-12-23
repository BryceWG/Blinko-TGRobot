from sqlalchemy import Column, String, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
import logging
import copy

logger = logging.getLogger(__name__)

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
                'api_endpoint': None,
                'model': None
            },
            'prompts': {
                'tag_prompt': None,
                'summary_prompt': None
            }
        }

    @property
    def settings(self):
        """获取设置"""
        # 确保设置有正确的结构
        if not isinstance(self._settings, dict):
            self._settings = {}
        
        # 确保ai_config存在
        if 'ai_config' not in self._settings:
            self._settings['ai_config'] = {
                'api_key': None,
                'api_endpoint': None,
                'model': None
            }
        
        # 确保prompts存在
        if 'prompts' not in self._settings:
            self._settings['prompts'] = {
                'tag_prompt': None,
                'summary_prompt': None
            }
        
        return self._settings

    def get_ai_config(self) -> dict:
        """获取AI配置"""
        settings = self.settings  # 使用property确保结构正确
        ai_config = settings.get('ai_config', {})
        
        # 如果没有配置AI，尝试从Blinko配置中获取
        if not ai_config.get('api_key'):
            ai_config['api_key'] = settings.get('blinko_token')
            
        return ai_config

    def update_settings(self, key: str, value: str) -> None:
        """更新设置
        
        Args:
            key: 设置键，支持点号分隔的嵌套键，如 'ai_config.api_key'
            value: 设置值
        """
        # 使用深拷贝确保不会修改原始数据
        settings = copy.deepcopy(self.settings)
        
        # 处理嵌套键
        if '.' in key:
            section, subkey = key.split('.')
            if section not in settings:
                settings[section] = {}
            settings[section][subkey] = value
            
            # 验证更新是否成功
            if settings[section][subkey] != value:
                logger.error(f"设置更新失败: {section}.{subkey} = {value}")
                raise ValueError(f"设置更新失败: {section}.{subkey}")
        else:
            settings[key] = value
            # 验证更新是否成功
            if settings[key] != value:
                logger.error(f"设置更新失败: {key} = {value}")
                raise ValueError(f"设置更新失败: {key}")
        
        # 更新设置
        self._settings = settings
        
        # 记录更新
        logger.info(f"用户 {self.telegram_id} 更新设置: {key} = {value}")

    def is_configured(self) -> bool:
        """检查是否已完成基本配置"""
        settings = self.settings
        ai_config = settings.get('ai_config', {})
        
        # 检查所有必需的配置项
        return bool(
            settings.get('blinko_token') and
            settings.get('blinko_url') and
            ai_config.get('api_key') and
            ai_config.get('api_endpoint') and
            ai_config.get('model')
        )

    def get_prompts(self) -> dict:
        """获取提示词配置"""
        return self.settings.get('prompts', {})

    def __repr__(self):
        return f"<User {self.telegram_id}>"