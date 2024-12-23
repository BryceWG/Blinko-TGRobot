from typing import List, Dict, Optional, Any
import aiohttp
import logging
from datetime import datetime
import asyncio
from aiohttp import ClientTimeout
from aiohttp.client_exceptions import ClientError

logger = logging.getLogger(__name__)

class BlinkoService:
    def __init__(self, config: dict):
        """初始化Blinko服务
        
        Args:
            config (dict): 配置信息，包含：
                - blinko_url: Blinko服务器URL
                - blinko_token: Blinko API Token
        """
        self.base_url = config.get("blinko_url", "").rstrip('/')
        self.token = config.get("blinko_token")
        self.session = None
        self.timeout = ClientTimeout(total=30)
        self.max_retries = 3
        self.retry_delay = 1

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    async def close(self):
        """关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送请求并处理响应"""
        if not self.base_url or not self.token:
            return {"error": "未配置Blinko服务"}

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        kwargs["headers"] = headers

        retries = 0
        last_exception = None

        while retries < self.max_retries:
            try:
                session = await self._get_session()
                async with session.request(method, url, **kwargs) as response:
                    if response.status == 429:  # 速率限制
                        retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                        await asyncio.sleep(retry_after)
                        retries += 1
                        continue

                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"Blinko请求失败: {text}")
                        return {"error": f"请求失败: {response.status}", "details": text}

                    return await response.json()

            except asyncio.TimeoutError as e:
                logger.warning(f"Blinko请求超时 (重试 {retries + 1}/{self.max_retries})")
                last_exception = e
            except ClientError as e:
                logger.warning(f"Blinko请求错误: {str(e)} (重试 {retries + 1}/{self.max_retries})")
                last_exception = e
            except Exception as e:
                logger.error(f"未预期的错误: {str(e)}")
                return {"error": f"请求异常: {str(e)}"}

            retries += 1
            if retries < self.max_retries:
                await asyncio.sleep(self.retry_delay * retries)

        return {"error": f"重试{self.max_retries}次后失败: {str(last_exception)}"}

    async def get_tags(self) -> List[Dict[str, Any]]:
        """获取所有标签"""
        result = await self._make_request("GET", "/api/v1/tags/list")
        if "error" in result:
            return {"error": result["error"]}
        return result

    async def save_note(self, content: str, files: List[Dict] = None) -> Dict[str, Any]:
        """保存笔记
        
        Args:
            content: 笔记内容
            files: 附件列表
        """
        data = {
            "content": content,
            "type": 0,  # 普通笔记
        }
        
        if files:
            # 上传文件
            uploaded_files = []
            for file in files:
                file_result = await self._make_request(
                    "POST",
                    "/api/v1/file/upload",
                    json=file
                )
                if "error" not in file_result:
                    uploaded_files.append(file_result)
            
            if uploaded_files:
                data["attachments"] = uploaded_files

        # 保存笔记
        return await self._make_request(
            "POST",
            "/api/v1/note/upsert",
            json=data
        )