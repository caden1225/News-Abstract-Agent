"""
可集成的TTS服务模块

提供简洁的API接口，便于集成到其他项目中。
支持流式文本输入和流式音频输出。
"""

import torch
import queue
import threading
import time
from typing import Generator, Iterator, Optional, Callable, Union, List
from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2, CosyVoice3, AutoModel
from cosyvoice.utils.file_utils import load_wav


class TTSService:
    """
    可集成的TTS服务类
    
    提供统一的接口，支持：
    - 流式文本输入
    - 流式音频输出
    - 预置音色合成
    - Zero-shot语音克隆
    """
    
    def __init__(
        self,
        model_dir: str,
        model_type: str = "auto",
        spk_id: str = "girl_zh",
        load_jit: bool = False,
        load_trt: bool = False,
        load_vllm: bool = False,
        fp16: bool = False,
        trt_concurrent: int = 1,
        **kwargs
    ):
        """
        初始化TTS服务
        
        Args:
            model_dir: 模型目录路径
            model_type: 模型类型 ("auto", "cosyvoice2", "cosyvoice3")
            spk_id: 默认说话人ID
            load_jit: 是否加载JIT优化模型
            load_trt: 是否加载TensorRT优化
            load_vllm: 是否加载vLLM加速
            fp16: 是否使用FP16精度
            trt_concurrent: TensorRT并发数
            **kwargs: 其他传递给模型的参数
        """
        # 验证 model_dir 参数
        if model_dir is None or model_dir == "null" or model_dir == "":
            raise ValueError(f"model_dir 不能为空或 'null': {model_dir}")
        
        self.model_dir = model_dir
        self.default_spk_id = spk_id
        
        # 根据model_type加载模型
        import os
        if model_type == "auto":
            # 自动检测模型类型，根据实际类型传递正确的参数
            if not os.path.exists(model_dir):
                from modelscope import snapshot_download
                model_dir = snapshot_download(model_dir)
            
            # 检查模型类型并调用相应的类
            if os.path.exists(os.path.join(model_dir, 'cosyvoice3.yaml')):
                # CosyVoice3不支持load_jit
                self.model = CosyVoice3(
                    model_dir=model_dir,
                    load_trt=load_trt,
                    load_vllm=load_vllm,
                    fp16=fp16,
                    trt_concurrent=trt_concurrent,
                    **kwargs
                )
            elif os.path.exists(os.path.join(model_dir, 'cosyvoice2.yaml')):
                self.model = CosyVoice2(
                    model_dir=model_dir,
                    load_jit=load_jit,
                    load_trt=load_trt,
                    load_vllm=load_vllm,
                    fp16=fp16,
                    trt_concurrent=trt_concurrent,
                    **kwargs
                )
            elif os.path.exists(os.path.join(model_dir, 'cosyvoice.yaml')):
                self.model = CosyVoice(
                    model_dir=model_dir,
                    load_jit=load_jit,
                    load_trt=load_trt,
                    fp16=fp16,
                    trt_concurrent=trt_concurrent,
                    **kwargs
                )
            else:
                raise ValueError(f'无法检测模型类型，请检查模型目录: {model_dir}')
        elif model_type == "cosyvoice2":
            self.model = CosyVoice2(
                model_dir=model_dir,
                load_jit=load_jit,
                load_trt=load_trt,
                load_vllm=load_vllm,
                fp16=fp16,
                trt_concurrent=trt_concurrent,
                **kwargs
            )
        elif model_type == "cosyvoice3":
            self.model = CosyVoice3(
                model_dir=model_dir,
                load_trt=load_trt,
                load_vllm=load_vllm,
                fp16=fp16,
                trt_concurrent=trt_concurrent,
                **kwargs
            )
        else:
            raise ValueError(f"Unknown model_type: {model_type}")
        
        self.sample_rate = self.model.sample_rate
    
    def list_speakers(self) -> List[str]:
        """
        列出所有可用的说话人ID
        
        Returns:
            说话人ID列表
        """
        return self.model.list_available_spks()
    
    def synthesize(
        self,
        text: str,
        spk_id: Optional[str] = None,
        stream: bool = False,
        speed: float = 1.0
    ) -> Generator[torch.Tensor, None, None]:
        """
        合成单个文本的语音
        
        Args:
            text: 要合成的文本
            spk_id: 说话人ID，如果为None则使用默认值
            stream: 是否流式输出
            speed: 语速倍数
            
        Yields:
            torch.Tensor: 音频数据块，shape为 (1, samples)
        """
        if spk_id is None:
            spk_id = self.default_spk_id
        
        for result in self.model.inference_sft(
            tts_text=text,
            spk_id=spk_id,
            stream=stream,
            speed=speed
        ):
            yield result['tts_speech']
    
    def synthesize_streaming(
        self,
        text_chunks: Union[List[str], Generator[str, None, None]],
        spk_id: Optional[str] = None,
        stream: bool = True,
        speed: float = 1.0,
        token_hop_len: Optional[int] = None,
    ) -> Generator[torch.Tensor, None, None]:
        """
        流式合成多个文本块的语音
        
        Args:
            text_chunks: 文本块列表或生成器
            spk_id: 说话人ID，如果为None则使用默认值
            stream: 是否流式输出音频
            speed: 语速倍数（流式模式下建议使用1.0）
            token_hop_len: 输出chunk大小（可选）
            
        Yields:
            torch.Tensor: 音频数据块，shape为 (1, samples)
        """
        if spk_id is None:
            spk_id = self.default_spk_id
        
        # 检查是否有inference_sft_chunked方法
        if hasattr(self.model, 'inference_sft_chunked'):
            for result in self.model.inference_sft_chunked(
                text_chunks=text_chunks,
                spk_id=spk_id,
                stream=stream,
                speed=speed,
                token_hop_len=token_hop_len,
            ):
                yield result['tts_speech']
        else:
            # 如果没有chunked方法，则逐个处理文本块
            if isinstance(text_chunks, (list, tuple)):
                for chunk in text_chunks:
                    for result in self.model.inference_sft(
                        tts_text=chunk,
                        spk_id=spk_id,
                        stream=stream,
                        speed=speed
                    ):
                        yield result['tts_speech']
            else:
                for chunk in text_chunks:
                    for result in self.model.inference_sft(
                        tts_text=chunk,
                        spk_id=spk_id,
                        stream=stream,
                        speed=speed
                    ):
                        yield result['tts_speech']
    
    def synthesize_zero_shot(
        self,
        text: str,
        prompt_text: str,
        prompt_wav: Union[str, torch.Tensor],
        stream: bool = False,
        speed: float = 1.0
    ) -> Generator[torch.Tensor, None, None]:
        """
        Zero-shot语音克隆
        
        Args:
            text: 要合成的文本
            prompt_text: 参考音频的文本
            prompt_wav: 参考音频路径或tensor（16kHz）
            stream: 是否流式输出
            speed: 语速倍数
            
        Yields:
            torch.Tensor: 音频数据块
        """
        # 加载参考音频
        if isinstance(prompt_wav, str):
            prompt_speech = load_wav(prompt_wav, 16000)
        else:
            prompt_speech = prompt_wav
        
        for result in self.model.inference_zero_shot(
            tts_text=text,
            prompt_text=prompt_text,
            prompt_speech_16k=prompt_speech,
            stream=stream,
            speed=speed
        ):
            yield result['tts_speech']
    
    def synthesize_from_queue(
        self,
        text_queue: queue.Queue,
        spk_id: Optional[str] = None,
        end_marker: str = "<END>",
        stream: bool = True,
        token_hop_len: Optional[int] = None,
    ) -> Generator[torch.Tensor, None, None]:
        """
        从队列读取文本并流式合成语音
        
        Args:
            text_queue: 文本队列
            spk_id: 说话人ID
            end_marker: 结束标记
            stream: 是否流式输出
            token_hop_len: 输出chunk大小
            
        Yields:
            torch.Tensor: 音频数据块
        """
        def text_generator():
            while True:
                try:
                    text = text_queue.get(timeout=0.1)
                    if text == end_marker:
                        break
                    if text and text.strip():
                        yield text
                except queue.Empty:
                    continue
        
        yield from self.synthesize_streaming(
            text_chunks=text_generator(),
            spk_id=spk_id,
            stream=stream,
            token_hop_len=token_hop_len,
        )
    
    def synthesize_from_callback(
        self,
        text_callback: Callable[[], Optional[str]],
        spk_id: Optional[str] = None,
        stream: bool = True,
        poll_interval: float = 0.1,
        token_hop_len: Optional[int] = None,
    ) -> Generator[torch.Tensor, None, None]:
        """
        通过回调函数获取文本并流式合成语音
        
        Args:
            text_callback: 回调函数，返回文本块或None（表示结束）
            spk_id: 说话人ID
            stream: 是否流式输出
            poll_interval: 轮询间隔（秒）
            token_hop_len: 输出chunk大小
            
        Yields:
            torch.Tensor: 音频数据块
        """
        def text_generator():
            while True:
                text = text_callback()
                if text is None:
                    break
                if text and text.strip():
                    yield text
                time.sleep(poll_interval)
        
        yield from self.synthesize_streaming(
            text_chunks=text_generator(),
            spk_id=spk_id,
            stream=stream,
            token_hop_len=token_hop_len,
        )


class AsyncTTSService:
    """
    异步TTS服务类
    
    使用多线程实现异步处理，适合高并发场景
    """
    
    def __init__(self, tts_service: TTSService):
        """
        初始化异步TTS服务
        
        Args:
            tts_service: TTSService实例
        """
        self.tts_service = tts_service
        self.audio_queue = queue.Queue()
        self.processing_thread = None
        self.is_running = False
    
    def start_streaming(
        self,
        text_chunks: Union[List[str], Generator[str, None, None]],
        spk_id: Optional[str] = None,
        stream: bool = True,
        token_hop_len: Optional[int] = None,
    ):
        """
        启动异步流式处理
        
        Args:
            text_chunks: 文本块列表或生成器
            spk_id: 说话人ID
            stream: 是否启用流式输出
            token_hop_len: 输出chunk大小
        """
        self.is_running = True
        
        def process_audio():
            try:
                for audio in self.tts_service.synthesize_streaming(
                    text_chunks=text_chunks,
                    spk_id=spk_id,
                    stream=stream,
                    token_hop_len=token_hop_len,
                ):
                    if not self.is_running:
                        break
                    self.audio_queue.put(audio)
            finally:
                self.audio_queue.put(None)  # 结束标记
        
        self.processing_thread = threading.Thread(target=process_audio, daemon=True)
        self.processing_thread.start()
    
    def get_audio_stream(self) -> Generator[torch.Tensor, None, None]:
        """
        获取音频流
        
        Yields:
            torch.Tensor: 音频数据块
        """
        while True:
            audio = self.audio_queue.get()
            if audio is None:  # 结束标记
                break
            yield audio
    
    def stop(self):
        """停止流式处理"""
        self.is_running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=5)

