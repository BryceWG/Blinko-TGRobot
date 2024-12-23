# Blinko Telegram Bot

这是一个用于将消息转发到Blinko服务器的Telegram机器人。

## 功能特点

- 支持发送文本消息到Blinko
- 支持发送图片到Blinko
- 用户个性化设置管理
- 可扩展的模块化设计

## 项目结构

```
.
├── src/
│   ├── handlers/           # 消息和命令处理器
│   ├── models/            # 数据模型
│   ├── services/          # 外部服务接口
│   ├── config.py         # 配置管理
│   └── database.py       # 数据库连接
├── main.py               # 主程序入口
├── requirements.txt      # 项目依赖
└── .env.example         # 环境变量模板
```

## 安装

1. 克隆项目
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 复制 `.env.example` 到 `.env` 并填写配置：
   ```bash
   cp .env.example .env
   ```

## 配置

在 `.env` 文件中设置以下环境变量：

- `TELEGRAM_BOT_TOKEN`: Telegram机器人token
- `BLINKO_API_URL`: Blinko API地址
- `BLINKO_API_KEY`: Blinko API密钥
- `DATABASE_URL`: 数据库连接URL（默认使用SQLite）

## 运行

```bash
python main.py
```

## 使用方法

1. 在Telegram中搜索你的机器人并启动
2. 使用 `/start` 命令初始化账户
3. 使用 `/settings` 查看当前设置
4. 使用 `/set key value` 修改设置
5. 直接发送文本或图片，机器人会自动转发到Blinko

## 扩展开发

1. 在 `src/services` 中添加新的外部服务接口
2. 在 `src/handlers` 中添加新的消息处理逻辑
3. 在 `src/models` 中添加新的数据模型

## 贡献

欢迎提交Issue和Pull Request！ 