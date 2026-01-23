"""
CosyVoice2 TTS 服务
高效流式语音合成服务，专为新闻播报场景设计
"""
import os
import sys
import logging
import asyncio
import base64
import time
import uuid as uuid_module
from typing import AsyncGenerator, Optional, List, Dict, Tuple, Tuple
from threading import Lock
from pathlib import Path
from collections import deque

# 添加CosyVoice2模块到路径
# 优先使用项目内的 CosyVoice2_IN 目录
_possible_paths = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'CosyVoice2_IN')),  # 项目内的 CosyVoice2_IN（优先）
]

for _path in _possible_paths:
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

import torch
import numpy as np

try:
    from cosyvoice.cli.cosyvoice import CosyVoice2
    COSYVOICE_AVAILABLE = True
except ImportError:
    COSYVOICE_AVAILABLE = False
    CosyVoice2 = None

from models.tts import SentenceBuffer
from llm_utils.config import config

logger = logging.getLogger(__name__)

# 抑制CosyVoice内部日志（如果可用）
if COSYVOICE_AVAILABLE:
    try:
        from cosyvoice.utils import file_utils as cosyvoice_file_utils
        cosyvoice_file_utils.logging.setLevel(logging.WARNING)
    except (ImportError, AttributeError) as e:
        logger.debug(f"无法设置CosyVoice日志级别: {e}")


class CosyVoice2TTS:
    """
    CosyVoice2 流式TTS服务

    特点：
    1. 模型单例加载，避免重复初始化
    2. 支持文本chunk流式输入
    3. 支持音频流式输出
    4. 智能句子缓冲和分块
    5. 线程安全的异步接口
    """

    _instance = None
    _lock = Lock()
    _model_lock = Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化TTS服务"""
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.model: Optional[CosyVoice2] = None
        self.sample_rate = 22050
        self.spk_id = "zh_girl"
        self.device = None
        self._model_loaded = False

        # TTS 参数
        tts_config = config.get("tts", {})
        self.model_path = tts_config.get("local_model_dir", "")
        self.spk_id = tts_config.get("default_spk_id", "zh_girl")
        self.use_fp16 = tts_config.get("fp16", False)
        self.use_tensorrt = tts_config.get("tensorrt", False)
        self.seed = tts_config.get("seed", 0)  # 随机种子

        # 流式参数
        self.stream_mode = True
        self.token_hop_len = tts_config.get("token_hop_len", 25)  # ~1秒音频
        self.mel_cache_len = tts_config.get("mel_cache_len", 6)  # 边界平滑

        # 句子缓冲区配置（从 tts.buffer.* 读取）
        buffer_config = tts_config.get("buffer", {})
        self.min_length = buffer_config.get("min_length", 15)
        self.max_length = buffer_config.get("max_length", 200)
        self.max_wait_time = buffer_config.get("max_wait_time", 1.0)

        logger.info(f"CosyVoice2TTS 初始化: model_path={self.model_path}, spk_id={self.spk_id}, "
                   f"fp16={self.use_fp16}, stream_mode={self.stream_mode}, "
                   f"token_hop_len={self.token_hop_len}, mel_cache_len={self.mel_cache_len}, "
                   f"seed={self.seed}")

        # Session 管理：为每个 request_id 维护独立的 UUID 和状态
        self._session_lock = Lock()
        self._sessions: Dict[str, Dict] = {}  # request_id -> {uuid, chunk_count, created_at}
        self._session_timeout = 300  # session 超时时间（秒）
        
        # 方案C：队列机制 - 为每个 request_id 维护文本队列和处理任务
        self._text_queues: Dict[str, asyncio.Queue] = {}  # request_id -> Queue[Tuple[text, is_last, future]]
        self._processing_tasks: Dict[str, asyncio.Task] = {}  # request_id -> Task
        self._queue_lock = asyncio.Lock()  # 异步锁，用于保护队列字典

        self._initialized = True

    def _get_or_create_session(self, request_id: Optional[str]) -> Optional[str]:
        """
        获取或创建 session UUID
        
        Args:
            request_id: 请求ID，如果为 None 则不使用 session（每次生成新 UUID）
        
        Returns:
            UUID 字符串，如果 request_id 为 None 则返回 None
        """
        if request_id is None:
            return None
        
        with self._session_lock:
            # 清理超时的 session
            current_time = time.time()
            expired_sessions = [
                rid for rid, session in self._sessions.items()
                if current_time - session['created_at'] > self._session_timeout
            ]
            for rid in expired_sessions:
                del self._sessions[rid]
                logger.debug(f"清理超时 session: request_id={rid}")
            
            # 获取或创建 session
            if request_id not in self._sessions:
                session_uuid = str(uuid_module.uuid4())
                self._sessions[request_id] = {
                    'uuid': session_uuid,
                    'chunk_count': 0,
                    'created_at': current_time
                }
                logger.debug(f"创建新 session: request_id={request_id}, uuid={session_uuid}")
            else:
                self._sessions[request_id]['chunk_count'] += 1
                self._sessions[request_id]['created_at'] = current_time  # 更新最后使用时间
                logger.debug(f"复用 session: request_id={request_id}, uuid={self._sessions[request_id]['uuid']}, chunk_count={self._sessions[request_id]['chunk_count']}")
            
            return self._sessions[request_id]['uuid']
    
    def _release_session(self, request_id: Optional[str], is_final: bool = False):
        """
        释放 session
        
        Args:
            request_id: 请求ID
            is_final: 是否为最后一个 chunk
        """
        if request_id is None:
            return
        
        with self._session_lock:
            if request_id in self._sessions:
                if is_final:
                    # 最后一个 chunk，清理 session
                    del self._sessions[request_id]
                    logger.debug(f"释放 session: request_id={request_id}")
                # 否则保留 session 供后续 chunk 使用

    async def _process_text_queue(self, request_id: str, spk_id: str):
        """
        方案C：后台处理任务 - 从队列读取所有文本chunk，合并后一次性调用 inference_sft_chunked
        
        Args:
            request_id: 请求ID
            spk_id: 说话人ID
        """
        if not self._model_loaded:
            self.load_model()
        
        # 获取或创建 session UUID
        session_uuid = self._get_or_create_session(request_id)
        
        try:
            # 累积所有文本 chunk
            text_chunks = []
            futures = []  # 存储每个 chunk 对应的 Future
            
            logger.info(f"[方案C] 开始处理队列: request_id={request_id}, session_uuid={session_uuid}")
            
            # 从队列读取所有 chunk
            while True:
                item = await self._text_queues[request_id].get()
                if item is None:  # 结束信号（如果最后一个chunk已经处理，这里会收到None）
                    logger.debug(f"[方案C] 收到结束信号，已累积 {len(text_chunks)} 个chunks")
                    break
                
                text, is_last, future = item
                text_chunks.append(text)
                futures.append(future)
                
                logger.debug(f"[方案C] 收到 chunk {len(text_chunks)}: {len(text)} 字符, is_last={is_last}")
                
                if is_last:
                    # 收到最后一个chunk，开始处理
                    logger.debug(f"[方案C] 收到最后一个chunk，开始处理 {len(text_chunks)} 个chunks")
                    break
            
            if not text_chunks:
                logger.warning(f"[方案C] 没有文本需要处理: request_id={request_id}")
                # 设置所有 Future 为空结果
                for future in futures:
                    if not future.done():
                        future.set_result(b"")
                return
            
            logger.info(f"[方案C] 开始合并合成: {len(text_chunks)} 个chunks, 总长度={sum(len(t) for t in text_chunks)} 字符")
            
            # 一次性调用 inference_sft_chunked，合并所有 chunk
            loop = asyncio.get_event_loop()
            
            def run_synthesis():
                audio_chunks = []
                # 使用 inference_sft_chunked 方法，将所有 chunk 合并处理
                # 这样所有 chunk 共享同一个 UUID 和 KV-cache，保证音色一致性
                for result in self.model.inference_sft_chunked(
                    text_chunks=text_chunks,  # 所有 chunk 合并传入
                    spk_id=spk_id,
                    stream=False,  # 非流式模式，一次性返回完整音频
                    speed=1.0,
                    text_frontend=True
                ):
                    audio = result["tts_speech"]
                    if isinstance(audio, torch.Tensor):
                        audio = audio.squeeze().cpu().numpy()
                    
                    if audio.dtype == np.float32 or audio.dtype == np.float64:
                        audio = (audio * 32767).astype(np.int16)
                    
                    audio_chunks.append(audio)
                
                return b"".join(chunk.tobytes() for chunk in audio_chunks)
            
            # 在线程池中执行合成
            merged_audio = await loop.run_in_executor(None, run_synthesis)
            
            logger.info(f"[方案C] 合并合成完成: {len(merged_audio)} 字节, {len(merged_audio)/2/self.sample_rate:.2f}秒")
            
            # 将合并后的音频按文本长度比例分割
            # 计算每个 chunk 的文本长度比例
            chunk_count = len(text_chunks)
            if chunk_count > 0 and len(futures) == chunk_count:
                total_text_len = sum(len(t) for t in text_chunks)
                if total_text_len > 0:
                    # 按文本长度比例分割音频
                    # 16-bit PCM = 2 bytes per sample，确保分割位置是2的倍数
                    current_pos = 0
                    for i, (text_chunk, future) in enumerate(zip(text_chunks, futures)):
                        # 计算这个 chunk 的文本长度比例
                        text_ratio = len(text_chunk) / total_text_len
                        # 计算对应的音频长度（字节，16-bit PCM = 2 bytes per sample）
                        chunk_audio_bytes = int(len(merged_audio) * text_ratio)
                        # 确保分割位置是2的倍数（16-bit对齐）
                        chunk_audio_bytes = (chunk_audio_bytes // 2) * 2
                        
                        # 确保最后一个 chunk 包含所有剩余音频
                        if i == chunk_count - 1:
                            chunk_audio = merged_audio[current_pos:]
                        else:
                            chunk_audio = merged_audio[current_pos:current_pos + chunk_audio_bytes]
                            current_pos += chunk_audio_bytes
                        
                        if not future.done():
                            future.set_result(chunk_audio)
                            logger.debug(f"[方案C] 设置 chunk {i+1} 音频: {len(chunk_audio)} 字节 (文本长度={len(text_chunk)}, 比例={text_ratio:.3f})")
                else:
                    # 文本长度为0，平均分割（确保2字节对齐）
                    chunk_size = (len(merged_audio) // chunk_count // 2) * 2  # 对齐到2字节
                    for i, future in enumerate(futures):
                        if i < chunk_count - 1:
                            chunk_audio = merged_audio[i * chunk_size:(i + 1) * chunk_size]
                        else:
                            chunk_audio = merged_audio[i * chunk_size:]
                        if not future.done():
                            future.set_result(chunk_audio)
                            logger.debug(f"[方案C] 设置 chunk {i+1} 音频: {len(chunk_audio)} 字节 (平均分割)")
            else:
                logger.error(f"[方案C] chunks和futures数量不匹配: chunks={chunk_count}, futures={len(futures)}")
                # 设置所有 Future 为异常
                error = ValueError(f"chunks和futures数量不匹配: chunks={chunk_count}, futures={len(futures)}")
                for future in futures:
                    if not future.done():
                        future.set_exception(error)
            
            # 释放 session
            self._release_session(request_id, is_final=True)
            
        except Exception as e:
            logger.error(f"[方案C] 处理队列失败: request_id={request_id}, error={e}", exc_info=True)
            # 设置所有 Future 为异常（如果futures列表已初始化）
            if 'futures' in locals() and futures:
                for future in futures:
                    if not future.done():
                        future.set_exception(e)
            else:
                # 如果异常发生在futures初始化之前，需要从队列中获取所有future
                logger.warning(f"[方案C] 异常发生在futures初始化之前，尝试从队列获取所有future")
                try:
                    # 使用异步方式清理队列
                    while True:
                        try:
                            item = await asyncio.wait_for(self._text_queues[request_id].get(), timeout=0.1)
                            if item is not None:
                                _, _, future = item
                                if not future.done():
                                    future.set_exception(e)
                        except asyncio.TimeoutError:
                            # 队列为空，退出循环
                            break
                        except Exception as get_error:
                            logger.error(f"[方案C] 从队列获取item时出错: {get_error}", exc_info=True)
                            break
                except Exception as cleanup_error:
                    logger.error(f"[方案C] 清理队列时出错: {cleanup_error}", exc_info=True)
        finally:
            # 清理队列和任务
            async with self._queue_lock:
                if request_id in self._text_queues:
                    del self._text_queues[request_id]
                if request_id in self._processing_tasks:
                    del self._processing_tasks[request_id]

    def load_model(self):
        """加载TTS模型（线程安全）"""
        if self._model_loaded:
            return

        with self._model_lock:
            if self._model_loaded:
                return

            # 如果导入失败，再次尝试导入（路径可能已添加）
            global COSYVOICE_AVAILABLE, CosyVoice2
            if not COSYVOICE_AVAILABLE:
                # 再次尝试添加可能的路径（优先使用项目内的 CosyVoice2_IN）
                _possible_paths = [
                    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'CosyVoice2_IN')),  # 项目内的 CosyVoice2_IN（优先）
                ]
                for _path in _possible_paths:
                    if os.path.exists(_path) and _path not in sys.path:
                        sys.path.insert(0, _path)
                        logger.info(f"已添加 CosyVoice2 路径: {_path}")
                
                try:
                    from cosyvoice.cli.cosyvoice import CosyVoice2
                    COSYVOICE_AVAILABLE = True
                    logger.info("✅ CosyVoice2 导入成功")
                except ImportError as e:
                    raise RuntimeError(f"CosyVoice2 未安装，请确保项目内有 CosyVoice2_IN 目录。错误: {e}")

            if not self.model_path or not os.path.exists(self.model_path):
                raise ValueError(f"模型路径不存在: {self.model_path}")

            try:
                logger.info(f"正在加载 CosyVoice2 模型: {self.model_path}")
                start_time = time.time()

                from cosyvoice.utils.common import set_all_random_seed
                set_all_random_seed(self.seed)

                # 检测设备
                if torch.cuda.is_available():
                    self.device = "cuda"
                    logger.info(f"使用 CUDA 设备: {torch.cuda.get_device_name(0)}")
                elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    self.device = "mps"
                    logger.info("使用 MPS 设备 (Apple Silicon)")
                else:
                    self.device = "cpu"
                    logger.info("使用 CPU 设备")

                # 初始化模型
                self.model = CosyVoice2(
                    self.model_path,
                    load_jit=False,
                    load_trt=self.use_tensorrt,
                    fp16=self.use_fp16 if self.device == "cuda" else False,
                )

                self.sample_rate = self.model.sample_rate

                # 验证说话人ID
                available_spks = self.model.list_available_spks()
                if self.spk_id not in available_spks:
                    logger.warning(f"说话人ID '{self.spk_id}' 不可用，使用默认说话人")
                    self.spk_id = available_spks[0] if available_spks else "zh_girl"

                load_time = time.time() - start_time
                logger.info(f"✅ CosyVoice2 模型加载完成 (耗时: {load_time:.2f}s)")
                logger.info(f"   采样率: {self.sample_rate}Hz")
                logger.info(f"   说话人: {self.spk_id}")
                logger.info(f"   可用说话人: {len(available_spks)} 个")

                self._model_loaded = True

            except Exception as e:
                logger.error(f"❌ 加载 CosyVoice2 模型失败: {e}", exc_info=True)
                raise

    def list_speakers(self) -> List[str]:
        """获取可用的说话人列表"""
        if not self._model_loaded:
            self.load_model()
        return self.model.list_available_spks()

    def set_speaker(self, spk_id: str):
        """设置说话人ID"""
        available = self.list_speakers()
        if spk_id not in available:
            raise ValueError(f"说话人ID '{spk_id}' 不可用，可用: {available}")
        self.spk_id = spk_id
        logger.info(f"说话人已切换为: {spk_id}")

    # async def synthesize_streaming(
    #     self,
    #     text_stream: AsyncGenerator[str, None],
    #     spk_id: Optional[str] = None
    # ) -> AsyncGenerator[bytes, None]:
    #     """
    #     流式语音合成

    #     Args:
    #         text_stream: 文本流生成器
    #         spk_id: 说话人ID（可选，默认使用配置的ID）

    #     Yields:
    #         PCM音频数据 (16-bit, mono, 22050Hz)
    #     """
    #     if not self._model_loaded:
    #         self.load_model()

    #     spk_id = spk_id or self.spk_id

    #     # 创建句子缓冲区
    #     buffer = SentenceBuffer(
    #         min_length=self.min_length,
    #         max_length=self.max_length,
    #         max_wait_time=self.max_wait_time
    #     )

    #     # 收集文本chunks
    #     text_chunks = []
    #     last_flush_time = time.time()

    #     try:
    #         # 第一阶段：收集文本chunk
    #         async for text in text_stream:
    #             if not text:
    #                 continue

    #             # 添加到缓冲区并检测完整句子
    #             sentences = buffer.add_text(text)

    #             # 输出完整句子
    #             for sentence in sentences:
    #                 text_chunks.append(sentence)
    #                 logger.debug(f"添加句子chunk: {sentence[:50]}...")
    #                 last_flush_time = time.time()

    #             # 检查超时
    #             if buffer.should_flush():
    #                 pending = buffer.flush()
    #                 if pending:
    #                     text_chunks.append(pending)
    #                     last_flush_time = time.time()

    #         # 第二阶段：处理剩余缓冲区
    #         remaining = buffer.flush()
    #         if remaining:
    #             text_chunks.append(remaining)

    #         if not text_chunks:
    #             logger.warning("没有文本需要合成")
    #             return

    #         logger.info(f"开始流式合成: {len(text_chunks)} 个文本chunks")

    #         # 第三阶段：流式语音合成
    #         loop = asyncio.get_event_loop()

    #         def run_synthesis():
    #             """在单独的线程中运行TTS"""
    #             try:
    #                 for result in self.model.inference_sft_chunked(
    #                     text_chunks=text_chunks,
    #                     spk_id=spk_id,
    #                     stream=self.stream_mode,
    #                     speed=1.0,
    #                     token_hop_len=self.token_hop_len,
    #                     mel_cache_len=self.mel_cache_len
    #                 ):
    #                     audio = result["tts_speech"]
    #                     if isinstance(audio, torch.Tensor):
    #                         audio = audio.squeeze().cpu().numpy()

    #                     # 转换为16-bit PCM
    #                     if audio.dtype == np.float32 or audio.dtype == np.float64:
    #                         audio = (audio * 32767).astype(np.int16)

    #                     yield audio.tobytes()

    #             except Exception as e:
    #                 logger.error(f"TTS合成失败: {e}", exc_info=True)
    #                 raise

    #         # 使用线程池执行CPU密集型任务
    #         for audio_chunk in await loop.run_in_executor(None, lambda: list(run_synthesis())):
    #             yield audio_chunk

    #         logger.info("流式合成完成")

    #     except Exception as e:
    #         logger.error(f"流式合成失败: {e}", exc_info=True)
    #         raise

    async def synthesize(
        self,
        text: str,
        spk_id: Optional[str] = None,
        request_id: Optional[str] = None,
        is_last_chunk: bool = False
    ) -> bytes:
        """
        非流式语音合成（方案C：使用队列机制，累积所有chunk后一次性处理）
        
        Args:
            text: 待合成文本
            spk_id: 说话人ID（可选，默认使用配置的ID）
            request_id: 请求ID，用于跨 chunk 的 session 管理，保证音色一致性
            is_last_chunk: 是否为最后一个 chunk，用于触发处理
        
        Returns:
            PCM音频数据
        """
        if not self._model_loaded:
            self.load_model()

        spk_id = spk_id or self.spk_id

        # 方案C：如果 request_id 为 None，使用原来的方式（单次处理）
        if request_id is None:
            logger.info(f"[方案C] request_id=None，使用单次处理模式: {len(text)} 字符")
            loop = asyncio.get_event_loop()
            
            def run_synthesis():
                audio_chunks = []
                for result in self.model.inference_sft_chunked(
                    text_chunks=[text],
                    spk_id=spk_id,
                    stream=False,
                    speed=1.0,
                    text_frontend=True
                ):
                    audio = result["tts_speech"]
                    if isinstance(audio, torch.Tensor):
                        audio = audio.squeeze().cpu().numpy()
                    if audio.dtype == np.float32 or audio.dtype == np.float64:
                        audio = (audio * 32767).astype(np.int16)
                    audio_chunks.append(audio)
                return b"".join(chunk.tobytes() for chunk in audio_chunks)
            
            audio_data = await loop.run_in_executor(None, run_synthesis)
            logger.info(f"合成完成: {len(audio_data)} 字节, {len(audio_data)/2/self.sample_rate:.2f}秒")
            return audio_data

        # 方案C：使用队列机制
        # 第一步：在锁内创建队列、放入文本、启动任务
        async with self._queue_lock:
            # 获取或创建队列
            if request_id not in self._text_queues:
                self._text_queues[request_id] = asyncio.Queue()
                logger.debug(f"[方案C] 创建新队列: request_id={request_id}")
            
            # 创建 Future 用于返回结果
            future = asyncio.Future()
            
            # 将文本放入队列
            await self._text_queues[request_id].put((text, is_last_chunk, future))
            logger.debug(f"[方案C] 文本入队: request_id={request_id}, len={len(text)}, is_last={is_last_chunk}")
            
            # 如果是第一个chunk，启动处理任务（后台持续运行）
            if request_id not in self._processing_tasks:
                task = asyncio.create_task(self._process_text_queue(request_id, spk_id))
                self._processing_tasks[request_id] = task
                logger.debug(f"[方案C] 启动处理任务: request_id={request_id}")
        
        # 第二步：释放锁后等待结果（避免死锁）
        # 注意：处理任务会在收到 is_last=True 的chunk后自动开始处理，不需要发送额外的结束信号
        try:
            audio_data = await future
            logger.info(f"[方案C] 合成完成: {len(audio_data)} 字节, {len(audio_data)/2/self.sample_rate:.2f}秒")
            return audio_data
        except Exception as e:
            logger.error(f"[方案C] 等待结果失败: request_id={request_id}, error={e}", exc_info=True)
            raise


# 全局TTS服务实例
_tts_service: Optional[CosyVoice2TTS] = None


def get_tts_service() -> CosyVoice2TTS:
    """获取TTS服务单例"""
    global _tts_service
    if _tts_service is None:
        _tts_service = CosyVoice2TTS()
    return _tts_service


async def initialize_tts():
    """初始化TTS服务（在应用启动时调用）"""
    global _tts_service
    if _tts_service is None:
        _tts_service = CosyVoice2TTS()

    try:
        _tts_service.load_model()
        logger.info("✅ TTS 服务初始化成功")
        return True
    except Exception as e:
        logger.error(f"❌ TTS 服务初始化失败: {e}")
        return False
