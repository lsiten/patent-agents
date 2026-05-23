#!/usr/bin/env python3
"""
演示数据 - 用于展示系统效果的示例数据
"""

import json
from datetime import datetime
from pathlib import Path

from src.models.enums import WorkflowState, PatentType, Severity
from src.models.domain import (
    RequirementDoc,
    KeyFeature,
    RetrievalReport,
    PatentDraft,
    Claim,
    DescriptionSection,
    ReviewReport,
    ReviewResult,
    ReviewIssue,
)


def create_demo_requirement_doc() -> RequirementDoc:
    """创建演示用的需求分析文档"""
    return RequirementDoc(
        tech_field="G06F 40/20 - 自然语言处理 / 多模态理解",
        core_principle=(
            "本发明提出了一种基于多模态融合的智能对话系统，通过"
            "统一的向量空间建模实现文本、语音、图像等多模态输入的"
            "联合理解，并结合动态知识图谱实现上下文推理。"
        ),
        application_scenarios=[
            "智能客服系统",
            "医疗咨询助手",
            "教育培训平台",
            "企业内部知识库问答",
            "法律文书辅助生成",
        ],
        technical_problem=(
            "现有对话系统存在以下不足：1) 单模态理解限制场景应用；"
            "2) 上下文记忆能力有限；3) 领域知识更新滞后；4) 无法"
            "有效处理跨模态问答需求。"
        ),
        technical_solution_summary=(
            "采用Transformer多模态编码器实现跨模态语义对齐，结合"
            "动态知识图谱实时更新领域知识，通过强化学习优化对话"
            "策略，实现多场景自适应应答。"
        ),
        key_features=[
            KeyFeature(
                name="多模态联合理解模块",
                description=(
                    "支持文本、语音、图像输入，通过跨模态注意力机制"
                    "实现统一语义向量空间建模"
                ),
                is_innovative=True,
            ),
            KeyFeature(
                name="动态知识图谱引擎",
                description=(
                    "基于对话内容实时更新知识图谱，支持增量学习和"
                    "领域自适应"
                ),
                is_innovative=True,
            ),
            KeyFeature(
                name="强化学习对话策略优化",
                description=(
                    "基于用户反馈实时调整对话风格和回答深度，实现"
                    "个性化交互"
                ),
                is_innovative=True,
            ),
            KeyFeature(
                name="情感感知共情引擎",
                description=(
                    "识别用户情绪状态，生成具有共情能力的回复内容"
                ),
                is_innovative=True,
            ),
        ],
        patent_type_recommendation=PatentType.INVENTION,
        recommendation_rationale=(
            "本发明涉及核心算法创新和系统架构创新，技术方案具备"
            "突出的实质性特点和显著的进步，符合发明专利申请条件。"
            "同时具备方法和系统的双重保护价值。"
        ),
        beneficial_effects=[
            "提升对话系统的场景适用性，支持多模态交互",
            "回答准确率提升40%以上",
            "领域知识更新延迟从周级降低到小时级",
            "用户满意度提升35%",
            "降低人工客服运营成本60%",
        ],
        information_gaps=[],
        analysis_confidence=0.94,
    )


def create_demo_retrieval_report() -> RetrievalReport:
    """创建演示用的检索分析报告"""
    return RetrievalReport(
        novelty_assessment="high",
        novelty_rationale=(
            "经检索，现有技术中未发现完全相同的多模态联合理解"
            "与动态知识图谱融合的技术方案。"
        ),
        inventive_step_assessment="high",
        inventive_step_rationale=(
            "相对于D1-US9876543B2的单模态对话系统，本发明在"
            "多模态融合、知识更新机制、情感共情等方面均具有"
            "非显而易见的技术改进。"
        ),
        utility_assessment="high",
        utility_rationale=(
            "技术方案可通过软件和硬件结合实现，具备工业应用价值，"
            "已在3个实际场景验证可行性。"
        ),
        overall_patentability="high",
        overall_confidence=0.88,
        prior_art_found=[],
        high_risk_references=[],
        writing_recommendations=[
            "重点突出多模态联合理解的具体实现方式",
            "强调动态知识图谱的增量学习算法细节",
            "在独立权利要求中涵盖方法和系统两种保护主题",
            "补充强化学习奖励函数的具体设计",
        ],
        claim_strategy_recommendations=[
            "构建多层次保护网：独立权利要求覆盖核心架构",
            "从属权利要求限定各模块的具体实现",
            "考虑同时申请方法和系统两项独立权利要求",
        ],
        risk_factors=[
            "部分算法细节可能涉及数学方法，建议结合具体应用场景描述",
            "建议补充实施例和对比实验数据",
        ],
        retrieval_databases=["USPTO", "EPO", "Google Patents", "arXiv"],
        retrieval_keywords=[
            "multi-modal dialogue",
            "knowledge graph",
            "conversation AI",
            "transformer",
            "reinforcement learning",
        ],
    )


def create_demo_patent_draft() -> PatentDraft:
    """创建演示用的专利申请文件草稿"""
    return PatentDraft(
        title="一种基于多模态融合和动态知识图谱的智能对话系统及方法",
        technical_field="本发明涉及人工智能技术领域，具体涉及自然语言处理、多模态理解和知识图谱技术。",
        background_art=DescriptionSection(
            section_name="背景技术",
            content=(
                "随着人工智能技术的快速发展，智能对话系统在客服、"
                "教育、医疗等领域得到广泛应用。然而，现有技术存在"
                "以下不足：首先，大多数对话系统仅支持文本单模态"
                "输入，无法满足多场景交互需求；其次，知识更新"
                "周期长，难以应对领域知识快速迭代的场景；再次，"
                "缺乏情感感知能力，用户体验有待提升。"
            ),
            word_count=150,
        ),
        summary_of_invention=DescriptionSection(
            section_name="发明内容",
            content=(
                "本发明的目的在于克服现有技术的不足，提供一种基于"
                "多模态融合和动态知识图谱的智能对话系统及方法。\n\n"
                "本发明解决其技术问题所采用的技术方案是：\n\n"
                "1. 一种智能对话方法，其特征在于包括以下步骤：\n"
                "   a) 获取用户的多模态输入数据，包括文本、语音、图像；\n"
                "   b) 通过多模态编码器将各模态输入映射到统一语义空间；\n"
                "   c) 利用动态知识图谱进行上下文推理和实体链接；\n"
                "   d) 基于强化学习策略生成优化的应答内容。\n\n"
                "2. 根据权利要求1所述的方法，其特征在于，所述"
                "多模态编码器采用跨模态注意力机制...\n\n"
                "本发明的有益效果包括：实现多模态联合理解，提升"
                "回答准确率40%以上；支持知识实时更新，更新延迟"
                "降低至小时级；具备情感感知能力，用户满意度提升35%。"
            ),
            word_count=320,
        ),
        detailed_description=DescriptionSection(
            section_name="具体实施方式",
            content=(
                "下面结合具体实施例对本发明作进一步详细说明。\n\n"
                "【实施例1】\n"
                "图1示出了本发明智能对话系统的整体架构，包括："
                "多模态输入接口、特征提取层、跨模态融合模块、"
                "动态知识图谱引擎、策略优化模块和应答生成模块。\n\n"
                "多模态输入接口支持同时接收文本、语音、图像三种"
                "输入形式，其中语音输入经过ASR转换为文本，图像"
                "输入经过CNN提取视觉特征。\n\n"
                "跨模态融合模块采用Transformer编码器架构，通过"
                "跨模态注意力机制实现不同模态特征的对齐和融合。\n\n"
                "动态知识图谱引擎采用增量学习算法，根据对话内容"
                "实时更新领域知识图谱的实体和关系。\n\n"
                "【实施例2】\n"
                "强化学习策略优化模块采用PPO算法，奖励函数设计"
                "包括：回答正确性、相关性、共情度、简洁性等维度。"
            ),
            word_count=450,
        ),
        claims=[
            Claim(
                claim_number=1,
                claim_type="independent",
                category="method",
                content=(
                    "1. 一种智能对话方法，其特征在于包括以下步骤：\n"
                    "   a) 获取用户的多模态输入数据，所述多模态输入包括"
                    "文本、语音和/或图像；\n"
                    "   b) 通过预训练的多模态编码器将各模态输入映射到"
                    "统一语义向量空间，获得融合语义表示；\n"
                    "   c) 基于所述融合语义表示进行实体链接，在动态"
                    "知识图谱中检索相关知识实体；\n"
                    "   d) 基于检索到的知识实体和对话上下文，通过"
                    "强化学习优化的策略网络生成应答内容；\n"
                    "   e) 向用户输出所述应答内容，并根据用户反馈"
                    "更新所述动态知识图谱和策略网络参数。"
                ),
                dependencies=[],
            ),
            Claim(
                claim_number=2,
                claim_type="dependent",
                category="method",
                content=(
                    "2. 根据权利要求1所述的方法，其特征在于，步骤b)中的"
                    "多模态编码器采用跨模态注意力机制，通过学习不同模态"
                    "特征之间的对齐关系实现语义融合，具体包括："
                    "计算文本、语音、图像各模态内部的自注意力权重；"
                    "计算跨模态间的交叉注意力权重；"
                    "通过加权融合获得统一的语义向量表示。"
                ),
                dependencies=[1],
            ),
            Claim(
                claim_number=3,
                claim_type="dependent",
                category="method",
                content=(
                    "3. 根据权利要求1所述的方法，其特征在于，所述动态"
                    "知识图谱的更新采用增量学习算法，仅更新与当前对话"
                    "相关的子图区域，包括："
                    "识别新出现的领域实体；"
                    "检测实体间的新增关系；"
                    "基于时间衰减因子老化低频实体和关系。"
                ),
                dependencies=[1],
            ),
            Claim(
                claim_number=4,
                claim_type="dependent",
                category="system",
                content=(
                    "4. 一种智能对话系统，其特征在于包括："
                    "多模态输入接口、多模态编码器、动态知识图谱引擎、"
                    "策略优化模块、应答生成模块和用户反馈接口。"
                ),
                dependencies=[],
            ),
        ],
        abstract=(
            "本发明公开了一种基于多模态融合和动态知识图谱的"
            "智能对话系统及方法，通过多模态编码器将文本、语音、"
            "图像输入映射到统一语义空间，结合动态知识图谱实现"
            "上下文推理，利用强化学习优化对话策略。本发明能够"
            "提升回答准确率40%以上，支持知识实时更新，具备"
            "情感感知能力，可广泛应用于智能客服、医疗咨询、"
            "教育培训等领域。"
        ),
        key_terms_dictionary={
            "多模态融合": "将不同模态（文本、语音、图像等）的特征进行联合建模的技术",
            "跨模态注意力": "一种注意力机制，能够学习不同模态特征之间的对应关系",
            "动态知识图谱": "支持实时增量更新的知识图谱",
            "PPO算法": "Proximal Policy Optimization，一种强化学习算法",
        },
        format_version="2024",
        word_count=1800,
        reference_patent_style_ids=["CN108763456A", "US9876543B2"],
        generated_at=datetime.now(),
        generation_model="demo",
    )


def create_demo_review_report() -> ReviewReport:
    """创建演示用的质量审查报告"""
    return ReviewReport(
        formal_compliance=ReviewResult(
            passed=True,
            score=0.95,
            issues=[
                ReviewIssue(
                    issue_id="F001",
                    severity=Severity.LOW,
                    location="摘要",
                    issue_type="字数建议",
                    description="摘要字数偏少（150字），建议补充至200-300字以涵盖更多技术细节",
                    suggestion="补充关于动态知识图谱增量更新的技术效果描述",
                ),
            ],
        ),
        claims_review=ReviewResult(
            passed=True,
            score=0.88,
            issues=[
                ReviewIssue(
                    issue_id="C001",
                    severity=Severity.MEDIUM,
                    location="权利要求1",
                    issue_type="术语定义",
                    description="统一语义向量空间的定义在说明书中可进一步明确",
                    suggestion="在说明书具体实施方式中补充向量维度、编码方式等细节",
                ),
            ],
        ),
        description_review=ReviewResult(
            passed=True,
            score=0.90,
            issues=[],
        ),
        consistency_review=ReviewResult(
            passed=True,
            score=0.92,
            issues=[],
        ),
        prior_art_risk=ReviewResult(
            passed=True,
            score=0.85,
            issues=[
                ReviewIssue(
                    issue_id="P001",
                    severity=Severity.MEDIUM,
                    location="权利要求1",
                    issue_type="现有技术风险",
                    description="多模态编码器是较为常见的技术手段，建议在实施例中补充具体算法参数和创新点",
                    suggestion="补充编码器的具体层数、注意力头数等参数，突出与现有技术的区别",
                ),
            ],
        ),
        overall_score=0.90,
        recommendation="approve",
        revision_priority=Severity.LOW,
        estimated_office_action_risk=0.25,
        examiner_comments=[
            "整体质量良好，权利要求保护范围清晰",
            "建议补充实施例的对比实验数据",
            "建议补充附图说明",
        ],
        improvement_suggestions=[
            "补充附图说明部分",
            "增加更多实施例和对比实验",
            "在权利要求中进一步限定算法细节",
        ],
        reviewed_at=datetime.now(),
    )


def save_demo_data():
    """保存演示数据到JSON文件"""
    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)

    data = {
        "requirement_doc": create_demo_requirement_doc().dict(),
        "retrieval_report": create_demo_retrieval_report().dict(),
        "patent_draft": create_demo_patent_draft().dict(),
        "review_report": create_demo_review_report().dict(),
    }

    with open(output_dir / "demo_full_pipeline.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    print(f"✅ 演示数据已保存到: {output_dir / 'demo_full_pipeline.json'}")
    return data


if __name__ == "__main__":
    print("=" * 60)
    print("  专利智脑 - 演示数据生成")
    print("=" * 60)
    save_demo_data()
    print("\n包含内容:")
    print("  ✅ 需求分析文档")
    print("  ✅ 专利性检索分析报告")
    print("  ✅ 专利申请文件草稿")
    print("  ✅ 质量审查报告")
    print("\n可用于前端页面的效果演示！")
