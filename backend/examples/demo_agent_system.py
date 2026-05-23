#!/usr/bin/env python3
"""
Hermes Agent 系统演示
展示 Profile 驱动的多 Agent 协作系统
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.agents import (
    get_profile_registry,
    get_agent_factory,
    register_default_profiles,
    AgentMemoryManager,
    KnowledgeBase,
)
from src.core import configure_logging, get_logger

# 配置日志
configure_logging()
logger = get_logger("demo")


async def demo_profile_registry():
    """演示 Profile 注册系统"""
    print("\n" + "="*60)
    print("  1. Profile 注册系统演示")
    print("="*60)

    registry = get_profile_registry()
    register_default_profiles(registry)

    print(f"\n已注册 {len(registry.list_all())} 个 Agent Profile:\n")
    for profile in registry.list_all():
        print(f"  ✅ {profile.name}")
        print(f"     ID: {profile.profile_id}")
        print(f"     角色: {profile.role.value}")
        print(f"     技能数: {len(profile.skills)}")
        print(f"     工具数: {len(profile.tool_config.enabled_tools)}")
        print(f"     温度系数: {profile.temperature}")
        print()

    # 搜索演示
    print("\n🔍 搜索 '专利性' 相关的 Agent:")
    results = registry.search("专利性")
    for profile in results:
        print(f"   - {profile.name}")

    # 按角色搜索
    print("\n👔 CEO 角色的 Agent:")
    ceo_profiles = registry.get_by_role("ceo")
    for profile in ceo_profiles:
        print(f"   - {profile.name}")


async def demo_memory_system():
    """演示记忆系统"""
    print("\n" + "="*60)
    print("  2. 记忆系统演示")
    print("="*60)

    # 创建记忆管理器
    memory_mgr = AgentMemoryManager(
        agent_id="demo_agent",
        user_id="demo_user",
        enable_long_term=True,
    )

    # 创建并注册专利法知识库
    patent_law_kb = KnowledgeBase(kb_id="patent_law", name="专利法知识库")
    patent_law_kb.add_entry(
        title="新颖性定义",
        content="新颖性，是指该发明或者实用新型不属于现有技术；也没有任何单位或者个人就同样的发明或者实用新型在申请日以前向国务院专利行政部门提出过申请，并记载在申请日以后公布的专利申请文件或者公告的专利文件中。",
        category="law",
        reference="专利法第二十二条",
    )
    patent_law_kb.add_entry(
        title="创造性定义",
        content="创造性，是指与现有技术相比，该发明具有突出的实质性特点和显著的进步，该实用新型具有实质性特点和进步。",
        category="law",
        reference="专利法第二十二条",
    )
    memory_mgr.register_knowledge_base(patent_law_kb)

    print("\n💬 短期记忆演示:")
    # 添加对话历史
    memory_mgr.add_chat_message("user", "我想申请一个关于AI算法的专利")
    memory_mgr.add_chat_message("assistant", "好的，我来帮您分析一下这个技术方案")
    memory_mgr.add_chat_message("user", "核心是改进了神经网络的训练方法")

    # 获取上下文
    context = memory_mgr.get_chat_context()
    print(f"上下文内容:\n{context}")

    print(f"\n短期记忆中的消息数: {memory_mgr.short_term.count()}")

    print("\n🧠 长期记忆演示:")
    # 添加长期记忆
    memory_mgr.add_important_memory(
        content="用户的技术核心是改进神经网络训练方法，使用了新的优化器",
        memory_type="tech_insight",
        importance=0.9,
    )
    memory_mgr.add_important_memory(
        content="用户希望申请发明专利，而非实用新型",
        memory_type="preference",
        importance=0.8,
    )
    print(f"长期记忆数量: {memory_mgr.long_term.count()}")

    print("\n📚 知识库检索演示:")
    # 检索相关内容
    results = memory_mgr.search_knowledge_base("patent_law", "新颖性", limit=2)
    for r in results:
        print(f"  📖 {r['title']} (相关度: {r['relevance_score']:.2f})")
        print(f"     引用: {r['reference']}")
        print(f"     内容摘要: {r['content'][:100]}...")

    print("\n📊 记忆摘要:")
    summary = memory_mgr.get_memory_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")


async def demo_agent_factory():
    """演示 Agent 工厂"""
    print("\n" + "="*60)
    print("  3. Agent 工厂演示")
    print("="*60)

    registry = get_profile_registry()
    register_default_profiles(registry)
    factory = get_agent_factory()

    print("\n🏭 创建需求分析 Agent:")
    analyst = factory.create_agent("patent.requirement_analyst.v1")
    print(f"   Agent 名称: {analyst.name}")
    print(f"   描述: {analyst.description}")
    print(f"   模型: {analyst.model}")
    print(f"   温度: {analyst.temperature}")
    print(f"   系统提示词长度: {len(analyst._build_system_prompt())} 字符")

    print("\n📋 Agent 系统提示词预览 (前 300 字):")
    system_prompt = analyst._build_system_prompt()
    print(f"   {system_prompt[:300]}...")


async def demo_ceo_workflow():
    """演示 CEO Agent 工作流协调"""
    print("\n" + "="*60)
    print("  4. CEO Agent 工作流协调演示")
    print("="*60)

    # 初始化环境
    registry = get_profile_registry()
    register_default_profiles(registry)
    factory = get_agent_factory()

    # 创建 CEO Agent
    ceo = factory.create_agent("patent.ceo.v1")
    print(f"\n👔 CEO Agent: {ceo.name}")

    # 模拟技术描述
    tech_description = """
    本发明涉及一种基于强化学习的神经网络自动结构搜索方法，
    主要创新点包括：
    1. 提出了一种新的奖励函数设计，能够同时优化准确率和推理速度
    2. 采用分层搜索策略，先搜索宏观结构再搜索微观参数
    3. 引入知识蒸馏，将搜索到的网络快速迁移到新任务

    技术效果：在图像分类任务上，搜索效率提升300%，模型精度提升5%。
    """

    print(f"\n📝 技术描述: {tech_description[:150]}...")

    # 使用任务规划工具
    print("\n🔧 执行任务规划工具...")

    # 注意：实际运行需要 LLM API Key，这里只演示初始化
    print("\n✅ 工作流规划演示完成")
    print("\n实际执行需要配置 LLM API Key 后运行完整流程:")
    print("  1. 需求分析 Agent -> 结构化技术描述")
    print("  2. 检索分析 Agent -> 现有技术比对与专利性评估")
    print("  3. 专利撰写 Agent -> 生成权利要求书与说明书")
    print("  4. 质量审查 Agent -> 合规性检查与质量优化")


async def main():
    """主函数"""
    print("\n" + "🚀"*20)
    print("     Hermes Agent 系统 - 专利申请多智能体演示")
    print("🚀"*20)

    # 1. Profile 注册系统
    await demo_profile_registry()

    # 2. 记忆系统
    await demo_memory_system()

    # 3. Agent 工厂
    await demo_agent_factory()

    # 4. CEO 工作流
    await demo_ceo_workflow()

    print("\n" + "="*60)
    print("  ✅ 所有演示完成！")
    print("="*60)
    print("\n💡 下一步:")
    print("   1. 配置 LLM API Key (OPENAI_API_KEY / ANTHROPIC_API_KEY)")
    print("   2. 运行各专业 Agent 进行完整测试")
    print("   3. 连接真实的专利数据库 API")
    print("   4. 实现向量搜索以增强记忆检索")


if __name__ == "__main__":
    asyncio.run(main())
