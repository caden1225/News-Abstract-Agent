"""
响应构建器模块
负责构建各种类型的响应帧
"""
import time
import logging
from typing import List, Dict, Any, Optional

from models.api import BaseResponse, ResponseData, FramePart, FramePartAudio, FramePartImage

logger = logging.getLogger(__name__)


class ResponseBuilder:
    """响应构建器类"""
    
    @staticmethod
    def build_thinking_token_frame(
        frame_id: int,
        thinking_token: str,
        request_id: str,
        version: str = "2.1"
    ) -> str:
        """构建 thinking token 流式帧"""
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=thinking_token,
            content=thinking_token,
            frame_is_final=False,
            response_type="thinking",
            extension={
                "token_type": "thinking"
            }
        )
        
        response = BaseResponse(
            version=version,
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
    
    @staticmethod
    def build_text_token_frame(
        frame_id: int,
        text_token: str,
        request_id: str,
        version: str = "2.1"
    ) -> str:
        """构建 text token 流式帧"""
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=text_token,
            content=text_token,
            frame_is_final=False,
            response_type="text",
            extension={
                "token_type": "content"
            }
        )
        
        response = BaseResponse(
            version=version,
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
    
    @staticmethod
    def build_audio_token_frame(
        frame_id: int,
        audio_chunk: str,
        is_final: bool,
        request_id: str,
        version: str = "2.1"
    ) -> str:
        """构建 audio 流式帧"""
        frame_parts = [
            FramePart(
                type="audio",
                audio=FramePartAudio(
                    format="pcm",
                    data=f"data:;base64,{audio_chunk}",
                    is_final=is_final
                )
            )
        ]
        
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            content="",
            frame_is_final=is_final,
            response_type="audio",
            frame_parts=frame_parts,
            extension={
                "token_type": "audio",
                "is_final": is_final
            }
        )
        
        response = BaseResponse(
            version=version,
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
    
    @staticmethod
    def build_image_frame(
        frame_id: int,
        image_links: List[str],
        request_id: str,
        version: str = "2.1"
    ) -> str:
        """构建包含图片链接的初始帧"""
        frame_parts = []
        
        # 为每个图片链接创建 FramePart
        for img_url in image_links[:10]:  # 最多10张图片
            # 从URL推断图片格式
            img_format = "jpg"  # 默认格式
            if img_url:
                if img_url.endswith((".png", ".PNG")):
                    img_format = "png"
                elif img_url.endswith((".jpg", ".jpeg", ".JPG", ".JPEG")):
                    img_format = "jpg"
                elif img_url.endswith((".gif", ".GIF")):
                    img_format = "gif"
                elif img_url.endswith((".webp", ".WEBP")):
                    img_format = "webp"
            
            frame_parts.append(
                FramePart(
                    type="image",
                    image=FramePartImage(
                        format=img_format,
                        data=img_url
                    )
                )
            )
        
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            content="",
            frame_is_final=False,
            response_type="image",
            frame_parts=frame_parts if frame_parts else None,
            extension={
                "image_count": len(image_links),
                "total_images": len(image_links)
            }
        )
        
        response = BaseResponse(
            version=version,
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
    
    @staticmethod
    def build_final_stream_frame(
        frame_id: int,
        full_text: str,
        thinking_content: str,
        request_id: str,
        debug_info: Optional[Dict[str, Any]] = None,
        system_agent_response: Optional[Dict[str, Any]] = None,
        version: str = "2.1"
    ) -> str:
        """
        构建流式生成的最终帧
        
        Args:
            frame_id: 帧ID
            full_text: 完整文本内容
            thinking_content: 思考内容
            request_id: 请求ID
            debug_info: 从状态中提取的debug信息（优先使用）
            system_agent_response: systemAgent响应（可选，用于合并外部debug信息）
            version: LLM Protocol 版本号
        """
        from core.utils import (
            extract_debug_info_from_system_agent,
            merge_debug_info
        )
        
        # 优先使用传入的debug_info，如果没有则尝试从systemAgent响应中提取
        final_debug_info = debug_info
        if not final_debug_info and system_agent_response:
            final_debug_info = extract_debug_info_from_system_agent(system_agent_response)
        elif final_debug_info and system_agent_response:
            # 如果两者都有，合并它们
            system_debug_info = extract_debug_info_from_system_agent(system_agent_response)
            final_debug_info = merge_debug_info(final_debug_info, system_debug_info)
        
        # 最后一帧不需要传递图片或语音，仅提供 complete_content
        response_data = ResponseData(
            event="completed", #需要在最终帧中添加
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            content=full_text,
            frame_is_final=True,
            complete_content=full_text,
            frame_parts=None,
            extension={
                "thinking_content": thinking_content,
                "total_text_length": len(full_text),
                "total_thinking_length": len(thinking_content),
            },
            debug_info=final_debug_info
        )
        
        response = BaseResponse(
            version=version,
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
    
    @staticmethod
    def build_error_response(
        error_message: str,
        request_id: str,
        version: str = "2.1"
    ) -> str:
        """
        构建错误响应
        """
        response_data = ResponseData(
            frame_id=0,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=True
        )

        response = BaseResponse(
            version=version,
            request_id=request_id,
            code=500,
            message=error_message,
            data=response_data
        )

        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
