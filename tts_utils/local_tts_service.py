"""
本地 TTS 服务模块

使用 CosyVoice2/CosyVoice3 本地模型进行语音合成
"""
import asyncio
import base64
import logging
import uuid
import os
from typing import AsyncGenerator, Optional, Dict
from pathlib import Path
import sys

# 添加 tts_modules 到 Python 路径
_tts_modules_path = Path(__file__).parent.parent / "tts_modules"
if str(_tts_modules_path) not in sys.path:
    sys.path.insert(0, str(_tts_modules_path))

import torch
import numpy as np

from llm_utils.config import config
from models.tts import AudioChunk, SentenceBuffer

logger = logging.getLogger(__name__)


def _get_gpu_memory():
    """获取当前GPU显存使用情况（GB）"""
    try:
        import torch
        if torch.cuda.is_available():
            # 获取当前GPU的属性
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            allocated = torch.cuda.memory_allocated(0) / 1024**3
            reserved = torch.cuda.memory_reserved(0) / 1024**3
            free = total - reserved

            return f"总计: {total:.1f}GB | 已用: {allocated:.2f}GB | 可用: {free:.1f}GB"
        else:
            return "GPU不可用"
    except Exception as e:
        return f"错误: {e}"


class LocalTTSService:
    """本地 TTS 服务类（使用 CosyVoice2/CosyVoice3 模型）"""

    def __init__(
        self,
        model_dir: Optional[str] = None,
        model_type: str = "auto",
        spk_id: str = "girl_zh",
        enabled: bool = True,
        **model_kwargs
    ):
        """
        初始化本地 TTS 服务

        Args:
            model_dir: 模型目录路径（从配置读取）
            model_type: 模型类型 ("auto", "cosyvoice2", "cosyvoice3")
            spk_id: 默认说话人ID
            enabled: 是否启用
            **model_kwargs: 其他模型参数
        """
        # 检查 MOCK_TTS 环境变量
        mock_tts_str = os.getenv("MOCK_TTS", "false").lower()
        self.mock_tts = mock_tts_str in ("true", "1", "yes", "on")
        
        if self.mock_tts:
            logger.info("MOCK_TTS 已启用，将返回假的音频数据块")
            self.model = None
            self.enabled = enabled
            self.sample_rate = 24000  # 默认采样率
            return
        
        # 直接从 cosyvoice2 包导入（避免模块代理冲突）
        import cosyvoice2.tts_service as cosyvoice2_module
        CosyVoiceTTSService = cosyvoice2_module.TTSService

        if model_dir is None:
            model_dir = config.get("tts.local_model_dir")

        # 处理字符串 "null" 或空字符串的情况
        if model_dir is None or model_dir == "null" or model_dir == "":
            raise ValueError("TTS_LOCAL_MODEL_DIR 未配置，请设置环境变量 TTS_LOCAL_MODEL_DIR 或配置 config.yaml 中的 tts.local_model_dir")

        # 检查模型目录是否存在
        model_path = Path(model_dir)
        if not model_path.exists():
            raise FileNotFoundError(
                f"TTS_LOCAL_MODEL_DIR 指定的目录不存在: {model_dir}。"
                f"请确保模型目录路径正确，或设置正确的 TTS_LOCAL_MODEL_DIR 环境变量。"
            )
        if not model_path.is_dir():
            raise NotADirectoryError(
                f"TTS_LOCAL_MODEL_DIR 指定的路径不是目录: {model_dir}。"
                f"请确保路径指向一个有效的目录。"
            )

        try:
            # 方案C优化：从配置读取加速参数
            fp16 = config.get("tts.acceleration.fp16", "true").lower() in ("true", "1", "yes")
            load_trt = config.get("tts.acceleration.tensorrt", "true").lower() in ("true", "1", "yes")
            trt_concurrent = int(config.get("tts.acceleration.tensorrt_concurrent", 4))
            load_vllm = config.get("tts.acceleration.vllm", "false").lower() in ("true", "1", "yes")

            logger.info(
                f"TTS加速配置: fp16={fp16}, tensorrt={load_trt}, "
                f"trt_concurrent={trt_concurrent}, vllm={load_vllm}"
            )

            # 清理GPU缓存，确保显存统计准确
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            # 打印加载前的GPU显存使用
            logger.info(f"📊 加载TTS模型前显存: {_get_gpu_memory()}")

            # 初始化 CosyVoice TTS 服务（启用加速）
            self.model = CosyVoiceTTSService(
                model_dir=model_dir,
                model_type=model_type,
                spk_id=spk_id,
                fp16=fp16,
                load_trt=load_trt,
                trt_concurrent=trt_concurrent,
                load_vllm=load_vllm,
                **model_kwargs
            )
            self.enabled = enabled
            self.sample_rate = self.model.sample_rate

            # 同步GPU并打印加载后的显存使用
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            logger.info(f"📊 加载TTS模型后显存: {_get_gpu_memory()}")

            logger.info(
                f"本地 TTS 服务初始化成功: model_dir={model_dir}, spk_id={spk_id}, "
                f"加速=FP16({fp16})+TensorRT({load_trt})"
            )
        except Exception as e:
            logger.error(f"本地 TTS 服务初始化失败: {e}", exc_info=True)
            self.model = None
            self.enabled = False

    def list_speakers(self):
        """列出所有可用的说话人ID"""
        if self.model:
            return self.model.list_speakers()
        return []

    def _torch_to_bytes(self, audio_tensor: torch.Tensor, format: str = "pcm") -> bytes:
        """
        将 PyTorch tensor 转换为音频字节数据

        Args:
            audio_tensor: 音频张量，shape 为 (1, samples) 或 (samples,)
            format: 音频格式

        Returns:
            音频二进制数据
        """
        # 转换为 numpy 数组
        if isinstance(audio_tensor, torch.Tensor):
            audio_array = audio_tensor.cpu().numpy()
        else:
            audio_array = audio_tensor

        # 如果是 (1, samples) 转换为 (samples,)
        if len(audio_array.shape) > 1 and audio_array.shape[0] == 1:
            audio_array = audio_array[0]

        # 转换为 int16 PCM
        if audio_array.dtype == np.float32 or audio_array.dtype == np.float64:
            # 假设范围是 [-1, 1]
            audio_array = (audio_array * 32767).astype(np.int16)

        return audio_array.tobytes()
    
    def _generate_mock_audio(self, text_length: int, sample_rate: int = 24000, duration_seconds: float = None) -> bytes:
        """
        生成假的音频数据块
        
        Args:
            text_length: 文本长度（用于估算音频时长）
            sample_rate: 采样率
            duration_seconds: 音频时长（秒），如果为None则根据文本长度估算
            
        Returns:
            假的音频数据（PCM int16格式）
        """
        # 如果未指定时长，根据文本长度估算（假设每个字符约0.1秒）
        if duration_seconds is None:
            duration_seconds = max(0.5, text_length * 0.1)
        
        # 生成采样点数
        num_samples = int(sample_rate * duration_seconds)
        
        # 生成简单的正弦波作为假的音频数据（440Hz，A4音符）
        t = np.linspace(0, duration_seconds, num_samples, False)
        frequency = 440.0  # A4音符
        audio_float = np.sin(2 * np.pi * frequency * t) * 0.3  # 降低音量
        
        # 转换为 int16 PCM 格式
        audio_int16 = (audio_float * 32767).astype(np.int16)
        
        return audio_int16.tobytes()

    async def synthesize_stream(
        self,
        text_stream: AsyncGenerator[str, None],
        language: str = "zh",
        request_id: Optional[str] = None,
        format: str = "pcm",
        sample_rate: int = 24000,
        voice: Optional[str] = None
    ) -> AsyncGenerator[AudioChunk, None]:
        """
        流式 TTS 合成

        Args:
            text_stream: 文本流
            language: 语言代码
            request_id: 请求ID
            format: 音频格式
            sample_rate: 采样率
            voice: 语音ID

        Yields:
            AudioChunk: 音频块
        """
        if not self.enabled:
            logger.warning("本地 TTS 服务未启用")
            return

        if request_id is None:
            request_id = f"local_tts_{uuid.uuid4().hex[:8]}"

        # 如果启用 mock 模式，生成假的音频数据
        if self.mock_tts:
            logger.info(f"使用 MOCK_TTS 模式生成假的音频数据: request_id={request_id}")
            
            # 收集所有文本
            full_text = ""
            async for text_token in text_stream:
                full_text += text_token
            
            if not full_text:
                return
            
            # 将文本分割成句子（简单分割）
            sentences = []
            current_sentence = ""
            for char in full_text:
                current_sentence += char
                if char in ['。', '.', '！', '!', '？', '?', '\n']:
                    if current_sentence.strip():
                        sentences.append(current_sentence.strip())
                    current_sentence = ""
            
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
            
            # 如果没有句子，至少生成一个块
            if not sentences:
                sentences = [full_text]
            
            # 为每个句子生成假的音频块
            chunk_counter = 0
            for idx, sentence in enumerate(sentences):
                chunk_counter += 1
                chunk_id = f"{request_id}_chunk_{chunk_counter}"
                
                # 生成假的音频数据
                mock_audio = self._generate_mock_audio(
                    text_length=len(sentence),
                    sample_rate=sample_rate
                )
                
                yield AudioChunk(
                    chunk_id=chunk_id,
                    text=sentence,
                    audio_data=mock_audio,
                    format=format,
                    is_final=(idx == len(sentences) - 1),
                    timestamp=int(asyncio.get_event_loop().time() * 1000),
                    metadata={
                        "sample_rate": sample_rate,
                        "mock": True
                    }
                )
            
            logger.info(f"MOCK_TTS 合成完成: request_id={request_id}, chunks={chunk_counter}")
            return

        if self.model is None:
            logger.warning("本地 TTS 模型未初始化")
            return

        logger.info(f"开始本地 TTS 合成: request_id={request_id}")

        # 从配置文件读取流式合成参数（确保类型转换）
        min_length = int(config.get("tts.streaming.min_length", 5))
        max_length = int(config.get("tts.streaming.max_length", 200))
        max_wait_time = float(config.get("tts.streaming.max_wait_time", 1.0))
        token_hop_len = int(config.get("tts.streaming.token_hop_len", 20))
        mel_cache_len = int(config.get("tts.streaming.mel_cache_len", 6))

        logger.debug(
            f"TTS流式合成参数: min_length={min_length}, max_length={max_length}, "
            f"max_wait_time={max_wait_time}, token_hop_len={token_hop_len}, "
            f"mel_cache_len={mel_cache_len}"
        )

        # 创建句子缓冲区（使用配置文件参数）
        sentence_buffer = SentenceBuffer(
            min_length=min_length,
            max_length=max_length,
            max_wait_time=max_wait_time
        )

        chunk_counter = 0

        try:
            # 流式处理：直接传入生成器，实现真正的流式处理
            # 现在CosyVoice的inference_sft_chunked支持生成器，不需要先收集所有文本

            # 使用流式合成
            if hasattr(self.model, 'synthesize_streaming'):
                # 优化：使用asyncio.Queue替代threading.Queue（减少线程切换开销）
                # 但由于TTS模型需要同步生成器，仍需要桥接
                import queue
                import threading
                text_queue = queue.Queue()  # 仍使用threading.Queue（因为需要同步生成器）
                stream_done = threading.Event()
                
                # 优化：导入动态超时工具
                from tts_utils.tts_optimization_utils import AdaptiveTimeout

                # 优化：维护文本到音频块的映射（解决文本信息丢失问题）
                sentence_audio_map: Dict[int, str] = {}
                sentence_counter = 0
                
                async def async_text_collector():
                    """
                    异步收集文本并放入队列
                    
                    优化：
                    - 维护文本映射，保留文本信息
                    - 每个句子分配唯一ID
                    """
                    nonlocal sentence_counter
                    try:
                        token_count = 0
                        async for text_token in text_stream:
                            token_count += 1
                            logger.debug(f"[TTS_DEBUG] 收到token#{token_count}: '{text_token}' (len={len(text_token)})")
                            complete_sentences = sentence_buffer.add_text(text_token)
                            logger.debug(f"[TTS_DEBUG] Buffer: '{sentence_buffer.get_pending_text()}' (len={len(sentence_buffer.get_pending_text())}), 句子数={len(complete_sentences)}")
                            
                            # 如果有完整句子，立即放入队列（优化：保留文本信息）
                            for sentence in complete_sentences:
                                sentence_counter += 1
                                sentence_key = sentence_counter
                                sentence_audio_map[sentence_key] = sentence  # ✅ 保存文本映射
                                logger.debug(f"[TTS_DEBUG] -> 放入队列 #{sentence_key}: '{sentence}'")
                                text_queue.put((sentence_key, sentence))  # ✅ 传递(sentence_key, sentence)元组

                        # 处理剩余文本
                        remaining_text = sentence_buffer.flush()
                        if remaining_text:
                            sentence_counter += 1
                            sentence_key = sentence_counter
                            sentence_audio_map[sentence_key] = remaining_text
                            text_queue.put((sentence_key, remaining_text))
                    finally:
                        stream_done.set()
                        text_queue.put(None)  # 结束信号

                # 启动异步收集任务
                collector_task = asyncio.create_task(async_text_collector())

                def text_chunk_generator():
                    """
                    同步生成器，从队列中获取文本块
                    
                    优化：
                    - 动态超时调整（根据数据流自适应）
                    - 提取文本内容（从元组中）
                    """
                    # 优化：使用自适应超时
                    adaptive_timeout = AdaptiveTimeout(
                        initial=0.1,
                        min_timeout=0.01,
                        max_timeout=0.3
                    )
                    
                    chunk_count = 0
                    all_chunks = []  # 收集所有chunk
                    while True:
                        try:
                            # 优化：使用动态超时
                            timeout = adaptive_timeout.get_timeout()
                            item = text_queue.get(timeout=timeout)
                            
                            if item is None:  # 结束信号
                                logger.info(f"[TTS_DEBUG] text_chunk_generator 收到结束信号，总共收到 {len(all_chunks)} 个chunk")
                                break
                            
                            # 优化：提取文本内容（如果是元组）
                            if isinstance(item, tuple):
                                sentence_key, sentence_text = item
                                chunk = sentence_text
                            else:
                                chunk = item
                            
                            chunk_count += 1
                            all_chunks.append(chunk)
                            adaptive_timeout.adjust(has_data=True)  # 有数据，减小超时
                            logger.debug(f"[TTS_DEBUG] text_chunk_generator 收到chunk#{chunk_count}: '{chunk[:30]}...'")
                            yield chunk
                        except queue.Empty:
                            # 超时，调整超时时间
                            adaptive_timeout.adjust(has_data=False)  # 无数据，增大超时
                            
                            # 检查是否已经结束
                            if stream_done.is_set() and text_queue.empty():
                                logger.info(f"[TTS_DEBUG] text_chunk_generator 超时退出 (stream_done={stream_done.is_set()}, queue_empty={text_queue.empty()})")
                                break
                            # 继续循环，等待下一个chunk
                            continue
                    logger.info(f"[TTS_DEBUG] text_chunk_generator 完成，总计yield了 {chunk_count} 个chunk")

                # 使用流式API，直接传入生成器
                streaming_kwargs = {
                    'text_chunks': text_chunk_generator(),  # 传入生成器，实现真正的流式处理
                    'spk_id': voice,
                    'stream': True,
                    'token_hop_len': token_hop_len,  # 从配置文件读取
                }
                # 只有CosyVoice2支持mel_cache_len参数
                if hasattr(self.model.model, 'mel_cache_len'):
                    streaming_kwargs['mel_cache_len'] = mel_cache_len  # 从配置文件读取

                # 使用迭代器来保持流式处理的优势
                # 现在CosyVoice可以在收到第一个完整句子后立即开始处理
                audio_iter = self.model.synthesize_streaming(**streaming_kwargs)
                
                # 优化：维护当前处理的文本（解决文本信息丢失问题）
                # 从sentence_audio_map中获取实际文本，而不是使用占位符
                current_sentence_key = None
                current_sentence_text = None
                
                # 尝试获取第一个句子（如果有）
                try:
                    # 从队列中获取第一个句子（不阻塞）
                    if not text_queue.empty():
                        first_item = text_queue.get_nowait()
                        if first_item and first_item is not None and isinstance(first_item, tuple):
                            current_sentence_key, current_sentence_text = first_item
                            # 重新放回队列（因为text_chunk_generator会取）
                            text_queue.put(first_item)
                except queue.Empty:
                    pass
                
                # 辅助函数：在线程池中执行同步的next()调用，避免阻塞事件循环
                # 注意：StopIteration在asyncio协程中不能直接raise，需要使用自定义异常
                class IteratorExhausted(Exception):
                    """标记迭代器已耗尽的异常（替代StopIteration）"""
                    pass
                
                # 使用特殊哨兵值来标记迭代器耗尽
                _SENTINEL = object()
                
                def _next_wrapper(iterator):
                    """包装next()调用，将StopIteration转换为特殊值"""
                    try:
                        return next(iterator)
                    except StopIteration:
                        # StopIteration不能直接传播到Future，返回哨兵值
                        return _SENTINEL
                
                async def safe_next(iterator):
                    """在线程池中安全地调用next()，避免阻塞事件循环"""
                    loop = asyncio.get_event_loop()
                    # 使用run_in_executor在线程池中执行同步的next()调用
                    # 这样可以避免阻塞事件循环，让文本收集任务能够继续运行
                    result = await loop.run_in_executor(None, _next_wrapper, iterator)
                    if result is _SENTINEL:
                        # 迭代器已耗尽，raise自定义异常（在调用方会被捕获）
                        raise IteratorExhausted()
                    return result
                
                try:
                    # 优化：减小初始等待时间（0.1秒 → 0.05秒）
                    await asyncio.sleep(0.05)
                    
                    # 获取第一个音频tensor（在线程池中执行，避免阻塞）
                    current_audio = await safe_next(audio_iter)
                    
                    # 优化：维护句子索引，用于追踪当前处理的文本
                    sentence_index = 0
                    sentence_keys = sorted(sentence_audio_map.keys()) if sentence_audio_map else []
                    
                    while True:
                        # 尝试获取下一个音频tensor来判断是否是最后一个
                        try:
                            next_audio = await safe_next(audio_iter)
                            # 有下一个，yield当前的（不是最后一个）
                            chunk_counter += 1
                            chunk_id = f"{request_id}_chunk_{chunk_counter}"
                            audio_bytes = self._torch_to_bytes(current_audio, format)
                            
                            # 优化：使用实际文本，不是占位符
                            # 根据句子索引获取对应的文本
                            if sentence_index < len(sentence_keys):
                                sentence_key = sentence_keys[sentence_index]
                                actual_text = sentence_audio_map.get(sentence_key, "处理中...")
                            else:
                                actual_text = current_sentence_text or "处理中..."
                            
                            yield AudioChunk(
                                chunk_id=chunk_id,
                                text=actual_text,  # ✅ 使用实际文本
                                audio_data=audio_bytes,
                                format=format,
                                is_final=False,
                                timestamp=int(asyncio.get_event_loop().time() * 1000),
                                metadata={
                                    "sample_rate": self.sample_rate,
                                    "local_model": True,
                                    "streaming": True,
                                    "chunk_index": chunk_counter,
                                    "sentence_key": sentence_keys[sentence_index] if sentence_index < len(sentence_keys) else None
                                }
                            )
                            # 更新当前tensor
                            current_audio = next_audio
                            # 移动到下一个句子（每个音频块对应一个句子）
                            sentence_index += 1
                        except IteratorExhausted:
                            # 没有下一个，当前是最后一个
                            chunk_counter += 1
                            chunk_id = f"{request_id}_chunk_{chunk_counter}"
                            audio_bytes = self._torch_to_bytes(current_audio, format)
                            
                            # 优化：使用实际文本，不是占位符
                            if sentence_index < len(sentence_keys):
                                sentence_key = sentence_keys[sentence_index]
                                actual_text = sentence_audio_map.get(sentence_key, "处理中...")
                            else:
                                actual_text = current_sentence_text or "处理中..."
                            
                            yield AudioChunk(
                                chunk_id=chunk_id,
                                text=actual_text,  # ✅ 使用实际文本
                                audio_data=audio_bytes,
                                format=format,
                                is_final=True,
                                timestamp=int(asyncio.get_event_loop().time() * 1000),
                                metadata={
                                    "sample_rate": self.sample_rate,
                                    "local_model": True,
                                    "streaming": True,
                                    "chunk_index": chunk_counter,
                                    "sentence_key": sentence_keys[sentence_index] if sentence_index < len(sentence_keys) else None
                                }
                            )
                            break
                except IteratorExhausted:
                    # 如果没有生成任何chunk
                    pass
                finally:
                    # 确保收集任务完成
                    await collector_task
            else:
                # 如果没有synthesize_streaming方法，回退到批量处理
                # 收集所有文本块
                text_chunks = []
                async for text_token in text_stream:
                    complete_sentences = sentence_buffer.add_text(text_token)
                    text_chunks.extend(complete_sentences)
                
                remaining_text = sentence_buffer.flush()
                if remaining_text:
                    text_chunks.append(remaining_text)
                
                # 逐个处理文本块
                for idx, text_chunk in enumerate(text_chunks):
                    for audio_tensor in self.model.synthesize(
                        text=text_chunk,
                        spk_id=voice,
                        stream=False
                    ):
                        chunk_counter += 1
                        chunk_id = f"{request_id}_chunk_{chunk_counter}"

                        audio_bytes = self._torch_to_bytes(audio_tensor, format)

                        yield AudioChunk(
                            chunk_id=chunk_id,
                            text=text_chunk,
                            audio_data=audio_bytes,
                            format=format,
                            is_final=(idx == len(text_chunks) - 1),
                            timestamp=int(asyncio.get_event_loop().time() * 1000),
                            metadata={
                                "sample_rate": self.sample_rate,
                                "local_model": True
                            }
                        )
                        break  # 每个 chunk 只取第一个结果

            logger.info(f"本地 TTS 合成完成: request_id={request_id}, chunks={chunk_counter}")

        except Exception as e:
            logger.error(f"本地 TTS 合成失败: {e}", exc_info=True)
            # 优化：添加错误恢复机制（重试和降级）
            from core.retry import retry_async, RetryConfig
            
            # 如果是一次性错误，尝试重试
            if chunk_counter == 0:  # 还没有生成任何chunk
                logger.warning(f"TTS合成失败，尝试重试: request_id={request_id}")
                try:
                    # 重试一次（使用批量模式作为降级）
                    remaining_text = sentence_buffer.flush() if 'sentence_buffer' in locals() else ""
                    if remaining_text:
                        logger.info(f"使用批量模式作为降级: request_id={request_id}")
                        audio_data = await self.synthesize_batch(
                            text=remaining_text,
                            language=language,
                            request_id=request_id,
                            format=format,
                            sample_rate=sample_rate,
                            voice=voice
                        )
                        if audio_data:
                            yield AudioChunk(
                                chunk_id=f"{request_id}_chunk_fallback",
                                text=remaining_text,
                                audio_data=audio_data,
                                format=format,
                                is_final=True,
                                timestamp=int(asyncio.get_event_loop().time() * 1000),
                                metadata={
                                    "sample_rate": self.sample_rate,
                                    "local_model": True,
                                    "fallback": True
                                }
                            )
                            logger.info(f"降级模式成功: request_id={request_id}")
                            return
                except Exception as retry_error:
                    logger.error(f"重试也失败: {retry_error}", exc_info=True)
            
            # 如果重试失败，抛出异常
            raise

    async def synthesize_batch(
        self,
        text: str,
        language: str = "zh",
        request_id: Optional[str] = None,
        format: str = "pcm",
        sample_rate: int = 24000,
        voice: Optional[str] = None
    ) -> bytes:
        """
        批量 TTS 合成

        Args:
            text: 完整文本
            language: 语言代码
            request_id: 请求ID
            format: 音频格式
            sample_rate: 采样率
            voice: 语音ID

        Returns:
            完整的音频数据
        """
        if not self.enabled:
            logger.warning("本地 TTS 服务未启用")
            return b""

        if request_id is None:
            request_id = f"local_tts_{uuid.uuid4().hex[:8]}"

        # 如果启用 mock 模式，生成假的音频数据
        if self.mock_tts:
            logger.info(f"使用 MOCK_TTS 模式生成假的音频数据: request_id={request_id}, text_length={len(text)}")
            mock_audio = self._generate_mock_audio(
                text_length=len(text),
                sample_rate=sample_rate
            )
            return mock_audio

        if self.model is None:
            logger.warning("本地 TTS 模型未初始化")
            return b""

        logger.info(f"批量本地 TTS 合成: request_id={request_id}, text_length={len(text)}")

        try:
            # 将文本转换为流
            async def text_stream():
                yield text

            # 收集所有音频块
            audio_chunks = []
            async for audio_chunk in self.synthesize_stream(
                text_stream=text_stream(),
                language=language,
                request_id=request_id,
                format=format,
                sample_rate=sample_rate,
                voice=voice
            ):
                audio_chunks.append(audio_chunk.audio_data)

            # 合并音频块
            return b"".join(audio_chunks)

        except Exception as e:
            logger.error(f"批量本地 TTS 合成失败: {e}", exc_info=True)
            raise
