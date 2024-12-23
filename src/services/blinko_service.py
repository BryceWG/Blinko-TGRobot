from typing import List, Dict, Optional, Any
import aiohttp
import logging
from datetime import datetime
import asyncio
from aiohttp import ClientTimeout
from aiohttp.client_exceptions import ClientError

logger = logging.getLogger(__name__)

class BlinkoService:
    def __init__(self, config: Dict[str, Any]):
        """初始化Blinko服务"""
        self.base_url = config.get("blinko_url", "").rstrip("/")
        self.token = config.get("blinko_token")
        self.timeout = ClientTimeout(total=30)
        self.max_retries = 3
        self.retry_delay = 1
        self.session = None

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
            "Content-Type": "application/json",
            "Accept": "application/json"
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

    async def upload_file_by_url(self, file_url: str) -> Dict[str, Any]:
        """通过URL上传文件
        
        Args:
            file_url: 文件URL
        """
        data = {
            "url": file_url
        }
        
        result = await self._make_request(
            "POST",
            "/api/file/upload-by-url",
            json=data
        )
        
        if "error" in result:
            return result
            
        return {
            "filePath": result["filePath"],
            "fileName": result["fileName"],
            "originalURL": result["originalURL"],
            "type": result["type"],
            "size": result["size"]
        }

    async def save_note(self, note_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存笔记
        
        Args:
            note_data: 笔记数据，包含：
                - content: 笔记内容
                - type: 笔记类型（0: 闪念, 1: 日记）
                - attachments: 附件列表
                - createdAt: 创建时间（可选）
        """
        try:
            # 发送到blinko
            result = await self._make_request(
                "POST",
                "/api/v1/note/upsert",
                json=note_data
            )
            
            if not result:
                return {"error": "未收到响应"}
            
            # 检查响应状态
            if result.get("status") == "success":
                return {
                    "url": result.get("data", {}).get("url", ""),
                    "id": result.get("data", {}).get("id", "")
                }
            else:
                return {"error": result.get("message", "未知错误")}
                
        except Exception as e:
            logger.error(f"保存笔记失败: {str(e)}", exc_info=True)
            return {"error": str(e)}

    async def get_tags(self) -> List[Dict[str, Any]]:
        """获取所有标签"""
        result = await self._make_request("GET", "/api/v1/tags/list")
        if "error" in result:
            return {"error": result["error"]}
        return result

    async def get_ai_config(self) -> Dict[str, Any]:
        """获取AI配置"""
        return await self._make_request("GET", "/api/v1/config/list")