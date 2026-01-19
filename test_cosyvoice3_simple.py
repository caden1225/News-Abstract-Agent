"""
CosyVoice3 模型语音合成简单测试脚本

直接使用 CosyVoice3 模型进行文本转语音合成测试
"""
import os
import sys
import torch
import numpy as np
from scipy.io import wavfile
from pathlib import Path
from typing import Optional

# 添加 tts_modules 到 Python 路径
_tts_modules_path = Path(__file__).parent / "tts_modules"
if str(_tts_modules_path) not in sys.path:
    sys.path.insert(0, str(_tts_modules_path))

from cosyvoice2.cosyvoice.cli.cosyvoice import CosyVoice3


def test_cosyvoice3(
    model_dir: str,
    text: str = "你好，这是一个CosyVoice3模型的测试。",
    spk_id: Optional[str] = None,
    output_dir: str = "test_output",
    stream: bool = False,
    speed: float = 1.0,
    fp16: bool = False,
    load_trt: bool = False,
    load_vllm: bool = False,
):
    """
    测试 CosyVoice3 模型进行语音合成
    
    Args:
        model_dir: 模型目录路径（可以是本地路径或 ModelScope 路径）
        text: 要合成的文本
        spk_id: 说话人ID，如果为None则使用第一个可用说话人
        output_dir: 输出目录
        stream: 是否使用流式输出
        speed: 语速倍数
        fp16: 是否使用FP16精度
        load_trt: 是否加载TensorRT引擎
        load_vllm: 是否加载vLLM引擎
    """
    print("=" * 80)
    print("CosyVoice3 语音合成测试")
    print("=" * 80)
    print(f"模型目录: {model_dir}")
    print(f"文本: {text}")
    print(f"流式输出: {stream}")
    print(f"语速: {speed}x")
    print(f"FP16: {fp16}")
    print(f"TensorRT: {load_trt}")
    print(f"vLLM: {load_vllm}")
    print("-" * 80)
    
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # 初始化模型
    print("\n📦 正在加载 CosyVoice3 模型...")
    try:
        model = CosyVoice3(
            model_dir=model_dir,
            load_trt=load_trt,
            load_vllm=load_vllm,
            fp16=fp16,
            trt_concurrent=1
        )
        print(f"✅ 模型加载成功!")
        print(f"   采样率: {model.sample_rate} Hz")
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 列出可用的说话人
    print("\n🎤 可用的说话人:")
    available_spks = model.list_available_spks()
    for i, spk in enumerate(available_spks, 1):
        print(f"   {i}. {spk}")
    
    # 选择说话人
    if spk_id is None:
        if available_spks:
            spk_id = available_spks[0]
            print(f"\n使用默认说话人: {spk_id}")
        else:
            print("❌ 没有可用的说话人!")
            return
    elif spk_id not in available_spks:
        print(f"⚠️  说话人 '{spk_id}' 不存在，使用第一个可用说话人: {available_spks[0]}")
        spk_id = available_spks[0]
    else:
        print(f"\n使用说话人: {spk_id}")
    
    # 进行语音合成
    print("\n🎵 开始语音合成...")
    print("-" * 80)
    
    audio_chunks = []
    total_samples = 0
    
    try:
        import time
        start_time = time.time()
        
        for i, result in enumerate(model.inference_sft(
            tts_text=text,
            spk_id=spk_id,
            stream=stream,
            speed=speed
        )):
            audio_tensor = result['tts_speech']  # shape: (1, samples)
            audio_chunks.append(audio_tensor)
            total_samples += audio_tensor.shape[1]
            
            chunk_duration = audio_tensor.shape[1] / model.sample_rate
            print(f"  块 #{i+1}: {chunk_duration:.2f} 秒, 形状: {audio_tensor.shape}")
        
        synthesis_time = time.time() - start_time
        total_duration = total_samples / model.sample_rate
        
        print("-" * 80)
        print(f"✅ 合成完成!")
        print(f"   总块数: {len(audio_chunks)}")
        print(f"   总时长: {total_duration:.2f} 秒")
        print(f"   合成耗时: {synthesis_time:.2f} 秒")
        print(f"   RTF: {synthesis_time / total_duration:.2f}")
        
    except Exception as e:
        print(f"❌ 合成失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 合并音频块并保存
    if not audio_chunks:
        print("❌ 没有生成音频数据!")
        return
    
    print("\n💾 保存音频文件...")
    try:
        # 合并所有音频块
        merged_audio = torch.cat(audio_chunks, dim=1)  # (1, total_samples)
        
        # 转换为numpy数组并处理格式
        # 将tensor转换为numpy，并确保是单声道 (samples,)
        audio_np = merged_audio.squeeze(0).cpu().numpy()  # (total_samples,)
        
        # 归一化到 [-1, 1] 范围（如果不在这个范围）
        if audio_np.max() > 1.0 or audio_np.min() < -1.0:
            audio_np = audio_np / np.max(np.abs(audio_np))
        
        # 转换为16位整数格式
        audio_int16 = (audio_np * 32767).astype(np.int16)
        
        # 生成输出文件名
        safe_text = "".join(c for c in text[:30] if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_text = safe_text.replace(' ', '_') if safe_text else "cosyvoice3_test"
        output_filename = f"{safe_text}_{spk_id}.wav"
        output_file = output_path / output_filename
        
        # 使用 scipy.io.wavfile 保存为WAV文件
        wavfile.write(
            str(output_file),
            model.sample_rate,
            audio_int16
        )
        
        file_size = output_file.stat().st_size
        print(f"✅ 音频已保存!")
        print(f"   文件路径: {output_file}")
        print(f"   文件大小: {file_size} 字节 ({file_size / 1024:.2f} KB)")
        print(f"   音频时长: {total_duration:.2f} 秒")
        print(f"   采样率: {model.sample_rate} Hz")
        print(f"   声道数: 1 (单声道)")
        print(f"   位深: 16 bit")
        
    except Exception as e:
        print(f"❌ 保存失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CosyVoice3 语音合成测试")
    parser.add_argument(
        "--model_dir",
        type=str,
        required=True,
        help="模型目录路径（本地路径或 ModelScope 路径，如 'iic/CosyVoice3-0_5B'）"
    )
    parser.add_argument(
        "--text",
        type=str,
        default="你好，这是一个CosyVoice3模型的测试。",
        help="要合成的文本"
    )
    parser.add_argument(
        "--spk_id",
        type=str,
        default=None,
        help="说话人ID（如果不指定，将使用第一个可用说话人）"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="test_output",
        help="输出目录"
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="使用流式输出"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="语速倍数（默认1.0）"
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="使用FP16精度（需要CUDA）"
    )
    parser.add_argument(
        "--load_trt",
        action="store_true",
        help="加载TensorRT引擎（需要CUDA和预编译的TRT引擎）"
    )
    parser.add_argument(
        "--load_vllm",
        action="store_true",
        help="加载vLLM引擎（需要CUDA和预编译的vLLM引擎）"
    )
    
    args = parser.parse_args()
    
    # 检查CUDA可用性
    if args.fp16 or args.load_trt or args.load_vllm:
        if not torch.cuda.is_available():
            print("⚠️  警告: 未检测到CUDA，将禁用FP16/TensorRT/vLLM选项")
            args.fp16 = False
            args.load_trt = False
            args.load_vllm = False
    
    test_cosyvoice3(
        model_dir=args.model_dir,
        text=args.text,
        spk_id=args.spk_id,
        output_dir=args.output_dir,
        stream=args.stream,
        speed=args.speed,
        fp16=args.fp16,
        load_trt=args.load_trt,
        load_vllm=args.load_vllm
    )

