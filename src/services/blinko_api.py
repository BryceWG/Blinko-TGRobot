import aiohttp
from typing import Optional, Dict, Any
from src.config import BLINKO_API_URL, BLINKO_API_KEY
import logging
import asyncio
from aiohttp import ClientTimeout, ClientError

logger = logging.getLogger(__name__)

class BlinkoAPI:
    def __init__(self):
        self.base_url = BLINKO_API_URL
        self.api_key = BLINKO_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
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

    async def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """发送请求并处理响应"""
        retries = 0
        last_exception = None

        while retries < self.max_retries:
            try:
                session = await self._get_session()
                async with session.request(method, url, headers=self.headers, **kwargs) as response:
                    if response.status == 429:  # 速率限制
                        retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                        await asyncio.sleep(retry_after)
                        retries += 1
                        continue
                        
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"请求失败: {text}")
                        return {"error": f"请求失败: {response.status}", "details": text}
                    
                    return await response.json()

            except asyncio.TimeoutError as e:
                logger.warning(f"请求超时 (重试 {retries + 1}/{self.max_retries})")
                last_exception = e
            except ClientError as e:
                logger.warning(f"请求错误: {str(e)} (重试 {retries + 1}/{self.max_retries})")
                last_exception = e
            except Exception as e:
                logger.error(f"未预期的错误: {str(e)}")
                return {"error": f"请求异常: {str(e)}"}

            retries += 1
            if retries < self.max_retries:
                await asyncio.sleep(self.retry_delay * retries)

        return {"error": f"重试{self.max_retries}次后失败: {str(last_exception)}"}

    async def send_text(self, text: str, user_settings: Dict[str, Any]) -> Dict[str, Any]:
        """发送文本消息到Blinko"""
        return await self._make_request(
            "POST",
            f"{self.base_url}/text",
            json={"text": text, "settings": user_settings}
        )

    async def send_file(self, file_data: bytes, file_type: str, 
                       user_settings: Dict[str, Any]) -> Dict[str, Any]:
        """发送文件到Blinko"""
        form_data = aiohttp.FormData()
        form_data.add_field('file',
                          file_data,
                          filename=f'file.{file_type}',
                          content_type=f'application/{file_type}')
        form_data.add_field('settings', str(user_settings))
        
        return await self._make_request(
            "POST",
            f"{self.base_url}/file",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data=form_data
        ) 