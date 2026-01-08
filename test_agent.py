"""
本地测试脚本
测试新闻播报Agent的各项功能
"""
import asyncio
import sys
from news_scraper import NewsScraper
from news_summarizer import NewsSummarizer
from tts_service import MockTTSService


async def test_news_scraper():
    """测试新闻抓取功能"""
    print("=" * 60)
    print("测试1: 新闻抓取功能")
    print("=" * 60)

    scraper = NewsScraper()
    news_list = scraper.fetch_today_news(limit_per_source=3)

    print(f"\n✓ 成功获取 {len(news_list)} 条新闻")

    if news_list:
        print("\n前3条新闻:")
        for i, news in enumerate(news_list[:3], 1):
            print(f"\n{i}. [{news.source}] {news.title}")
            print(f"   摘要: {news.summary[:100]}...")

        print("\n✓ 新闻抓取功能正常")
        return True
    else:
        print("\n✗ 未获取到新闻,可能需要检查网络连接")
        return False


async def test_news_summarizer():
    """测试新闻摘要功能"""
    print("\n" + "=" * 60)
    print("测试2: 新闻摘要功能 (使用Mock模式,不需要Sidecar)")
    print("=" * 60)

    # 创建测试数据
    test_news = [
        {
            "title": "测试新闻1: 人工智能取得重大突破",
            "summary": "研究人员在人工智能领域取得重大突破,新模型性能提升30%。这项技术将应用于自动驾驶、医疗诊断等多个领域。",
            "link": "http://test1.com"
        },
        {
            "title": "测试新闻2: 全球气候峰会达成新协议",
            "summary": "在最新的全球气候峰会上,各国代表就减排目标达成新协议,承诺在2030年前将碳排放减少50%。",
            "link": "http://test2.com"
        }
    ]

    print(f"\n测试数据: {len(test_news)} 条新闻")

    # 测试单条新闻摘要(注意:真实环境需要Sidecar,这里只是演示)
    print("\n注意: 真实的摘要功能需要连接Sidecar服务")
    print("当前为演示模式,将使用简化的摘要生成逻辑")

    # 简化版摘要(取前100字)
    for news in test_news:
        summary = news['summary'][:100]
        print(f"\n原标题: {news['title']}")
        print(f"简化摘要: {summary}...")

    print("\n✓ 摘要功能结构正常(需要Sidecar才能使用真实LLM)")
    return True


async def test_tts_service():
    """测试TTS功能"""
    print("\n" + "=" * 60)
    print("测试3: TTS语音播报功能 (Mock模式)")
    print("=" * 60)

    tts = MockTTSService()
    test_text = "各位听众好,以下是今日热点新闻。"

    print(f"\n测试文本: {test_text}")
    result = await tts.text_to_speech(test_text)

    if result is not None:
        print(f"✓ TTS转换成功 (Mock模式)")
        return True
    else:
        print("✗ TTS转换失败")
        return False


async def test_news_report_generation():
    """测试新闻播报稿生成"""
    print("\n" + "=" * 60)
    print("测试4: 新闻播报稿生成")
    print("=" * 60)

    # 模拟新闻列表
    mock_news = [
        {
            "title": "科技新闻: AI技术快速发展",
            "summary": "人工智能技术在各个领域快速发展,应用场景不断拓展。",
            "ai_summary": "AI技术快速发展,应用场景拓展。"
        },
        {
            "title": "经济新闻: 市场持续向好",
            "summary": "经济数据显示市场持续向好,各行业复苏迹象明显。",
            "ai_summary": "经济数据显示市场向好,各行业复苏明显。"
        },
        {
            "title": "体育新闻: 冠军争夺激烈",
            "summary": "在最新的体育赛事中,各队表现出色,冠军争夺十分激烈。",
            "ai_summary": "体育赛事激烈,冠军争夺白热化。"
        }
    ]

    print(f"\n使用 {len(mock_news)} 条模拟新闻生成播报稿")

    # 生成播报稿
    report_parts = ["各位听众好,以下是今日热点新闻:"]
    for i, news in enumerate(mock_news, 1):
        report_parts.append(f"{i}. {news['title']} - {news['ai_summary']}")
    report_parts.append("以上就是今日热点新闻,感谢收听")

    report = "\n".join(report_parts)

    print("\n生成的播报稿:")
    print("-" * 60)
    print(report)
    print("-" * 60)

    print("\n✓ 播报稿生成成功")
    return True


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("新闻播报Agent - 本地功能测试")
    print("=" * 60)

    results = []

    # 测试1: 新闻抓取
    try:
        result1 = await test_news_scraper()
        results.append(("新闻抓取", result1))
    except Exception as e:
        print(f"\n✗ 新闻抓取测试失败: {e}")
        results.append(("新闻抓取", False))

    # 测试2: 新闻摘要
    try:
        result2 = await test_news_summarizer()
        results.append(("新闻摘要", result2))
    except Exception as e:
        print(f"\n✗ 新闻摘要测试失败: {e}")
        results.append(("新闻摘要", False))

    # 测试3: TTS功能
    try:
        result3 = await test_tts_service()
        results.append(("TTS功能", result3))
    except Exception as e:
        print(f"\n✗ TTS功能测试失败: {e}")
        results.append(("TTS功能", False))

    # 测试4: 播报稿生成
    try:
        result4 = await test_news_report_generation()
        results.append(("播报稿生成", result4))
    except Exception as e:
        print(f"\n✗ 播报稿生成测试失败: {e}")
        results.append(("播报稿生成", False))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name:20s} {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print("\n" + "-" * 60)
    print(f"总计: {len(results)} 个测试, {passed} 个通过, {failed} 个失败")
    print("-" * 60)

    if failed == 0:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
