import httpx
import json
import time
import logging
import uuid
import asyncio
from typing import Dict, Any, AsyncGenerator, Union

from fastapi import HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from app.core.config import settings
from app.providers.base_provider import BaseProvider
from app.utils.sse_utils import (
    create_sse_data, 
    create_chat_completion_chunk, 
    create_non_stream_chat_completion,
    DONE_CHUNK
)

logger = logging.getLogger(__name__)

class AskAIProvider(BaseProvider):
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.API_REQUEST_TIMEOUT)
        self.api_url = "https://pjfuothbq9.execute-api.us-east-1.amazonaws.com/get-summary"

    async def chat_completion(self, request_data: Dict[str, Any], stream: bool) -> Union[StreamingResponse, JSONResponse]:
        
        full_text, request_id, model = await self._get_upstream_response(request_data)

        if stream:
            return StreamingResponse(
                self._stream_generator(full_text, request_id, model), 
                media_type="text/event-stream"
            )
        else:
            completion_data = create_non_stream_chat_completion(request_id, model, full_text)
            return JSONResponse(content=completion_data)

    async def _get_upstream_response(self, request_data: Dict[str, Any]) -> (str, str, str):
        """
        统一处理上游请求，返回 (响应文本, 请求ID, 模型名称)。
        """
        request_id = f"chatcmpl-{uuid.uuid4()}"
        model = request_data.get("model", settings.DEFAULT_MODEL)
        
        try:
            payload = self._prepare_payload(request_data)
            headers = self._prepare_headers()

            response = await self.client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            
            # 应用【模式：JSON-in-Text-Parsing】
            response_text = response.text
            data = json.loads(response_text)
            
            summary = data.get("summary")
            if summary is None:
                raise ValueError("上游响应的 JSON 中缺少 'summary' 字段。")
            
            return summary, request_id, model

        except httpx.HTTPStatusError as e:
            logger.error(f"请求上游 API 时发生 HTTP 错误: {e.response.status_code} - {e.response.text}", exc_info=True)
            raise HTTPException(status_code=e.response.status_code, detail=f"上游服务错误: {e.response.text}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"解析上游响应时出错: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"无法解析上游服务响应: {e}")
        except Exception as e:
            logger.error(f"请求上游时发生未知错误: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"内部服务器错误: {e}")

    async def _stream_generator(self, full_text: str, request_id: str, model: str) -> AsyncGenerator[bytes, None]:
        """
        应用【模式：高速分块伪流】
        """
        try:
            # 为了达到 1000 tokens/s 的感知速度，我们每次发送2个字符，延迟1毫秒
            chunk_size = 2
            delay = 0.001 
            
            for i in range(0, len(full_text), chunk_size):
                chunk_content = full_text[i:i+chunk_size]
                chunk = create_chat_completion_chunk(request_id, model, chunk_content)
                yield create_sse_data(chunk)
                await asyncio.sleep(delay)
            
            # 发送结束标志
            final_chunk = create_chat_completion_chunk(request_id, model, "", "stop")
            yield create_sse_data(final_chunk)
            yield DONE_CHUNK
        except Exception as e:
            logger.error(f"流生成器发生错误: {e}", exc_info=True)
            error_chunk = create_chat_completion_chunk(request_id, model, f"内部错误: {e}", "stop")
            yield create_sse_data(error_chunk)
            yield DONE_CHUNK

    def _prepare_headers(self) -> Dict[str, str]:
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://askaiquestions.net",
            "referer": "https://askaiquestions.net/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        }

    def _prepare_payload(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        messages = request_data.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="请求体中缺少 'messages' 字段。")
        
        return {
            "website": "ask-ai-questions",
            "messages": messages
        }

    async def get_models(self) -> JSONResponse:
        model_data = {
            "object": "list",
            "data": [
                {"id": name, "object": "model", "created": int(time.time()), "owned_by": "lzA6"}
                for name in settings.KNOWN_MODELS
            ]
        }
        return JSONResponse(content=model_data)
