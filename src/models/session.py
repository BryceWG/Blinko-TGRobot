# src/models/session.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime

@dataclass
class NoteContent:
    """单条消息内容"""
    type: str  # text, image, audio, video, url, file
    content: str
    metadata: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class UserSession:
    """用户会话"""
    contents: List[NoteContent] = field(default_factory=list)
    files: List[Dict] = field(default_factory=list)  # 存储已上传的文件信息
    current_summary: Optional[str] = None
    selected_tags: List[str] = field(default_factory=list)
    state: str = "INITIAL"
    last_state: Optional[str] = None

    def add_content(self, content_type: str, content: str, metadata: Dict = None):
        self.contents.append(NoteContent(
            type=content_type,
            content=content,
            metadata=metadata or {}
        ))

    def clear(self):
        self.contents.clear()
        self.files.clear()
        self.current_summary = None
        self.selected_tags.clear()
        self.state = "INITIAL"
        self.last_state = None

class NoteState:
    """笔记状态"""
    INITIAL = "INITIAL"              # 初始状态
    COLLECTING = "COLLECTING"        # 正在收集内容
    AWAITING_ACTION = "AWAITING_ACTION"  # 等待用户操作
    SUMMARIZING = "SUMMARIZING"      # 正在生成总结
    SELECTING_TAGS = "SELECTING_TAGS"  # 正在选择标签
    PARSING_CONTENT = "PARSING_CONTENT"  # 正在解析内容（文件/URL）

class MessageType:
    """消息类型"""
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    URL = "URL"
    FILE = "FILE"