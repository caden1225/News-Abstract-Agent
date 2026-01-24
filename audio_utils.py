#!/usr/bin/env python3
"""
音频工具 - 播放和转换PCM音频
"""
import sys
import wave
import numpy as np
import argparse
from scipy import signal

def wav_to_pcm(wav_file, pcm_file, target_sample_rate=24000, target_channels=1, target_bit_depth=16):
    """转换WAV到PCM
    
    Args:
        wav_file: 输入的WAV文件路径
        pcm_file: 输出的PCM文件路径
        target_sample_rate: 目标采样率（默认24000Hz）
        target_channels: 目标声道数（默认1，单声道）
        target_bit_depth: 目标位深（默认16位）
    """
    print(f"读取WAV文件: {wav_file}")
    
    # 读取WAV文件
    with wave.open(wav_file, 'rb') as wav:
        original_sample_rate = wav.getframerate()
        original_channels = wav.getnchannels()
        original_bit_depth = wav.getsampwidth() * 8
        n_frames = wav.getnframes()
        
        print(f"原始格式:")
        print(f"  采样率: {original_sample_rate}Hz")
        print(f"  声道数: {original_channels}")
        print(f"  位深: {original_bit_depth}bit")
        print(f"  帧数: {n_frames}")
        
        # 读取音频数据
        audio_data = wav.readframes(n_frames)
    
    # 根据原始位深转换为numpy数组
    if original_bit_depth == 8:
        audio = np.frombuffer(audio_data, dtype=np.uint8).astype(np.int16) - 128
        audio = (audio * 256).astype(np.int16)
    elif original_bit_depth == 16:
        audio = np.frombuffer(audio_data, dtype=np.int16)
    elif original_bit_depth == 24:
        # 24位需要特殊处理
        audio = np.frombuffer(audio_data, dtype=np.uint8)
        audio = audio.reshape(-1, 3)
        audio = (audio[:, 0] | (audio[:, 1] << 8) | (audio[:, 2] << 16)).astype(np.int32)
        audio = (audio - 8388608).astype(np.int16)  # 转换为有符号16位
    elif original_bit_depth == 32:
        audio = np.frombuffer(audio_data, dtype=np.int32)
        audio = (audio >> 16).astype(np.int16)  # 降采样到16位
    else:
        raise ValueError(f"不支持的位深: {original_bit_depth}bit")
    
    # 处理多声道：转换为单声道
    if original_channels > 1:
        audio = audio.reshape(-1, original_channels)
        if target_channels == 1:
            # 转换为单声道（取平均值）
            audio = audio.mean(axis=1).astype(np.int16)
            print(f"  多声道已转换为单声道")
    
    # 重采样
    if original_sample_rate != target_sample_rate:
        print(f"重采样: {original_sample_rate}Hz -> {target_sample_rate}Hz")
        # 计算重采样比例
        num_samples = int(len(audio) * target_sample_rate / original_sample_rate)
        audio = signal.resample(audio, num_samples).astype(np.int16)
    
    # 确保是16位
    if target_bit_depth == 16:
        audio = audio.astype(np.int16)
    else:
        raise ValueError(f"目前只支持16位输出，请求的是{target_bit_depth}位")
    
    # 写入PCM文件
    print(f"写入PCM文件: {pcm_file}")
    with open(pcm_file, 'wb') as f:
        f.write(audio.tobytes())
    
    duration = len(audio) / target_sample_rate
    file_size = len(audio) * 2  # 16位 = 2字节
    
    print(f"✅ 转换完成!")
    print(f"   采样率: {target_sample_rate}Hz")
    print(f"   声道数: {target_channels}")
    print(f"   位深: {target_bit_depth}bit")
    print(f"   时长: {duration:.2f}秒")
    print(f"   文件大小: {file_size} bytes ({file_size/1024:.2f} KB)")

def pcm_to_wav(pcm_file, wav_file, sample_rate=22050, channels=1):
    """转换PCM到WAV"""
    print(f"读取PCM文件: {pcm_file}")

    with open(pcm_file, 'rb') as f:
        pcm_data = f.read()

    # 转换为numpy数组
    audio = np.frombuffer(pcm_data, dtype=np.int16)

    # 写入WAV文件
    print(f"写入WAV文件: {wav_file}")
    with wave.open(wav_file, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(audio.tobytes())

    duration = len(audio) / sample_rate
    print(f"✅ 转换完成!")
    print(f"   采样率: {sample_rate}Hz")
    print(f"   声道数: {channels}")
    print(f"   时长: {duration:.2f}秒")
    print(f"   文件大小: {len(pcm_data)} bytes")

def play_pcm_pyaudio(pcm_file, sample_rate=22050, channels=1, chunk_size=1024):
    """使用PyAudio播放PCM"""
    try:
        import pyaudio
    except ImportError:
        print("❌ 需要安装 pyaudio: pip install pyaudio")
        return False

    print(f"播放PCM文件: {pcm_file}")
    print("提示: 按 Ctrl+C 停止播放")

    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            output=True
        )

        with open(pcm_file, 'rb') as f:
            data = f.read(chunk_size * 2)
            while data:
                stream.write(data)
                data = f.read(chunk_size * 2)

        stream.stop_stream()
        stream.close()
        print("✅ 播放完成")
        return True

    except KeyboardInterrupt:
        print("\n⚠️  播放已停止")
        return False
    finally:
        p.terminate()

def play_pcm_ffplay(pcm_file, sample_rate=22050, channels=1):
    """使用ffplay播放PCM"""
    import subprocess

    print(f"使用ffplay播放: {pcm_file}")

    # PCM格式参数
    format_params = [
        'f=s16le',      # 16-bit little-endian
        f'ar={sample_rate}',  # 采样率
        f'ac={channels}'      # 声道数
    ]

    cmd = [
        'ffplay',
        '-f', 's16le',
        '-ar', str(sample_rate),
        '-ac', str(channels),
        '-i', pcm_file,
        '-nodisp',      # 不显示视频窗口
        '-autoexit'     # 播放完成后自动退出
    ]

    try:
        subprocess.run(cmd, check=True)
        print("✅ 播放完成")
        return True
    except FileNotFoundError:
        print("❌ 未找到ffplay，请安装ffmpeg")
        print("   Ubuntu/Debian: sudo apt install ffmpeg")
        print("   MacOS: brew install ffmpeg")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ 播放失败: {e}")
        return False

def analyze_pcm(pcm_file, sample_rate=22050):
    """分析PCM文件信息"""
    with open(pcm_file, 'rb') as f:
        data = f.read()

    size = len(data)
    duration = size / 2 / sample_rate
    samples = size // 2

    # 转换为numpy分析
    audio = np.frombuffer(data, dtype=np.int16)

    print("=" * 60)
    print("PCM文件分析")
    print("=" * 60)
    print(f"文件: {pcm_file}")
    print(f"文件大小: {size} bytes ({size/1024:.2f} KB)")
    print(f"采样数: {samples}")
    print(f"采样率: {sample_rate} Hz")
    print(f"时长: {duration:.2f} 秒")
    print(f"声道数: 1 (mono)")
    print(f"位深: 16-bit")
    print(f"\n音频统计:")
    print(f"  最大值: {audio.max()}")
    print(f"  最小值: {audio.min()}")
    print(f"  平均值: {audio.mean():.2f}")
    print(f"  标准差: {audio.std():.2f}")
    print(f"  RMS: {np.sqrt(np.mean(audio**2)):.2f}")

def main():
    parser = argparse.ArgumentParser(description="音频工具")
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # WAV转PCM命令
    wav2pcm_parser = subparsers.add_parser('wav2pcm', help='转换WAV到PCM')
    wav2pcm_parser.add_argument('wav_file', help='WAV文件路径')
    wav2pcm_parser.add_argument('pcm_file', nargs='?', help='PCM文件路径（可选）')
    wav2pcm_parser.add_argument('--sample-rate', type=int, default=24000, help='目标采样率（默认24000Hz）')
    wav2pcm_parser.add_argument('--channels', type=int, default=1, help='目标声道数（默认1，单声道）')
    wav2pcm_parser.add_argument('--bit-depth', type=int, default=16, help='目标位深（默认16位）')
    
    # 转换命令
    convert_parser = subparsers.add_parser('convert', help='转换PCM到WAV')
    convert_parser.add_argument('pcm_file', help='PCM文件路径')
    convert_parser.add_argument('wav_file', nargs='?', help='WAV文件路径（可选）')
    convert_parser.add_argument('--sample-rate', type=int, default=22050, help='采样率')
    convert_parser.add_argument('--channels', type=int, default=1, help='声道数')

    # 播放命令
    play_parser = subparsers.add_parser('play', help='播放PCM文件')
    play_parser.add_argument('pcm_file', help='PCM文件路径')
    play_parser.add_argument('--method', choices=['pyaudio', 'ffplay'], default='ffplay', help='播放方法')
    play_parser.add_argument('--sample-rate', type=int, default=22050, help='采样率')
    play_parser.add_argument('--channels', type=int, default=1, help='声道数')

    # 分析命令
    analyze_parser = subparsers.add_parser('analyze', help='分析PCM文件')
    analyze_parser.add_argument('pcm_file', help='PCM文件路径')
    analyze_parser.add_argument('--sample-rate', type=int, default=22050, help='采样率')

    args = parser.parse_args()

    if args.command == 'wav2pcm':
        pcm_file = args.pcm_file or args.wav_file.replace('.wav', '.pcm')
        wav_to_pcm(args.wav_file, pcm_file, args.sample_rate, args.channels, args.bit_depth)
    
    elif args.command == 'convert':
        wav_file = args.wav_file or args.pcm_file.replace('.pcm', '.wav')
        pcm_to_wav(args.pcm_file, wav_file, args.sample_rate, args.channels)

    elif args.command == 'play':
        if args.method == 'pyaudio':
            play_pcm_pyaudio(args.pcm_file, args.sample_rate, args.channels)
        else:
            play_pcm_ffplay(args.pcm_file, args.sample_rate, args.channels)

    elif args.command == 'analyze':
        analyze_pcm(args.pcm_file, args.sample_rate)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
