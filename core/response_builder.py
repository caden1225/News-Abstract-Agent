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
        request_id: str
    ) -> str:
        """构建 thinking token 流式帧"""
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=thinking_token,
            frame_is_final=False,
            response_type="thinking",
            extension={
                "token_type": "thinking"
            }
        )
        
        response = BaseResponse(
            version="2.1",
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
        request_id: str
    ) -> str:
        """构建 text token 流式帧"""
        response_data = ResponseData(
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text=text_token,
            frame_is_final=False,
            response_type="text",
            extension={
                "token_type": "content"
            }
        )
        
        response = BaseResponse(
            version="2.1",
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
        request_id: str
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
            frame_is_final=False,
            response_type="audio",
            frame_parts=frame_parts,
            extension={
                "token_type": "audio"
            }
        )
        
        response = BaseResponse(
            version="2.1",
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
        request_id: str
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
            frame_is_final=False,
            response_type="image",
            frame_parts=frame_parts if frame_parts else None,
            extension={
                "image_count": len(image_links),
                "total_images": len(image_links)
            }
        )
        
        response = BaseResponse(
            version="2.1",
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
        image_links: List[str],
        request_id: str,
        debug_info: Optional[Dict[str, Any]] = None,
        system_agent_response: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建流式生成的最终帧
        
        Args:
            frame_id: 帧ID
            full_text: 完整文本内容
            thinking_content: 思考内容
            image_links: 图片链接列表
            request_id: 请求ID
            debug_info: 从状态中提取的debug信息（优先使用）
            system_agent_response: systemAgent响应（可选，用于合并外部debug信息）
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
            frame_id=frame_id,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=True,
            complete_content=full_text,
            frame_parts=None,
            extension={
                "thinking_content": thinking_content,
                "total_text_length": len(full_text),
                "total_thinking_length": len(thinking_content),
                "image_count": len(image_links)
            },
            debug_info=final_debug_info
        )
        
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )
        
        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
    
    @staticmethod
    def build_final_response(
        state: Dict[str, Any],
        request_id: str,
        request_start_time: Optional[float] = None,
        system_agent_response: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建最终响应（非流式模式）
        
        Args:
            state: 状态对象
            request_id: 请求ID
            request_start_time: 请求开始时间（可选，用于计算总耗时）
            system_agent_response: 可选的systemAgent响应消息，用于提取debug_info
        """
        from core.utils import (
            extract_debug_info_from_system_agent,
            merge_debug_info,
            build_debug_info_from_state
        )
        
        summary = state.get("summary", "")
        image_links = state.get("image_links", [])
        audio_data = state.get("audio_data")
        thinking_chain = state.get("thinking_chain", [])
        
        # 从状态中提取debug_info
        debug_info = build_debug_info_from_state(state, request_start_time)
        
        # 如果提供了systemAgent响应，合并debug信息
        if system_agent_response:
            system_debug_info = extract_debug_info_from_system_agent(system_agent_response)
            debug_info = merge_debug_info(debug_info, system_debug_info)

        # 构建响应数据
        response_data = ResponseData(
            frame_id=0,
            frame_timestamp=int(time.time() * 1000),
            frame_text="",
            frame_is_final=True,
            complete_content=summary,
            extension={
                "news_count": state.get("news_count", 0),
                "processing_steps": state.get("processing_steps", []),
                "image_count": len(image_links),
                "tts_language": state.get("tts_language", "zh"),
                "thinking_chain": thinking_chain
            },
            debug_info=debug_info
        )

        # 添加音频和图片（如果有）
        frame_parts = []
        if audio_data:
            frame_parts.append(
                FramePart(
                    type="audio",
                    audio=FramePartAudio(
                        format="pcm",
                        data=f"data:;base64,{audio_data}",
                        is_final=True
                    )
                )
            )
        
        # 添加图片链接
        for img_url in image_links[:10]:  # 最多10张图片
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

        if frame_parts:
            response_data.frame_parts = frame_parts

        # 构建完整响应
        response = BaseResponse(
            version="2.1",
            request_id=request_id,
            code=0,
            message="success",
            data=response_data
        )

        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
    
    @staticmethod
    def build_error_response(
        error_message: str,
        request_id: str
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
            version="2.1",
            request_id=request_id,
            code=500,
            message=error_message,
            data=response_data
        )

        return f"event:data\ndata:{response.model_dump_json(exclude_none=False)}\n\n"
