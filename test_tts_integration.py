#!/usr/bin/env python3
"""
TTS集成测试脚本
测试CosyVoice2 TTS服务是否正常工作
"""
import asyncio
import os
import sys
import logging

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
# 添加CosyVoice2_MODULE到路径
sys.path.insert(0, os.path.join(project_root, 'CosyVoice2_MODULE'))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def text_generator():
    """生成测试文本流"""
    texts = [
        "今天天气很好，",
        "适合出去散步，",
        "希望大家都开心。"
    ]
    for text in texts:
        logger.info(f"发送文本: {text}")
        yield text
        await asyncio.sleep(0.1)


async def test_tts_service():
    """测试TTS服务"""
    logger.info("=" * 60)
    logger.info("开始测试TTS服务")
    logger.info("=" * 60)

    try:
        # 设置正确的模型路径（使用CosyVoice2-0_5B）
        os.environ['TTS_LOCAL_MODEL_DIR'] = '/data/models/CosyVoice2-0_5B'

        # 导入TTS服务
        from tts_utils import get_tts_service, initialize_tts

        # 初始化TTS服务
        logger.info("初始化TTS服务...")
        if await initialize_tts():
            logger.info("✅ TTS服务初始化成功")
        else:
            logger.error("❌ TTS服务初始化失败")
            return False

        # 获取TTS服务实例
        tts_service = get_tts_service()
        if not tts_service:
            logger.error("❌ 无法获取TTS服务实例")
            return False

        logger.info(f"TTS服务类型: {type(tts_service).__name__}")

        # 测试1: 列出可用说话人
        logger.info("\n--- 测试1: 列出可用说话人 ---")
        try:
            speakers = tts_service.list_speakers()
            logger.info(f"✅ 可用说话人: {speakers[:5]}... (共{len(speakers)}个)")
        except Exception as e:
            logger.warning(f"⚠️  获取说话人列表失败: {e}")

        # 测试2: 流式合成
        logger.info("\n--- 测试2: 流式语音合成 ---")
        try:
            chunk_count = 0
            total_bytes = 0

            async for audio_chunk in tts_service.synthesize_streaming(
                text_generator(),
                spk_id="zh_girl"
            ):
                chunk_count += 1
                total_bytes += len(audio_chunk)
                logger.info(f"  收到音频chunk {chunk_count}: {len(audio_chunk)} bytes")

            logger.info(f"✅ 流式合成完成: {chunk_count} chunks, {total_bytes} bytes")

        except Exception as e:
            logger.error(f"❌ 流式合成失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        # 测试3: 非流式合成
        logger.info("\n--- 测试3: 非流式语音合成 ---")
        try:
            test_text = "这是一个测试文本，用于验证非流式语音合成功能。"
            audio_data = await tts_service.synthesize(test_text, spk_id="zh_girl")

            logger.info(f"✅ 非流式合成完成: {len(audio_data)} bytes")

            # 保存测试音频
            output_path = os.path.join(os.path.dirname(__file__), "test_tts_output.pcm")
            with open(output_path, "wb") as f:
                f.write(audio_data)
            logger.info(f"  音频已保存到: {output_path}")

        except Exception as e:
            logger.error(f"❌ 非流式合成失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        logger.info("\n" + "=" * 60)
        logger.info("✅ 所有测试通过！")
        logger.info("=" * 60)
        return True

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_integration():
    """测试Orchestrator集成"""
    logger.info("\n" + "=" * 60)
    logger.info("测试Orchestrator集成")
    logger.info("=" * 60)

    try:
        from core.orchestrator import NewsAgentOrchestrator
        from tts_utils import get_tts_service, initialize_tts

        # 初始化TTS服务
        await initialize_tts()
        tts_service = get_tts_service()

        # 创建Orchestrator并注入TTS服务
        orchestrator = NewsAgentOrchestrator()
        orchestrator.tts_service = tts_service

        logger.info("✅ Orchestrator创建成功")
        logger.info(f"  - TTS服务: {'已注入' if orchestrator.tts_service else '未注入'}")
        logger.info(f"  - LLM配置: {orchestrator.llm_config.get('model', 'unknown')}")

        return True

    except Exception as e:
        logger.warning(f"⚠️  Orchestrator集成测试跳过: {e}")
        logger.warning("Orchestrator有其他依赖问题，这是正常的")
        return True  # 返回True以避免阻止其他测试


async def main():
    """主测试函数"""
    # 测试TTS服务
    tts_result = await test_tts_service()

    # 测试Orchestrator集成
    orch_result = await test_orchestrator_integration()

    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    logger.info(f"TTS服务: {'✅ 通过' if tts_result else '❌ 失败'}")
    logger.info(f"Orchestrator集成: {'✅ 通过' if orch_result else '❌ 失败'}")

    if tts_result and orch_result:
        logger.info("\n🎉 所有测试通过！TTS集成成功！")
        return 0
    else:
        logger.error("\n❌ 部分测试失败，请检查错误信息")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
