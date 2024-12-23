from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.models.user import User
from sqlalchemy.orm import Session
from src.services.blinko_service import BlinkoService
from src.database import get_db_session
import json
import re
import logging

logger = logging.getLogger(__name__)

# 定义会话状态
(
    CHOOSING_ACTION,
    SETTING_BLINKO_TOKEN,
    SETTING_BLINKO_URL,
    SETTING_JINA_KEY,
    SETTING_AI_KEY,
    SETTING_AI_URL,
    SETTING_AI_MODEL,
    SETTING_TAG_PROMPT,
    SETTING_SUMMARY_PROMPT,
    SWITCHING_USER,
) = range(10)

class CommandHandler:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def _validate_url(self, url: str) -> bool:
        """验证URL格式"""
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return bool(url_pattern.match(url))

    def _validate_token(self, token: str) -> bool:
        """验证Token格式"""
        # 这里根据实际的token格式要求进行验证
        return bool(token and len(token) >= 32)

    async def _update_user_settings(self, user_id: str, key: str, value: str) -> tuple[bool, str]:
        """更新用户设置并返回结果"""
        try:
            with get_db_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    return False, "用户未找到"
                
                # 验证输入
                if key in ['blinko_url', 'ai_config.api_endpoint']:
                    if not self._validate_url(value):
                        return False, "无效的URL格式"
                elif key in ['blinko_token', 'ai_config.api_key']:
                    if not self._validate_token(value):
                        return False, "无效的Token格式"
                
                # 更新设置
                user.update_settings(key, value)
                return True, f"✅ {key}已更新"
        except Exception as e:
            logger.error(f"更新设置失败: {str(e)}")
            return False, f"更新失败: {str(e)}"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        user_id = str(update.effective_user.id)
        
        with get_db_session() as session:
            user = session.query(User).filter_by(
                telegram_id=user_id
            ).first()

            if not user:
                user = User(
                    telegram_id=user_id,
                    username=update.effective_user.username
                )
                session.add(user)

        keyboard = [
            [InlineKeyboardButton("⚙️ 参数配置", callback_data='config')],
            [InlineKeyboardButton("👤 AI配置", callback_data='ai_config')],
            [InlineKeyboardButton("✍️ 提示词设置", callback_data='prompt_config')],
            [InlineKeyboardButton("✅ 完成配置", callback_data='finish')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = (
            "欢迎使用Blinko机器人！\n"
            "请选择以下操作：\n"
            "1. ⚙️ 参数配置：设置Blinko API和其他参数\n"
            "2. 🤖 AI配置：设置OpenAI参数\n"
            "3. ✍️ 提示词设置：自定义AI提示词\n"
            "4. ✅ 完成配置：确认并开始使用"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup
            )
        elif update.message:
            await update.message.reply_text(
                text=message_text,
                reply_markup=reply_markup
            )

        return CHOOSING_ACTION

    async def handle_setting_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理用户输入的配置值"""
        text = update.message.text
        current_state = context.user_data.get('current_state')

        # 根据当前状态处理不同的配置项
        state_handlers = {
            SETTING_BLINKO_TOKEN: ('blinko_token', "Blinko API Token"),
            SETTING_BLINKO_URL: ('blinko_url', "服务器URL"),
            SETTING_JINA_KEY: ('jina_key', "Jina Reader API Key"),
            SETTING_AI_KEY: ('ai_config.api_key', "OpenAI API Key"),
            SETTING_AI_URL: ('ai_config.api_endpoint', "OpenAI API URL"),
            SETTING_AI_MODEL: ('ai_config.model', "OpenAI模型名称"),
            SETTING_TAG_PROMPT: ('prompts.tag_prompt', "标签提示词"),
            SETTING_SUMMARY_PROMPT: ('prompts.summary_prompt', "总结提示词"),
        }

        if current_state in state_handlers:
            key, name = state_handlers[current_state]
            success, message = await self._update_user_settings(
                str(update.effective_user.id),
                key,
                text
            )
            
            await update.message.reply_text(message)
            if success:
                return await self.start(update, context)
            return current_state

        await update.message.reply_text("❌ 未知的配置项")
        return await self.start(update, context)

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /settings 命令"""
        with get_db_session() as session:
            user = session.query(User).filter_by(
                telegram_id=str(update.effective_user.id)
            ).first()

            if not user:
                await update.message.reply_text("请先使用 /start 命令初始化您的账户")
                return

            # 隐藏敏感信息
            settings_display = user.settings.copy()
            if settings_display.get('blinko_token'):
                settings_display['blinko_token'] = '***' + settings_display['blinko_token'][-4:]
            if settings_display.get('ai_config', {}).get('api_key'):
                settings_display['ai_config']['api_key'] = '***' + settings_display['ai_config']['api_key'][-4:]

            settings_text = json.dumps(settings_display, indent=2, ensure_ascii=False)
            await update.message.reply_text(
                f"当前配置：\n{settings_text}\n\n"
                f"使用 /start 重新配置"
            ) 

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮点击"""
        query = update.callback_query
        await query.answer()

        if query.data == 'config':
            keyboard = [
                [InlineKeyboardButton("🔑 设置Blinko Token", callback_data='set_token')],
                [InlineKeyboardButton("🌐 设置服务器URL", callback_data='set_url')],
                [InlineKeyboardButton("📝 设置Jina Key", callback_data='set_jina')],
                [InlineKeyboardButton("⬅️ 返回", callback_data='back')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="请选择要配置的参数：",
                reply_markup=reply_markup
            )
            return CHOOSING_ACTION

        elif query.data == 'ai_config':
            keyboard = [
                [InlineKeyboardButton("🔑 设置API Key", callback_data='set_ai_key')],
                [InlineKeyboardButton("🌐 设置API URL", callback_data='set_ai_url')],
                [InlineKeyboardButton("🤖 设置模型名称", callback_data='set_ai_model')],
                [InlineKeyboardButton("🔄 从Blinko获取配置", callback_data='get_blinko_ai_config')],
                [InlineKeyboardButton("⬅️ 返回", callback_data='back')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="请选择要配置的AI参数：",
                reply_markup=reply_markup
            )
            return CHOOSING_ACTION

        elif query.data == 'prompt_config':
            keyboard = [
                [InlineKeyboardButton("🏷️ 设置标签提示词", callback_data='set_tag_prompt')],
                [InlineKeyboardButton("📝 设置总结提示词", callback_data='set_summary_prompt')],
                [InlineKeyboardButton("⬅️ 返回", callback_data='back')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="请选择要配置的提示词：",
                reply_markup=reply_markup
            )
            return CHOOSING_ACTION

        elif query.data == 'set_token':
            await query.edit_message_text(
                text="请输入您的Blinko API Token："
            )
            context.user_data['current_state'] = SETTING_BLINKO_TOKEN
            return SETTING_BLINKO_TOKEN

        elif query.data == 'set_url':
            await query.edit_message_text(
                text="请输入Blinko服务器URL："
            )
            context.user_data['current_state'] = SETTING_BLINKO_URL
            return SETTING_BLINKO_URL

        elif query.data == 'set_jina':
            await query.edit_message_text(
                text="请输入Jina Reader API Key："
            )
            context.user_data['current_state'] = SETTING_JINA_KEY
            return SETTING_JINA_KEY

        elif query.data == 'set_ai_key':
            await query.edit_message_text(
                text="请输入OpenAI API Key："
            )
            context.user_data['current_state'] = SETTING_AI_KEY
            return SETTING_AI_KEY

        elif query.data == 'set_ai_url':
            await query.edit_message_text(
                text="请输入OpenAI API URL："
            )
            context.user_data['current_state'] = SETTING_AI_URL
            return SETTING_AI_URL

        elif query.data == 'set_ai_model':
            await query.edit_message_text(
                text="请输入OpenAI模型名称："
            )
            context.user_data['current_state'] = SETTING_AI_MODEL
            return SETTING_AI_MODEL

        elif query.data == 'set_tag_prompt':
            await query.edit_message_text(
                text="请输入标签生成的提示词模板（使用{content}作为内容占位符）："
            )
            context.user_data['current_state'] = SETTING_TAG_PROMPT
            return SETTING_TAG_PROMPT

        elif query.data == 'set_summary_prompt':
            await query.edit_message_text(
                text="请输入内容总结的提示词模板（使用{content}作为内容占位符）："
            )
            context.user_data['current_state'] = SETTING_SUMMARY_PROMPT
            return SETTING_SUMMARY_PROMPT

        elif query.data == 'switch_user':
            await query.edit_message_text(
                text="请输入新的Blinko API Token："
            )
            context.user_data['current_state'] = SWITCHING_USER
            return SWITCHING_USER

        elif query.data == 'back':
            return await self.start(update, context)

        elif query.data == 'finish':
            with get_db_session() as session:
                user = session.query(User).filter_by(
                    telegram_id=str(update.effective_user.id)
                ).first()
                
                if not user.is_blinko_configured():
                    await query.edit_message_text(
                        text="⚠️ 请先完成Blinko配置：\n"
                             "1. Blinko Token\n"
                             "2. Blinko URL"
                    )
                    return await self.start(update, context)
                
                # 如果已配置Blinko，尝试获取AI配置
                if not user.is_ai_configured():
                    try:
                        # 创建临时BlinkoService实例
                        blinko_config = {
                            "blinko_url": user.settings.get("blinko_url"),
                            "blinko_token": user.settings.get("blinko_token")
                        }
                        blinko_service = BlinkoService(blinko_config)
                        
                        # 获取AI配置
                        result = await blinko_service._make_request("GET", "/api/v1/config/list")
                        await blinko_service.close()
                        
                        if "error" not in result:
                            # 更新配置
                            settings = user.settings.copy()
                            if "ai_config" not in settings:
                                settings["ai_config"] = {}
                            
                            settings["ai_config"].update({
                                "api_key": result.get("api_key"),
                                "api_endpoint": result.get("api_endpoint"),
                                "model": result.get("model")
                            })
                            
                            user._settings = settings
                            logger.info(f"已自动从Blinko获取AI配置: {settings['ai_config']}")
                    except Exception as e:
                        logger.warning(f"自动获取AI配置失败: {str(e)}")
                
                user.is_active = True
                
            await query.edit_message_text(
                text="✅ 配置完成！\n"
                     "现在您可以：\n"
                     "1. 直接发送文字或图片，我会帮您保存到Blinko\n"
                     "2. 使用 /settings 查看当前配置\n"
                     "3. 随时使用 /start 重新配置"
            )
            return ConversationHandler.END

        elif query.data == 'get_blinko_ai_config':
            with get_db_session() as session:
                user = session.query(User).filter_by(
                    telegram_id=str(update.effective_user.id)
                ).first()
                
                if not user.is_blinko_configured():
                    await query.edit_message_text(
                        text="⚠️ 请先配置Blinko Token和URL"
                    )
                    return await self.start(update, context)
                
                try:
                    # 创建临时BlinkoService实例
                    blinko_config = {
                        "blinko_url": user.settings.get("blinko_url"),
                        "blinko_token": user.settings.get("blinko_token")
                    }
                    blinko_service = BlinkoService(blinko_config)
                    
                    # 获取AI配置
                    result = await blinko_service._make_request("GET", "/api/v1/config/list")
                    await blinko_service.close()
                    
                    if "error" in result:
                        raise Exception(result["error"])
                    
                    # 更新用户配置
                    settings = user.settings.copy()
                    if "ai_config" not in settings:
                        settings["ai_config"] = {}
                    
                    # 更新配置
                    settings["ai_config"].update({
                        "api_key": result.get("api_key"),
                        "api_endpoint": result.get("api_endpoint"),
                        "model": result.get("model")
                    })
                    
                    user._settings = settings
                    
                    await query.edit_message_text(
                        text="✅ 已从Blinko获取并更新AI配置！"
                    )
                    return await self.start(update, context)
                    
                except Exception as e:
                    await query.edit_message_text(
                        text=f"❌ 获取AI配置失败: {str(e)}\n"
                             f"请检查Blinko配置是否正确。"
                    )
                    return await self.start(update, context) 