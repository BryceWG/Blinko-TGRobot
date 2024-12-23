import logging
import sys
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from src.handlers.command_handler import (
    CommandHandler as BlinkoCommandHandler,
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
)
from src.handlers.note_handler import NoteHandler
from src.database import get_session, init_db
from src.config import Config

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def error_handler(update, context):
    """处理错误"""
    logger.error(f"更新 {update} 导致错误 {context.error}")

def create_application():
    """创建应用实例"""
    # 初始化数据库
    init_db()
    
    # 创建应用
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # 获取数据库会话
    db_session = get_session()

    # 创建命令处理器实例
    command_handler = BlinkoCommandHandler(db_session)
    note_handler = NoteHandler(db_session)

    # 创建会话处理器
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", command_handler.start)],
        states={
            CHOOSING_ACTION: [
                CallbackQueryHandler(command_handler.button_handler),
            ],
            SETTING_BLINKO_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SETTING_BLINKO_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SETTING_JINA_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SETTING_AI_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SETTING_AI_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SETTING_AI_MODEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SETTING_TAG_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SETTING_SUMMARY_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
            SWITCHING_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, command_handler.handle_setting_input)
            ],
        },
        fallbacks=[CommandHandler("start", command_handler.start)],
    )

    # 添加处理器
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("settings", command_handler.settings))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, note_handler.handle_message))
    application.add_handler(CallbackQueryHandler(note_handler.handle_callback))
    application.add_error_handler(error_handler)

    return application

def main():
    """主函数"""
    try:
        # 创建应用
        application = create_application()

        # 启动机器人
        logger.info("启动机器人...")
        application.run_polling()

    except Exception as e:
        logger.error(f"程序出错: {str(e)}")
        sys.exit(1)

    finally:
        logger.info("程序退出。")

if __name__ == "__main__":
    main() 