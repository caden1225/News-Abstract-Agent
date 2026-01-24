#!/usr/bin/env python3
import os
import soundfile as sf

from cosyvoice.cli.cosyvoice import CosyVoice2
from cosyvoice.utils.file_utils import load_wav
from cosyvoice.utils.common import set_all_random_seed
import numpy as np
from pathlib import Path
import json
import time as _time

def main():
    set_all_random_seed(0)
    # 模型路径 - 从环境变量获取或使用默认值
    # model_path = '/Users/caden/models/CosyVoice2-0_5B'
    model_path = '/home/models/CosyVoice2-0_5B'
    print("正在初始化CosyVoice2模型...")
    cosyvoice = CosyVoice2(model_path, load_jit=False, load_trt=False, fp16=False)
    print("模型初始化完成！")

    # prompt_audio_path = '/Users/caden/workspace/audios/我当然知道了.wav'
    # prompt_audio_path = '/home/local/Cosyvoice2_MODULE/audios/我当然知道了.wav'
    # prompt_speech_16k = load_wav(prompt_audio_path, 16000)
    # print(f"已加载参考音频: {prompt_audio_path}")
    text_to_synthesize = '收到好友从远方寄来的生日礼物'
    
    # # 示例1：Zero-shot推理 DONE
    # print("\n=== Zero-shot推理 ===")
    # prompt_text = '我当然知道了'
    
    # print(f"合成文本: {text_to_synthesize}")
    # print(f"提示文本: {prompt_text}")
    # import time
    # start = time.perf_counter()
    # print(f"接收参数：text_to_synthesize, prompt_text, prompt_speech_16k") 
    # for i, result in enumerate(cosyvoice.inference_zero_shot(text_to_synthesize, prompt_text, prompt_speech_16k, stream=True)):
    #     output_file = f'orin_zero_shot_prompt_speech_{i}.wav'
    #     # 使用 soundfile 保存音频文件
    #     print(f"First chunk time cost: {time.perf_counter() - start}")
    #     sf.write(output_file, result['tts_speech'].squeeze().cpu().numpy(), cosyvoice.sample_rate)
    #     print(f"已保存: {output_file}")
    
    # # 示例2: 细粒度控制推理
    # print("\n=== 细粒度控制推理 ===")
    # print(f"接收参数：text_with_control, prompt_speech_16k") 
    # text_with_control = '在他讲述那个荒诞故事的过程中，他突然[laughter]停下来，因为他自己也被逗笑了[laughter]。'
    # print(f"合成文本: {text_with_control}")
    
    # for i, result in enumerate(cosyvoice.inference_cross_lingual(text_with_control, prompt_speech_16k, stream=False)):
    #     output_file = f'fine_grained_control_{i}.wav'
    #     # 使用 soundfile 保存音频文件
    #     sf.write(output_file, result['tts_speech'].squeeze().cpu().numpy(), cosyvoice.sample_rate)
    #     print(f"已保存: {output_file}")
    
    # # # 示例3: 指令推理
    # # print("\n=== 指令推理 ===")
    # # instruction = '用英文说这句话'
    # # text_to_synthesize = '今天天气真好，我们去公园散步吧。'
    
    # # print(f"合成文本: {text_to_synthesize}")
    # # print(f"指令: {instruction}")
    
    # # for i, result in enumerate(cosyvoice.inference_instruct2(text_to_synthesize, instruction, prompt_speech_16k, stream=False)):
    # #     output_file = f'instruct_{i}.wav'
    # #     # 使用 soundfile 保存音频文件
    # #     import soundfile as sf
    # #     sf.write(output_file, result['tts_speech'].squeeze().cpu().numpy(), cosyvoice.sample_rate)
    # #     print(f"已保存: {output_file}")

    # 示例4: 预置音色推理 DONE
    print("\n=== 预置音色推理 ===")
    print(f"接收参数：text_to_synthesize, spk_id:woman") 
    for i, result in enumerate(cosyvoice.inference_sft(text_to_synthesize, spk_id="woman", stream=False)):
        output_file = f'sft_spk_speech_{i}.wav'
        # 使用 soundfile 保存音频文件
        import soundfile as sf
        sf.write(output_file, result['tts_speech'].squeeze().cpu().numpy(), cosyvoice.sample_rate)
        print(f"已保存: {output_file}")


    # print("\n所有推理完成！")

if __name__ == "__main__":
    main()
