import json
import time
from typing import Dict, Any, Optional

DONE_CHUNK = b"data: [DONE]\n\n"

def create_sse_data(data: Dict[str, Any]) -> bytes:
    """将字典数据格式化为 SSE 事件字符串。"""
    return f"data: {json.dumps(data)}\n\n".encode('utf-8')

def create_chat_completion_chunk(
    request_id: str,
    model: str,
    content: str,
    finish_reason: Optional[str] = None
) -> Dict[str, Any]:
    """创建一个与 OpenAI 兼容的聊天补全流式块。"""
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content},
                "finish_reason": finish_reason
            }
        ]
    }

def create_non_stream_chat_completion(
    request_id: str,
    model: str,
    content: str
) -> Dict[str, Any]:
    """创建一个与 OpenAI 兼容的非流式聊天补全响应。"""
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
