# Blinko API调用指南
## 笔记上传API
```python
import requests

url = "https://your-domain/api/v1/note/upsert"

payload = {
    "content": "Hi, this is a test note",
    "type": 0,
    "attachments": []
}
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_SECRET_TOKEN"
}

response = requests.post(url, json=payload, headers=headers)

print(response.json())
```
说明:
- 需要使用Blinko的API密钥进行认证
- 笔记内容和附件需要根据实际情况进行填充
- content: 笔记内容
- type: 0 表示闪念，1 表示笔记
- attachments: 附件列表，每个附件是一个字典，包含文件名和文件路径

## 用户标签查询
```python
import requests
from typing import Dict, List

def build_tag_hierarchy(tags: List[Dict]) -> Dict[int, Dict]:
    """构建标签的层级字典
    
    Args:
        tags: 标签列表
    
    Returns:
        包含标签层级关系的字典
    """
    tag_dict = {}
    for tag in tags:
        tag_dict[tag['id']] = {
            'name': tag['name'],
            'parent': tag['parent'],
            'children': []
        }
    return tag_dict

def get_full_tag_path(tag_id: int, tag_dict: Dict) -> str:
    """获取完整的标签路径
    
    Args:
        tag_id: 标签ID
        tag_dict: 标签层级字典
    
    Returns:
        完整的标签路径字符串
    """
    if tag_id not in tag_dict:
        return ""
    
    current_tag = tag_dict[tag_id]
    if current_tag['parent'] == 0:
        return f"#{current_tag['name']}"
    
    parent_path = get_full_tag_path(current_tag['parent'], tag_dict)
    return f"{parent_path}/{current_tag['name']}"

def main():
    url = "https://your-domain/api/v1/tags/list"
    headers = {"Authorization": "Bearer YOUR_SECRET_TOKEN"}

    response = requests.get(url, headers=headers)
    tags = response.json()
    
    # 构建标签层级关系
    tag_dict = build_tag_hierarchy(tags)
    
    # 获取所有完整的标签路径
    tag_paths = set()
    for tag in tags:
        path = get_full_tag_path(tag['id'], tag_dict)
        if path:
            tag_paths.add(path)
    
    # 按字母顺序排序并打印
    for path in sorted(tag_paths):
        print(path)

if __name__ == "__main__":
    main()
```

## JINA Reader API
```python
import requests

headers = {
    "Accept": "application/json",
    "Authorization": "Bearer YOUR_SECRET_TOKEN",
    "X-Retain-Images": "none"
}

response = requests.get("https://r.jina.ai/https://example.com", headers=headers)

print(response.text)

```
说明:
- 使用JINA Reader的API进行网页内容提取
- 可选使用JINA Reader的API密钥进行认证,填入APIkey时可以加速网页内容提取
- 可选使用X-Retain-Images: none, 不保留网页中的图片
- 返回值为以下json示例,包含网页的标题、描述、URL、内容和使用情况:
```json
{
  "code": 200,
  "status": 20000,
  "data": {
    "images": {},
    "title": "Example Domain",
    "description": "",
    "url": "https://example.com/",
    "content": "This domain is for use in illustrative examples in documents. You may use this domain in literature without prior coordination or asking for permission.\n\n[More information...](https://www.iana.org/domains/example)",
    "usage": {
      "tokens": 42
    }
  }
}
```
- 拼接url时, 需要使用https://r.jina.ai/ 作为前缀

## Blinko AI 配置参数读取
```python
import requests

url = "https://your-domain/api/v1/config/list"

headers = {"Authorization": "Bearer YOUR_SECRET_TOKEN"}

response = requests.get(url, headers=headers)

print(response.json())
```

说明:
- 返回值为json格式, 包含AI配置参数
```json
{
  "isAutoArchived": true,
  "autoArchivedDays": 1,
  "isUseAI": true,
  "aiModelProvider": null, # 模型提供商,通常为openai,ollama或azure openai
  "aiApiKey": null, # 模型API密钥
  "aiApiEndpoint": null, # 模型API端点
  "aiApiVersion": null, # 模型API版本
  "aiModel": null, # 模型名称
  "isHiddenMobileBar": true,
  "toolbarVisibility": null,
  "isAllowRegister": null,
  "isOrderByCreateTime": null,
  "timeFormat": null,
  "smallDeviceCardColumns": null,
  "mediumDeviceCardColumns": null,
  "largeDeviceCardColumns": null,
  "textFoldLength": 1,
  "objectStorage": null,
  "s3AccessKeyId": null,
  "s3AccessKeySecret": null,
  "s3Endpoint": null,
  "s3Bucket": null,
  "s3CustomPath": null,
  "s3Region": null,
  "localCustomPath": null,
  "embeddingModel": null,
  "embeddingTopK": 1,
  "embeddingLambda": 1,
  "embeddingScore": 1,
  "excludeEmbeddingTagId": 1,
  "language": null,
  "theme": null,
  "webhookEndpoint": null,
  "twoFactorEnabled": true,
  "twoFactorSecret": "…",
  "spotifyConsumerKey": "…",
  "spotifyConsumerSecret": "…"
}
``` 
- 读取Blinko的配置参数, 主要是openai类型的AI配置参数, 用于配置AI模型和API密钥

## Blinko 文件上传API
```python
import requests

url = "https://your-domain/api/file/upload-by-url"

# 设置请求头
headers = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8",
    "cache-control": "no-cache",
    "content-type": "application/json; charset=UTF-8",
    "pragma": "no-cache",
    "authorization": "Bearer YOUR_SECRET_TOKEN"
}

# 请求体数据
data = {
    "url": "文件url"
}

# 发送POST请求
response = requests.post(
    url=url,
    headers=headers,
    json=data,
    verify=True
)

print(response.text)
```
- 返回值为json格式, 包含文件的url
```json
{"Message":"Success","status":200,"filePath":"/api/s3file/0091ee2c68746bc7f8193e527efb3c08_1734683118713.png","fileName":"0091ee2c68746bc7f8193e527efb3c08_1734683118713.png","originalURL":"https://pic.brycewg.xyz/pics/2024/12/0091ee2c68746bc7f8193e527efb3c08.png","type":"image/png","size":240659}
```
