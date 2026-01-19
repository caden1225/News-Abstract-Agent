#!/usr/bin/env python3
"""
合并test_output目录中的音频文件
按照文件名中的frame编号排序并合并
"""
import os
import re
from pathlib import Path
from typing import List, Dict
try:
    from pydub import AudioSegment
except ImportError:
    print("需要安装pydub库: pip install pydub")
    exit(1)


def extract_frame_number(filename: str) -> int:
    """从文件名中提取frame编号"""
    match = re.search(r'_frame(\d+)_', filename)
    if match:
        return int(match.group(1))
    return 0


def group_audio_files(audio_dir: Path) -> Dict[str, List[Path]]:
    """按前缀分组音频文件"""
    groups: Dict[str, List[Path]] = {}
    
    for wav_file in audio_dir.glob("*.wav"):
        # 提取前缀（frame之前的部分）
        match = re.match(r'(.+?)_frame\d+_', wav_file.name)
        if match:
            prefix = match.group(1)
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(wav_file)
    
    # 对每个组的文件按frame编号排序
    for prefix in groups:
        groups[prefix].sort(key=lambda x: extract_frame_number(x.name))
    
    return groups


def merge_audio_files(audio_files: List[Path], output_path: Path) -> bool:
    """合并多个音频文件"""
    if not audio_files:
        print(f"没有找到音频文件")
        return False
    
    print(f"开始合并 {len(audio_files)} 个音频文件...")
    
    try:
        # 加载第一个音频文件
        combined = AudioSegment.from_wav(str(audio_files[0]))
        print(f"  加载: {audio_files[0].name}")
        
        # 依次追加其他音频文件
        for audio_file in audio_files[1:]:
            print(f"  加载: {audio_file.name}")
            audio = AudioSegment.from_wav(str(audio_file))
            combined += audio
        
        # 导出合并后的音频
        combined.export(str(output_path), format="wav")
        print(f"✓ 成功合并到: {output_path}")
        print(f"  总时长: {len(combined) / 1000:.2f} 秒")
        return True
    except Exception as e:
        print(f"✗ 合并失败: {e}")
        return False


def main():
    audio_dir = Path(__file__).parent / "test_output"
    
    if not audio_dir.exists():
        print(f"错误: 目录 {audio_dir} 不存在")
        return
    
    # 按前缀分组音频文件
    groups = group_audio_files(audio_dir)
    
    if not groups:
        print("没有找到音频文件")
        return
    
    print(f"找到 {len(groups)} 个音频序列:\n")
    
    # 合并每个序列
    for prefix, audio_files in groups.items():
        print(f"序列: {prefix}")
        print(f"  文件数量: {len(audio_files)}")
        
        # 生成输出文件名
        output_filename = f"{prefix}_merged.wav"
        output_path = audio_dir / output_filename
        
        # 合并音频
        merge_audio_files(audio_files, output_path)
        print()


if __name__ == "__main__":
    main()

