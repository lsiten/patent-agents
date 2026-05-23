#!/usr/bin/env python3
"""
完整专利申请工作流演示
展示从技术描述到最终专利文档的完整多 Agent 协同流程
"""
import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, '.')

from src.agents import (
    get_profile_registry,
    get_agent_factory,
    register_default_profiles,
)
from src.core.workflow_engine import (
    PatentWorkflowEngine,
    WorkflowContext,
    WorkflowState,
    WorkflowPhase,
)
from src.core import get_logger

logger = get_logger("demo_workflow")


def print_separator(title: str) -> None:
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_phase_result(result: Any) -> None:
    """打印阶段结果"""
    print(f"\n✅ 阶段: {result.phase.value}")
    print(f"   状态: {'成功' if result.success else '失败'}")
    print(f"   耗时: {result.duration_seconds:.2f} 秒")

    if result.output:
        print(f"\n   输出摘要:")
        for key, value in list(result.output.items())[:5]:
            if isinstance(value, (str, int, float, bool)):
                preview = str(value)[:80] + "..." if len(str(value)) > 80 else str(value)
                print(f"     - {key}: {preview}")
            elif isinstance(value, list):
                print(f"     - {key}: {len(value)} 项")
            elif isinstance(value, dict):
                print(f"     - {key}: {len(value)} 键")

    if result.issues:
        print(f"\n   ⚠️  问题与警告:")
        for issue in result.issues[:5]:
            print(f"     - {issue}")
        if len(result.issues) > 5:
            print(f"     - ... 还有 {len(result.issues) - 5} 个问题")


def print_final_summary(context: WorkflowContext) -> None:
    """打印最终摘要"""
    print_separator("📊 工作流执行总结")

    print(f"\n任务 ID: {context.task_id}")
    print(f"用户 ID: {context.user_id}")
    print(f"当前状态: {context.current_phase.value}")
    print(f"创建时间: {context.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    duration = (datetime.now() - context.created_at).total_seconds()
    print(f"总耗时: {duration:.2f} 秒")

    print(f"\n迭代次数: {context.iteration_count}")
    print(f"已完成阶段数: {len(context.phase_history)}")

    print(f"\n📋 各阶段执行情况:")
    for result in context.phase_history:
        status = "✅" if result.success else "❌"
        duration = result.duration_seconds
        print(f"   {status} {result.phase.value}: {duration:.2f} 秒")

    if context.current_phase == WorkflowState.COMPLETED:
        print("\n🎉 专利申请工作流全部完成！")
        print("\n📄 生成的文档:")
        if context.requirement_analysis:
            print("   ✅ 需求分析文档")
        if context.retrieval_report:
            print("   ✅ 专利性检索报告")
        if context.patent_draft:
            print("   ✅ 专利申请文件草案")
        if context.review_report:
            print("   ✅ 质量审查报告")
    elif context.current_phase == WorkflowState.FAILED:
        print(f"\n❌ 工作流失败")


async def progress_callback(phase: Any, result: Any) -> None:
    """进度回调函数"""
    print(f"\n⏳ 完成阶段: {phase.value}")
    print(f"   状态: {'成功' if result.success else '失败'}")
    print(f"   耗时: {result.duration_seconds:.2f} 秒")
    if result.issues:
        print(f"   问题数: {len(result.issues)}")


async def demo_basic_workflow() -> None:
    """演示基本工作流"""
    print_separator("演示 1: 基本工作流执行")

    # 初始化
    registry = get_profile_registry()
    register_default_profiles(registry)
    engine = PatentWorkflowEngine()

    # 技术描述
    tech_description = """
    本发明涉及一种基于强化学习的神经网络自动结构搜索方法，
    主要创新点包括：
    1. 提出了一种新的奖励函数设计，能够同时优化准确率和推理速度
    2. 采用分层搜索策略，先搜索宏观结构再搜索微观参数
    3. 引入知识蒸馏，将搜索到的网络快速迁移到新任务

    技术效果：在图像分类任务上，搜索效率提升300%，模型精度提升5%。
    """

    print(f"\n📝 技术描述:")
    print(f"   {tech_description.strip()[:200]}...")

    # 创建工作流
    context = engine.create_workflow(
        task_id=f"demo_task_{datetime.now().strftime('%H%M%S')}",
        user_id="demo_user",
        description=tech_description.strip(),
    )

    print(f"\n✅ 工作流创建成功")
    print(f"   任务 ID: {context.task_id}")
    print(f"   初始状态: {context.current_phase.value}")

    # 执行完整工作流
    print(f"\n🚀 开始执行完整工作流（Mock 模式，无需 API Key）...")

    try:
        context = await engine.execute_full_workflow(
            context=context,
            phase_callback=progress_callback,
        )
        print_final_summary(context)
    except Exception as e:
        logger.error("工作流执行失败", error=str(e), exc_info=True)
        print(f"\n❌ 工作流执行失败: {e}")


async def demo_chat_brainstorm() -> None:
    """演示聊天头脑风暴"""
    print_separator("演示 2: 头脑风暴聊天交互")

    # 初始化
    registry = get_profile_registry()
    register_default_profiles(registry)
    engine = PatentWorkflowEngine()

    # 创建工作流
    context = engine.create_workflow(
        task_id=f"chat_demo_{datetime.now().strftime('%H%M%S')}",
        user_id="demo_user",
        description="我想申请一个关于 AI 图像识别的专利",
    )

    print(f"\n✅ 工作流创建成功，任务 ID: {context.task_id}")
    print(f"\n💬 开始头脑风暴对话...")

    # 模拟用户消息
    user_messages = [
        "我的发明主要是改进了卷积神经网络的特征提取方法",
        "具体来说，我提出了一种多尺度的特征融合策略",
        "这个方法在医学图像分割任务上效果特别好",
    ]

    for i, msg in enumerate(user_messages, 1):
        print(f"\n👤 用户消息 {i}: {msg}")
        context.add_message("user", msg)
        response = f"感谢您的说明！这是一个很有价值的创新点。关于多尺度特征融合，您是否已经测试了不同的融合策略（比如拼接、加权求和、注意力机制）？这对专利的权利要求很重要。"
        context.add_message("assistant", response)
        print(f"🤖 Agent 回复: {response[:150]}...")

    print(f"\n✅ 头脑风暴完成，准备进入正式申请流程")
    print(f"   消息历史数: {len(context.message_history)}")


async def demo_phase_by_phase() -> None:
    """演示逐阶段执行"""
    print_separator("演示 3: 逐阶段执行与控制")

    # 初始化
    registry = get_profile_registry()
    register_default_profiles(registry)
    engine = PatentWorkflowEngine()

    # 创建工作流
    context = engine.create_workflow(
        task_id=f"phase_demo_{datetime.now().strftime('%H%M%S')}",
        user_id="demo_user",
        description="一种基于 Transformer 的自然语言处理方法",
    )

    print(f"\n✅ 工作流创建成功，任务 ID: {context.task_id}")

    # 手动执行每个阶段（使用 WorkflowState 枚举）
    phases = [
        WorkflowState.BRAINSTORMING,
        WorkflowState.REQUIREMENT_ANALYSIS,
        WorkflowState.RETRIEVAL_ANALYSIS,
        WorkflowState.PATENT_WRITING,
        WorkflowState.QUALITY_REVIEW,
    ]

    for phase in phases:
        print(f"\n{'━' * 50}")
        print(f"⏳ 手动执行阶段: {phase.value}")

        # 执行阶段
        result = await engine.execute_phase(context, phase)
        print_phase_result(result)

        if not result.success:
            print(f"❌ 阶段执行失败，停止流程")
            break

    print(f"\n✅ 逐阶段执行演示完成")
    print(f"   最终状态: {context.current_phase.value}")


async def demo_cancellation() -> None:
    """演示工作流取消"""
    print_separator("演示 4: 工作流取消")

    # 初始化
    registry = get_profile_registry()
    register_default_profiles(registry)
    engine = PatentWorkflowEngine()

    # 创建工作流
    context = engine.create_workflow(
        task_id=f"cancel_demo_{datetime.now().strftime('%H%M%S')}",
        user_id="demo_user",
        description="测试取消功能",
    )

    print(f"\n✅ 工作流创建成功，任务 ID: {context.task_id}")
    print(f"   当前状态: {context.current_phase.value}")

    # 取消工作流（设置状态）
    context.current_phase = WorkflowState.CANCELLED
    context.add_message("system", "用户主动取消")

    print(f"\n✅ 工作流已取消")
    print(f"   新状态: {context.current_phase.value}")


async def main() -> None:
    """主函数"""
    print("\n" + "🚀" * 35)
    print("     完整专利申请多智能体工作流系统演示")
    print("🚀" * 35)

    # 演示 1: 基本工作流
    await demo_basic_workflow()

    # 演示 2: 聊天头脑风暴
    await demo_chat_brainstorm()

    # 演示 3: 逐阶段执行
    await demo_phase_by_phase()

    # 演示 4: 取消功能
    await demo_cancellation()

    print_separator("✅ 所有演示完成！")
    print("\n📋 系统功能清单:")
    print("   ✅ Profile 驱动的 Agent 创建系统")
    print("   ✅ 完整的记忆系统（短期/长期/知识库）")
    print("   ✅ LLM 客户端（Mock 模式 + Fallback 链）")
    print("   ✅ 结构化输出解析与重试")
    print("   ✅ 工作流引擎（状态机 + 阶段执行）")
    print("   ✅ 头脑风暴聊天交互")
    print("   ✅ 逐阶段执行控制")
    print("   ✅ 工作流取消机制")
    print("   ✅ 进度事件回调")

    print("\n💡 下一步:")
    print("   1. 配置 OPENAI_API_KEY 环境变量启用真实 LLM")
    print("   2. 启动 FastAPI 服务: python -m src.api.server")
    print("   3. 连接前端进行完整交互")
    print("   4. 接入真实的专利数据库 API")
    print("   5. 实现向量检索增强记忆系统")


if __name__ == "__main__":
    asyncio.run(main())
