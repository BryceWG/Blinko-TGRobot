from telegram import Update
from telegram.ext import ContextTypes
from src.services.blinko_api import BlinkoAPI
from src.models.user import User
from sqlalchemy.orm import Session

class MessageHandler:
    def __init__(self, db_session: Session):
        self.blinko_api = BlinkoAPI()
        self.db_session = db_session

    def get_user_settings(self, telegram_id: str) -> dict:
        """获取用户设置"""
        user = self.db_session.query(User).filter_by(telegram_id=telegram_id).first()
        return user.settings if user else {}

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息"""
        user_settings = self.get_user_settings(str(update.effective_user.id))
        response = await self.blinko_api.send_text(update.message.text, user_settings)
        await update.message.reply_text("消息已发送到Blinko")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理图片消息"""
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        user_settings = self.get_user_settings(str(update.effective_user.id))
        response = await self.blinko_api.send_file(photo_bytes, "image", user_settings)
        await update.message.reply_text("图片已发送到Blinko") 