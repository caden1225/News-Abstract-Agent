"""
ResponseBuilder 单元测试
"""
import pytest
from core.response_builder import ResponseBuilder


def test_build_thinking_token_frame():
    """测试构建thinking token帧"""
    frame = ResponseBuilder.build_thinking_token_frame(
        frame_id=1,
        thinking_token="思考内容",
        request_id="test_001"
    )
    
    assert "event:data" in frame
    assert "test_001" in frame
    assert "思考内容" in frame


def test_build_text_token_frame():
    """测试构建text token帧"""
    frame = ResponseBuilder.build_text_token_frame(
        frame_id=1,
        text_token="文本内容",
        request_id="test_001"
    )
    
    assert "event:data" in frame
    assert "test_001" in frame
    assert "文本内容" in frame


def test_build_audio_token_frame():
    """测试构建audio token帧"""
    import base64
    test_audio = base64.b64encode(b"test_audio_data").decode("utf-8")
    
    frame = ResponseBuilder.build_audio_token_frame(
        frame_id=1,
        audio_chunk=test_audio,
        is_final=False,
        request_id="test_001"
    )
    
    assert "event:data" in frame
    assert "test_001" in frame


def test_build_error_response():
    """测试构建错误响应"""
    frame = ResponseBuilder.build_error_response(
        error_message="测试错误",
        request_id="test_001"
    )
    
    assert "event:data" in frame
    assert "test_001" in frame
    assert "测试错误" in frame
