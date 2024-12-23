# src/handlers/note_handler.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from src.models.session import UserSession, NoteState, MessageType, NoteContent
from src.services.ai_service import AIService
from src.services.blinko_service import BlinkoService
from src.models.user import User
import re
import logging
import aiohttp
from typing import Optional
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# 全局会话状态
GLOBAL_SESSION = UserSession()

class NoteHandler:
    def __init__(self, db_session):
        self.db_session = db_session
        self.ai_service = None
        self.blinko_service = None
        self.bot = None

    async def _init_services(self, user_id: str):
        """初始化服务"""
        user = self.db_session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            raise ValueError("用户未找到")

        # 保存用户设置
        self.user_settings = user.settings

        # 初始化Blinko服务
        blinko_config = {
            "blinko_url": self.user_settings.get("blinko_url"),
            "blinko_token": self.user_settings.get("blinko_token")
        }
        self.blinko_service = BlinkoService(blinko_config)

        # 初始化AI服务
        ai_config = user.get_ai_config()
        ai_config["prompts"] = user.get_prompts()
        self.ai_service = AIService(ai_config)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理新消息"""
        try:
            # 保存bot引用
            self.bot = context.bot
            
            # 初始化服务
            await self._init_services(str(update.effective_user.id))

            # 如果状态是INITIAL，重置会话状态
            if GLOBAL_SESSION.state == NoteState.INITIAL:
                GLOBAL_SESSION.clear()
                GLOBAL_SESSION.state = NoteState.COLLECTING

            # 处理消息
            message_type = await self._detect_message_type(update.message)
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
        # 保存bot引用
        self.bot = context.bot
        
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
                    [InlineKeyboardButton("重新总结", callback_data="summarize")],
                    [InlineKeyboardButton("↩️ 返回", callback_data="back")]
                ]
                await query.edit_message_text(
                    f"总结内容：\n\n{summary}",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
            elif action == "save_summary":
                # 保存总结内容
                if GLOBAL_SESSION.current_summary:
                    GLOBAL_SESSION.add_content(MessageType.TEXT, GLOBAL_SESSION.current_summary)
                    await self._show_action_buttons(GLOBAL_SESSION, update, context)
                else:
                    await query.edit_message_text("没有可保存的总结内容")
            
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
                
                # 重新显示标签选择界面
                text_contents = [c.content for c in GLOBAL_SESSION.contents if c.type == MessageType.TEXT]
                existing_tags = await self.blinko_service.get_tags()
                existing_tag_names = [tag.get('name', '') for tag in existing_tags if isinstance(tag, dict)]
                
                # 创建标签选择按钮
                message_text = "请选择标签：\n\n"
                buttons = []
                
                for tag_name in existing_tag_names:
                    is_selected = tag_name in GLOBAL_SESSION.selected_tags
                    
                    # 添加标签说明到消息文本
                    message_text += f"{'✅ ' if is_selected else '☐ '}#{tag_name}\n"
                    
                    # 创建选择按钮
                    buttons.append([InlineKeyboardButton(
                        f"{'✅' if is_selected else ''} #{tag_name}",
                        callback_data=f"tag_{tag_name}"
                    )])
                
                buttons.append([InlineKeyboardButton("💾 完成选择", callback_data="save_tags")])
                buttons.append([InlineKeyboardButton("↩️ 返回", callback_data="back")])
                
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
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
                await query.edit_message_text("取消，您可以开始新的输入。")
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
            # 收集所有内容
            contents = []
            for content in session.contents:
                if content.type == MessageType.TEXT:
                    contents.append(content.content)
                elif content.type == MessageType.URL:
                    # 如果是URL，尝试使用JINA Reader解析
                    try:
                        jina_result = await self._parse_url_with_jina(content.content)
                        if jina_result:
                            contents.append(f"URL: {content.content}\n{jina_result}")
                        else:
                            contents.append(f"URL: {content.content}")
                    except Exception as e:
                        logger.error(f"解析URL失败: {str(e)}")
                        contents.append(f"URL: {content.content}")
            
            # 合并文本内容
            note_content = "\n\n".join(contents)
            
            # 准备笔记数据
            note_data = {
                "content": note_content,
                "type": 0,  # 闪念
                "createdAt": datetime.now(pytz.UTC).isoformat()
            }
            
            # 如果有附件，添加到笔记数据中
            if session.files:
                uploaded_files = []
                for file_info in session.files:
                    if "file_url" in file_info:
                        result = await self.blinko_service.upload_file_by_url(file_info["file_url"])
                        if result and "error" not in result:
                            uploaded_files.append(result)
                
                if uploaded_files:
                    note_data["attachments"] = uploaded_files
            
            # 保存笔记
            result = await self.blinko_service.save_note(note_data)
            
            if not result:
                raise Exception("保存笔记失败：未收到响应")
            
            if "error" in result:
                raise Exception(result["error"])
            
            await update.callback_query.edit_message_text("✅ 笔记已保存到Blinko")
            
            # 清理资源
            await self.blinko_service.close()
            if self.ai_service:
                await self.ai_service.close()
                
        except Exception as e:
            logger.error(f"保存笔记失败: {str(e)}")
            await update.callback_query.edit_message_text(f"❌ 保存失败: {str(e)}")
            
            # 确保清理资源
            try:
                await self.blinko_service.close()
                if self.ai_service:
                    await self.ai_service.close()
            except Exception as cleanup_error:
                logger.error(f"清理资源失败: {str(cleanup_error)}")
            
            raise

    async def _parse_url_with_jina(self, url: str) -> Optional[str]:
        """使用JINA Reader解析URL"""
        try:
            headers = {
                "Accept": "application/json",
                "X-Retain-Images": "none"
            }
            
            # 如果配置了JINA Key，添加到请求头
            if self.user_settings.get("jina_key"):
                headers["Authorization"] = f"Bearer {self.user_settings['jina_key']}"
            
            jina_url = f"https://r.jina.ai/{url}"
            async with aiohttp.ClientSession() as session:
                async with session.get(jina_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == 20000:
                            content = data["data"]["content"]
                            title = data["data"]["title"]
                            description = data["data"]["description"]
                            
                            # 构建解析结果
                            result = []
                            if title:
                                result.append(f"📑 标题: {title}")
                            if description:
                                result.append(f"📝 描述: {description}")
                            if content:
                                result.append(f"📄 内容:\n{content}")
                            
                            return "\n\n".join(result)
                        else:
                            logger.error(f"JINA Reader返回错误状态: {data}")
                            return None
                    else:
                        logger.error(f"JINA Reader请求失败: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"JINA Reader解析失败: {str(e)}", exc_info=True)
            return None

    async def _detect_message_type(self, message) -> MessageType:
        """检测消息类型"""
        try:
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
        except Exception as e:
            logger.error(f"检测消息类型时出错: {str(e)}", exc_info=True)
            return MessageType.TEXT

    async def _process_message(self, session: UserSession, message_type: MessageType, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """处理消息内容"""
        try:
            message = update.message
            logger.info(f"处理消息类型: {message_type}")
            
            if message_type == MessageType.TEXT:
                session.add_content(MessageType.TEXT, message.text)
                logger.info(f"添加文本内容: {message.text}")
                return True
                
            elif message_type == MessageType.URL:
                session.add_content(MessageType.URL, message.text)
                logger.info(f"添加URL内容: {message.text}")
                return True
                
            elif message_type == MessageType.IMAGE:
                file = await message.photo[-1].get_file()
                file_url = file.file_path  # 获取文件URL
                
                file_info = {
                    "file_url": file_url,
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size,
                    "mime_type": "image/jpeg"
                }
                session.add_content(MessageType.IMAGE, str(file_info))
                session.files.append(file_info)
                logger.info(f"添加图片内容: {file_info}")
                return True
                
            elif message_type == MessageType.AUDIO:
                file = await message.audio.get_file()
                file_url = file.file_path  # 获取文件URL
                
                file_info = {
                    "file_url": file_url,
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size,
                    "mime_type": message.audio.mime_type,
                    "file_name": message.audio.file_name or f"audio_{file.file_unique_id}"
                }
                session.add_content(MessageType.AUDIO, str(file_info))
                session.files.append(file_info)
                logger.info(f"添加音频内容: {file_info}")
                return True
                
            elif message_type == MessageType.VIDEO:
                file = await message.video.get_file()
                file_url = file.file_path  # 获取文件URL
                
                file_info = {
                    "file_url": file_url,
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size,
                    "mime_type": message.video.mime_type,
                    "file_name": f"video_{file.file_unique_id}"
                }
                session.add_content(MessageType.VIDEO, str(file_info))
                session.files.append(file_info)
                logger.info(f"添加视频内容: {file_info}")
                return True
                
            elif message_type == MessageType.FILE:
                file = await message.document.get_file()
                file_url = file.file_path  # 获取文件URL
                
                file_info = {
                    "file_url": file_url,
                    "file_id": file.file_id,
                    "file_unique_id": file.file_unique_id,
                    "file_size": file.file_size,
                    "mime_type": message.document.mime_type or "application/octet-stream",
                    "file_name": message.document.file_name
                }
                session.add_content(MessageType.FILE, str(file_info))
                session.files.append(file_info)
                logger.info(f"添加文件内容: {file_info}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"处理消息内容时出错: {str(e)}", exc_info=True)
            raise

    async def _show_action_buttons(self, session: UserSession, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示操作按钮"""
        try:
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
                    text="请���择操作：",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    text="请选择操作：",
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"显示操作按钮时出错: {str(e)}", exc_info=True)

    async def handle_photo(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理图片消息"""
        processing_msg = None
        try:
            # 保存bot引用
            self.bot = context.bot
            
            # 获取用户ID
            user_id = str(message.from_user.id)
            
            # 初始化服务
            await self._init_services(user_id)
            
            # 获取最大的图片文件
            photo = message.photo[-1]
            
            # 获取文件URL
            file = await self.bot.get_file(photo.file_id)
            file_url = file.file_path
            
            # 发送处理中的提示
            processing_msg = await message.reply_text("正在处理图片，请稍候...")
            
            try:
                # 上传图片到Blinko
                file_info = await self.blinko_service.upload_file_by_url(file_url)
                
                if not file_info or "error" in file_info:
                    error_msg = file_info.get("error", "未知错误") if file_info else "上传失败"
                    await processing_msg.edit_text(f"图片上传失败: {error_msg}")
                    return
                
                # 获取图片描述
                if self.ai_service and self.user_settings.get("enable_image_description", True):
                    description = await self.ai_service.describe_image(file_url)
                    if description:
                        # 准备笔记数据
                        note_data = {
                            "content": description,
                            "type": 0,  # 闪念
                            "attachments": [file_info],
                            "createdAt": datetime.now(pytz.UTC).isoformat()
                        }
                        
                        # 保存笔记
                        note = await self.blinko_service.save_note(note_data)
                        
                        if not note:
                            await processing_msg.edit_text("笔记保存失败：未收到响应")
                            return
                        
                        if "error" in note:
                            await processing_msg.edit_text(f"笔记保存失败: {note['error']}")
                            return
                        
                        # 构建成功消息
                        success_msg = [
                            "✅ 图片已成功上传并保存",
                            f"📝 图片描述:\n{description}",
                            f"🔗 笔记链接: {note.get('url', '')}"
                        ]
                        await processing_msg.edit_text("\n\n".join(success_msg))
                    else:
                        await processing_msg.edit_text("图片描述生成失败，但图片已上传。")
                else:
                    # 直接保存图片
                    note_data = {
                        "content": "图片笔记",
                        "type": 0,  # 闪念
                        "attachments": [file_info],
                        "createdAt": datetime.now(pytz.UTC).isoformat()
                    }
                    
                    # 保存笔记
                    note = await self.blinko_service.save_note(note_data)
                    
                    if not note:
                        await processing_msg.edit_text("笔记保存失败：未收到响应")
                        return
                    
                    if "error" in note:
                        await processing_msg.edit_text(f"笔记保存失败: {note['error']}")
                        return
                    
                    success_msg = [
                        "✅ 图片已成功上传并保存",
                        f"🔗 笔记链接: {note.get('url', '')}"
                    ]
                    await processing_msg.edit_text("\n\n".join(success_msg))
            
            except Exception as e:
                logger.error(f"图片处理失败: {str(e)}", exc_info=True)
                if processing_msg:
                    await processing_msg.edit_text("图片处理过程中出现错误，请重试。")
        
        except Exception as e:
            logger.error(f"图片处理失败: {str(e)}", exc_info=True)
            error_msg = "图片处理失败，请确保您已完成配置并重试。"
            if processing_msg:
                await processing_msg.edit_text(error_msg)
            else:
                await message.reply_text(error_msg)
        
        finally:
            # 清理资源
            try:
                await self.blinko_service.close()
                if self.ai_service:
                    await self.ai_service.close()
            except Exception as cleanup_error:
                logger.error(f"清理资源失败: {str(cleanup_error)}")