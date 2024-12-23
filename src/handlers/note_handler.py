# src/handlers/note_handler.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.models.session import UserSession, NoteState, MessageType, NoteContent
from src.services.ai_service import AIService
from src.services.blinko_service import BlinkoService
from src.models.user import User
import re
import logging

logger = logging.getLogger(__name__)

# 全局会话状态
GLOBAL_SESSION = UserSession()

class NoteHandler:
    def __init__(self, db_session):
        self.db_session = db_session
        self.ai_service = None
        self.blinko_service = None

    async def _init_services(self, user_id: str):
        """初始化服务"""
        user = self.db_session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            raise ValueError("用户未找到")

        # 初始化Blinko服务
        blinko_config = {
            "blinko_url": user.settings.get("blinko_url"),
            "blinko_token": user.settings.get("blinko_token")
        }
        self.blinko_service = BlinkoService(blinko_config)

        # 初始化AI服务
        ai_config = user.get_ai_config()
        ai_config["prompts"] = user.get_prompts()
        self.ai_service = AIService(ai_config)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理新消息"""
        try:
            # 初始化服务
            await self._init_services(str(update.effective_user.id))

            # 如果状态是INITIAL，重置会话状态
            if GLOBAL_SESSION.state == NoteState.INITIAL:
                GLOBAL_SESSION.clear()
                GLOBAL_SESSION.state = NoteState.COLLECTING

            # 处理消息
            message_type = self._detect_message_type(update.message)
            success = await self._process_message(GLOBAL_SESSION, message_type, update, context)
            
            # 显示操作按钮
            if success and GLOBAL_SESSION.state == NoteState.COLLECTING:
                await self._show_action_buttons(GLOBAL_SESSION, update, context)
                GLOBAL_SESSION.state = NoteState.AWAITING_ACTION
        except Exception as e:
            logger.error(f"处理消息时出错: {str(e)}", exc_info=True)
            await update.message.reply_text("处理消息时出错，请重试")
            GLOBAL_SESSION.clear()

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮回调"""
        query = update.callback_query
        
        if GLOBAL_SESSION.state == NoteState.INITIAL:
            await query.answer("请先发送一条消息")
            return

        try:
            # 初始化服务
            await self._init_services(str(update.effective_user.id))

            action = query.data
            
            if action == "continue":
                # 继续收集内容
                GLOBAL_SESSION.state = NoteState.COLLECTING
                await query.edit_message_text("请继续输入内容...")
            
            elif action == "save":
                # 保存笔记
                await self._save_note(GLOBAL_SESSION, update, context)
                GLOBAL_SESSION.clear()
            
            elif action == "summarize":
                # 生成总结
                GLOBAL_SESSION.state = NoteState.SUMMARIZING
                summary = await self.ai_service.summarize(GLOBAL_SESSION.contents)
                GLOBAL_SESSION.current_summary = summary
                
                # 显示总结和操作按钮
                buttons = [
                    [InlineKeyboardButton("💾 保存总结", callback_data="save_summary")],
                    [InlineKeyboardButton("🔄 重新总结", callback_data="summarize")],
                    [InlineKeyboardButton("↩️ 返回", callback_data="back")]
                ]
                await query.edit_message_text(
                    f"总结内容：\n\n{summary}",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "tags":
                # 获取AI标签建议
                GLOBAL_SESSION.state = NoteState.SELECTING_TAGS
                text_contents = [c.content for c in GLOBAL_SESSION.contents if c.type == MessageType.TEXT]
                
                # 从Blinko获取现有标签
                existing_tags = await self.blinko_service.get_tags()
                if "error" in existing_tags:
                    raise Exception(f"获取标签失败: {existing_tags['error']}")
                
                # 提取标签名列表
                existing_tag_names = [tag.get('name', '') for tag in existing_tags if isinstance(tag, dict)]
                
                # 获取AI标签建议
                tags_text = await self.ai_service.generate_tags(text_contents, existing_tag_names)
                
                # 解析标签和推荐理由
                tag_info = {}  # 用于存储标签和推荐理由
                for line in tags_text.split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split('-', 1)
                    if len(parts) == 2:
                        tag = parts[0].strip().strip('#').strip()
                        reason = parts[1].strip()
                        if tag:
                            tag_info[tag] = reason
                
                # 创建标签选择按钮
                message_text = "请选择标签：\n\n"
                buttons = []
                
                for tag, reason in tag_info.items():
                    is_selected = tag in GLOBAL_SESSION.selected_tags
                    is_existing = "[已有]" in reason
                    
                    # 添加标签说明到消息文本
                    message_text += f"{'✅ ' if is_selected else '☐ '}#{tag}"
                    if is_existing:
                        message_text += " [已有]"
                    message_text += f"\n💡 {reason}\n\n"
                    
                    # 创建选择按钮
                    buttons.append([InlineKeyboardButton(
                        f"{'✅' if is_selected else ''} #{tag}",
                        callback_data=f"tag_{tag}"
                    )])
                
                buttons.append([InlineKeyboardButton("💾 完成选择", callback_data="save_tags")])
                buttons.append([InlineKeyboardButton("↩️ 返回", callback_data="back")])
                
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action.startswith("tag_"):
                # 处理标签选择
                tag = action.replace("tag_", "")
                if tag in GLOBAL_SESSION.selected_tags:
                    GLOBAL_SESSION.selected_tags.remove(tag)
                else:
                    GLOBAL_SESSION.selected_tags.append(tag)
                # 刷新标签选择界面
                await self.handle_callback(update, context)
            
            elif action == "save_tags":
                # 保存选择的标签
                tags_text = " ".join([f"#{tag}" for tag in GLOBAL_SESSION.selected_tags])
                if GLOBAL_SESSION.contents:
                    last_content = GLOBAL_SESSION.contents[-1]
                    if last_content.type == MessageType.TEXT:
                        last_content.content += f"\n{tags_text}"
                    else:
                        GLOBAL_SESSION.add_content(MessageType.TEXT, tags_text)
                await self._show_action_buttons(GLOBAL_SESSION, update, context)
            
            elif action == "parse":
                # 解析文件内容
                GLOBAL_SESSION.state = NoteState.PARSING_CONTENT
                last_content = GLOBAL_SESSION.contents[-1]
                parsed_content = await self.ai_service.parse_file(last_content.type, last_content.content)
                GLOBAL_SESSION.add_content(MessageType.TEXT, parsed_content)
                await self._show_action_buttons(GLOBAL_SESSION, update, context)
            
            elif action == "cancel":
                # 取消当前会话
                await query.edit_message_text("已取消，您可以开始新的输入。")
                GLOBAL_SESSION.clear()
            
            elif action == "back":
                # 返回上一步
                if GLOBAL_SESSION.last_state:
                    GLOBAL_SESSION.state = GLOBAL_SESSION.last_state
                    GLOBAL_SESSION.last_state = None
                await self._show_action_buttons(GLOBAL_SESSION, update, context)

        except Exception as e:
            logger.error(f"处理回调时出错: {str(e)}", exc_info=True)
            # 显示错误消息和操作按钮
            buttons = [
                [InlineKeyboardButton("🔄 重试", callback_data=action)],
                [InlineKeyboardButton("❌ 取消", callback_data="cancel")]
            ]
            await query.edit_message_text(
                f"❌ 操作失败: {str(e)}\n\n请选择操作：",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    async def _save_note(self, session: UserSession, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """保存笔记到Blinko"""
        try:
            # 收集所有文本内容
            text_contents = []
            for content in session.contents:
                if content.type == MessageType.TEXT:
                    text_contents.append(content.content)
            
            # 合并文本内容
            note_content = "\n".join(text_contents)
            
            # 保存笔记
            result = await self.blinko_service.save_note(note_content, session.files or [])
            
            if "error" in result:
                raise Exception(result["error"])
            
            await update.callback_query.edit_message_text("✅ 笔记已保存到Blinko")
        except Exception as e:
            logger.error(f"保存笔记失败: {str(e)}")
            await update.callback_query.edit_message_text(f"❌ 保存失败: {str(e)}")
            raise

    def _detect_message_type(self, message) -> MessageType:
        """检测消息类型"""
        if message.text:
            # 检查是否是URL
            url_pattern = r'https?://\S+'
            if re.search(url_pattern, message.text):
                return MessageType.URL
            return MessageType.TEXT
        elif message.photo:
            return MessageType.IMAGE
        elif message.audio:
            return MessageType.AUDIO
        elif message.video:
            return MessageType.VIDEO
        elif message.document:
            return MessageType.FILE
        else:
            return MessageType.TEXT

    async def _process_message(self, session: UserSession, message_type: MessageType, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """处理消息内容"""
        try:
            message = update.message
            
            if message_type == MessageType.TEXT:
                session.add_content(MessageType.TEXT, message.text)
                return True
                
            elif message_type == MessageType.URL:
                session.add_content(MessageType.URL, message.text)
                return True
                
            elif message_type == MessageType.IMAGE:
                file = await message.photo[-1].get_file()
                file_info = {
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size
                }
                session.add_content(MessageType.IMAGE, file_info)
                session.files.append(file_info)
                return True
                
            elif message_type == MessageType.AUDIO:
                file = await message.audio.get_file()
                file_info = {
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size,
                    "duration": message.audio.duration,
                    "mime_type": message.audio.mime_type
                }
                session.add_content(MessageType.AUDIO, file_info)
                session.files.append(file_info)
                return True
                
            elif message_type == MessageType.VIDEO:
                file = await message.video.get_file()
                file_info = {
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size,
                    "duration": message.video.duration,
                    "mime_type": message.video.mime_type
                }
                session.add_content(MessageType.VIDEO, file_info)
                session.files.append(file_info)
                return True
                
            elif message_type == MessageType.FILE:
                file = await message.document.get_file()
                file_info = {
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size,
                    "file_name": message.document.file_name,
                    "mime_type": message.document.mime_type
                }
                session.add_content(MessageType.FILE, file_info)
                session.files.append(file_info)
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"处理消息内容时出错: {str(e)}", exc_info=True)
            raise

    async def _show_action_buttons(self, session: UserSession, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示操作按钮"""
        buttons = [
            [InlineKeyboardButton("📝 继续输入", callback_data="continue")],
            [InlineKeyboardButton("💾 保存笔记", callback_data="save")],
            [InlineKeyboardButton("📊 生成总结", callback_data="summarize")],
            [InlineKeyboardButton("🏷️ 生成标签", callback_data="tags")],
            [InlineKeyboardButton("❌ 取消", callback_data="cancel")]
        ]
        
        # 如果最后一条内容是文件，添加解析按钮
        if session.contents and session.contents[-1].type in [MessageType.IMAGE, MessageType.AUDIO, MessageType.VIDEO, MessageType.FILE]:
            buttons.insert(-1, [InlineKeyboardButton("🔍 解析内容", callback_data="parse")])
        
        # 如果最后一条内容是URL，添加解析按钮
        elif session.contents and session.contents[-1].type == MessageType.URL:
            buttons.insert(-1, [InlineKeyboardButton("🔍 解析URL", callback_data="parse_url")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text="请选择操作：",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text="请选择操作：",
                reply_markup=reply_markup
            )