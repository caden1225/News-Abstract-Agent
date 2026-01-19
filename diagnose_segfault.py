#!/usr/bin/env python3
"""
段错误诊断脚本
逐步测试 TTS 服务初始化的每个步骤，定位段错误发生的位置
"""
import sys
import os
import traceback
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "tts_modules"))

print("=" * 70)
print("段错误诊断脚本")
print("=" * 70)
print()

# 步骤1: 检查基础导入
print("[步骤 1] 检查基础库导入...")
try:
    import torch
    print(f"  ✅ PyTorch: {torch.__version__}")
    print(f"  ✅ CUDA 可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  ✅ CUDA 版本: {torch.version.cuda}")
        print(f"  ✅ GPU 数量: {torch.cuda.device_count()}")
except Exception as e:
    print(f"  ❌ PyTorch 导入失败: {e}")
    sys.exit(1)

try:
    import numpy as np
    print(f"  ✅ NumPy: {np.__version__}")
except Exception as e:
    print(f"  ❌ NumPy 导入失败: {e}")
    sys.exit(1)

print()

# 步骤2: 检查 cosyvoice2 模块导入
print("[步骤 2] 检查 cosyvoice2 模块导入...")
try:
    import cosyvoice2.tts_service as cosyvoice2_module
    print("  ✅ cosyvoice2.tts_service 导入成功")
except Exception as e:
    print(f"  ❌ cosyvoice2 模块导入失败: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# 步骤3: 检查配置
print("[步骤 3] 检查配置...")
try:
    from llm_utils.config import config
    model_dir = config.get("tts.local_model_dir")
    model_type = config.get("tts.local_model_type", "auto")
    fp16 = config.get("tts.acceleration.fp16", "true").lower() in ("true", "1", "yes")
    load_trt = config.get("tts.acceleration.tensorrt", "true").lower() in ("true", "1", "yes")
    
    print(f"  ✅ 模型目录: {model_dir}")
    print(f"  ✅ 模型类型: {model_type}")
    print(f"  ✅ FP16: {fp16}")
    print(f"  ✅ TensorRT: {load_trt}")
    
    if not model_dir or model_dir == "null":
        print("  ❌ 模型目录未配置")
        sys.exit(1)
    
    if not os.path.exists(model_dir):
        print(f"  ❌ 模型目录不存在: {model_dir}")
        sys.exit(1)
    
    print(f"  ✅ 模型目录存在")
except Exception as e:
    print(f"  ❌ 配置检查失败: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# 步骤4: 检查模型文件
print("[步骤 4] 检查模型文件...")
try:
    model_path = Path(model_dir)
    required_files = [
        "cosyvoice3.yaml" if model_type in ("auto", "cosyvoice3") else "cosyvoice2.yaml",
        "campplus.onnx",
        "speech_tokenizer_v3.onnx" if model_type in ("auto", "cosyvoice3") else "speech_tokenizer_v2.onnx",
        "spk2info.pt",
        "llm.pt",
        "flow.pt",
        "hift.pt"
    ]
    
    for file in required_files:
        file_path = model_path / file
        if file_path.exists():
            print(f"  ✅ {file} 存在")
        else:
            print(f"  ⚠️  {file} 不存在")
except Exception as e:
    print(f"  ❌ 模型文件检查失败: {e}")
    traceback.print_exc()

print()

# 步骤5: 尝试创建 CosyVoiceTTSService 实例（这是段错误发生的地方）
print("[步骤 5] 尝试创建 CosyVoiceTTSService 实例...")
print("  ⚠️  这一步可能会触发段错误")
print()

try:
    CosyVoiceTTSService = cosyvoice2_module.TTSService
    
    print(f"  📝 准备初始化，参数:")
    print(f"     - model_dir: {model_dir}")
    print(f"     - model_type: {model_type}")
    print(f"     - fp16: {fp16}")
    print(f"     - load_trt: {load_trt}")
    print()
    
    # 这里可能会发生段错误
    print("  🔄 开始初始化 CosyVoiceTTSService...")
    tts_service = CosyVoiceTTSService(
        model_dir=model_dir,
        model_type=model_type,
        spk_id="girl_zh",
        fp16=fp16,
        load_trt=load_trt,
        trt_concurrent=4,
        load_vllm=False
    )
    print("  ✅ CosyVoiceTTSService 初始化成功！")
    print(f"  ✅ 采样率: {tts_service.model.sample_rate}")
    
except Exception as e:
    print(f"  ❌ CosyVoiceTTSService 初始化失败: {e}")
    print(f"  ❌ 错误类型: {type(e).__name__}")
    traceback.print_exc()
    sys.exit(1)
except SystemError as e:
    print(f"  ❌ 系统错误（可能是段错误）: {e}")
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print("✅ 所有步骤完成，未发现段错误")
print("=" * 70)

