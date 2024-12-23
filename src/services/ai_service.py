from typing import List, Dict, Any
import aiohttp
from src.models.session import NoteContent, MessageType
import logging
import asyncio
from aiohttp import ClientTimeout, ClientError
import json
from typing import Optional
import base64
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self, config: Dict[str, Any]):
        """初始化AI服务"""
        self.config = config
        self.api_key = config.get("openai_key")
        self.api_base = config.get("openai_base", "https://api.openai.com/v1")
        self.model = config.get("model", "gpt-4-vision-preview")
        self.max_tokens = config.get("max_tokens", 500)
        self.temperature = config.get("temperature", 0.7)
        self.prompts = config.get("prompts", {})
        self.session = None
        self.timeout = ClientTimeout(total=30)

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

    async def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送请求到OpenAI API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            session = await self._get_session()
            async with session.post(
                f"{self.api_base}/{endpoint}",
                headers=headers,
                json=data
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"API请求失败: {response.status} - {error_text}")
                    return None
        except Exception as e:
            logger.error(f"API请求异常: {str(e)}", exc_info=True)
            return None

    async def _call_openai(self, prompt: str) -> str:
        """调用OpenAI API"""
        result = await self._make_request(
            f"{self.api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一个专业的内容分析助手。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 1000
            }
        )
        
        if "error" in result:
            return f"OpenAI调用失败: {result['error']}"
            
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            logger.error(f"解析OpenAI响应失败: {str(e)}")
            return "AI响应解析失败"

    async def summarize(self, contents: List[NoteContent]) -> str:
        """总结消息内容"""
        # 收集所有文本内容
        text_contents = []
        for content in contents:
            if content.type == MessageType.TEXT:
                text_contents.append(content.content)
            elif content.type == MessageType.IMAGE:
                text_contents.append("[图片]")
            elif content.type == MessageType.AUDIO:
                text_contents.append("[音频]")
            elif content.type == MessageType.VIDEO:
                text_contents.append("[视频]")
            elif content.type == MessageType.URL:
                text_contents.append(f"[链接] {content.content}")
            elif content.type == MessageType.FILE:
                text_contents.append("[文件]")

        # 使用自定义提示词或默认提示词
        default_summary_prompt = """请总结以下内容，生成一个简洁的摘要：

{content}

要求：
1. 保持原文的主要信息
2. 使用简洁的语言
3. 突出重点内容
4. 长度控制在100字以内"""

        prompt = self.prompts.get("summary_prompt", default_summary_prompt).format(
            content=' '.join(text_contents)
        )

        return await self._call_openai(prompt)

    async def generate_tags(self, contents: List[str], existing_tags: List[str]) -> str:
        """生成标签建议
        
        Args:
            contents: 要生成标签的内容列表
            existing_tags: Blinko中已有的标签列表
        
        Returns:
            str: 标签建议文本，每行一个标签及其推荐理由
        """
        # 构建提示词
        content_text = " ".join(contents)
        existing_tags_text = ", ".join(existing_tags) if existing_tags else "无"
        
        # 使用自定义提示词或默认提示词
        default_tag_prompt = """作为标签推荐助手，请为以下内容推荐合适的标签：

待标记内容：
{content}

Blinko系统中已有的标签：
{tags}

要求：
1. 从已有标签中选择最相关的标签
2. 如果已有标签不足以表达内容，可以创建新标签
3. 新标签应该简洁且有意义，每个标签不超过10个字
4. 总共返回5-8个标签建议
5. 按照相关度从高到低排序
6. 每行返回一个标签，格式：标签名 - 推荐理由
7. 对于已有标签，在标签名后标注[已有]

注意：
- 优先使用已有标签，避免创建重复含义的新标签
- 标签应该具有可复用性，避免过于具体或独特
- 同时考虑内容的主题、类型、领域等多个维度"""

        prompt = self.prompts.get("tag_prompt", default_tag_prompt).format(
            content=content_text,
            tags=existing_tags_text
        )

        # 调用AI服务获取标签建议
        return await self._call_openai(prompt)

    async def parse_file(self, file_type: str, file_info: Dict) -> str:
        """解析文件内容"""
        if file_type == MessageType.IMAGE:
            prompt = "请描述这张图片的内容，包括主要对象、场景和关键细节。"
            # 这里需要实现图片解析逻辑
            return "图片解析功能开发中..."
        
        elif file_type == MessageType.AUDIO:
            # 这里需要实现音频转写逻辑
            return "音频转写功能开发中..."
        
        elif file_type == MessageType.VIDEO:
            # 这里需要实现视频解析逻辑
            return "视频解析功能开发中..."
        
        return "不支持的文件类型"

    async def describe_image(self, image_url: str) -> Optional[str]:
        """生成图片描述"""
        try:
            # 准备消息
            messages = [
                {
                    "role": "system",
                    "content": self.prompts.get("image_description", "请详细描述这张图片的内容，包括主要对象、场景、颜色、布局等关键信息。使用简洁明了的语言。")
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请描述这张图片"
                        },
                        {
                            "type": "image_url",
                            "image_url": image_url
                        }
                    ]
                }
            ]
            
            # 准备请求数据
            data = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
            
            # 发送请求
            response = await self._make_request("chat/completions", data)
            
            if response and response.get("choices"):
                return response["choices"][0]["message"]["content"].strip()
            
            return None
        
        except Exception as e:
            logger.error(f"生成图片描述失败: {str(e)}", exc_info=True)
            return None

    async def generate_tags(self, content: str) -> Optional[str]:
        """生成标签"""
        try:
            # 准备消息
            messages = [
                {
                    "role": "system",
                    "content": self.prompts.get("tag_generation", "请为以下内容生成相关的标签。标签应该简洁、准确，并且能够反映内容的主要主题和关键概念。")
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
            
            # 准备请求数据
            data = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
            
            # 发送请求
            response = await self._make_request("chat/completions", data)
            
            if response and response.get("choices"):
                return response["choices"][0]["message"]["content"].strip()
            
            return None
        
        except Exception as e:
            logger.error(f"生成标签失败: {str(e)}", exc_info=True)
            return None

    async def generate_summary(self, content: str) -> Optional[str]:
        """生成内容摘要"""
        try:
            # 准备消息
            messages = [
                {
                    "role": "system",
                    "content": self.prompts.get("summary_generation", "请为以下内容生成一个简洁的摘要，突出重点信息。")
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
            
            # 准备请求数据
            data = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
            
            # 发送请求
            response = await self._make_request("chat/completions", data)
            
            if response and response.get("choices"):
                return response["choices"][0]["message"]["content"].strip()
            
            return None
        
        except Exception as e:
            logger.error(f"生成摘要失败: {str(e)}", exc_info=True)
            return None