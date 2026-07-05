"""
Claim Drafter Tool - 权利要求撰写工具
帮助专利撰写 Agent 生成高质量权利要求书
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)


def _split_features(features: str) -> list[str]:
    items = []
    for part in re.split(r"[\n；;、,，]+", features or ""):
        clean = part.strip(" -0123456789.）)")
        if len(clean) >= 4:
            items.append(clean[:80])
    return items


CLAIM_TYPE_PATTERNS = {
    "parameter_refinement": {
        "description": "参数细化型从权",
        "pattern": "在独立权利要求基础上细化具体参数、阈值、范围或取值条件",
        "example": "所述采样频率为10Hz至100Hz；所述光源发光强度为50至500流明。",
    },
    "alternative_impl": {
        "description": "替代实现型从权",
        "pattern": "提供技术特征的替代实现方式或等效方案",
        "example": "所述光学传感器可替换为光电二极管、光电三极管或CMOS图像传感器。",
    },
    "combination": {
        "description": "组合特征型从权",
        "pattern": "将多个独立技术特征进行特定组合，形成协同效果",
        "example": "所述运动状态信息与心率光信号采用融合算法进行联合处理。",
    },
    "risk_mitigation": {
        "description": "风险规避型从权",
        "pattern": "针对潜在侵权风险或新颖性缺陷，增加限定特征",
        "example": "所述运动状态信息由加速度计和陀螺仪共同获取，其中加速度计采样频率高于陀螺仪。",
    },
    "structural_detail": {
        "description": "结构细节型从权",
        "pattern": "补充装置或系统的具体结构、连接关系、布局方式",
        "example": "所述多个发光二极管以环形阵列方式均匀分布在传感器探头周围。",
    },
    "processing_step": {
        "description": "处理步骤型从权",
        "pattern": "细化核心处理步骤的具体操作、算法逻辑或处理流程",
        "example": "所述对心率光信号进行处理包括：滤波去噪、峰值检测、信号归一化和心率计算四个子步骤。",
    },
}


def _generate_drafting_materials(topic: str, claim_type: str) -> Dict[str, str]:
    materials = {
        "parameter_ranges": "",
        "alternative_implementations": "",
        "sub_steps": "",
        "structural_details": "",
        "combination_ways": "",
        "risk_mitigation_features": "",
    }
    
    if "运动" in topic or "状态" in topic or "传感器" in topic:
        materials["parameter_ranges"] = "采样频率10Hz至100Hz；加速度阈值0.5g至5g；角速度范围0至360度/秒；数据更新周期10ms至100ms"
        materials["alternative_implementations"] = "可替代采用IMU惯性测量单元、光学追踪系统、压力传感器或GPS定位模块获取"
        materials["sub_steps"] = "包括：数据采集；信号滤波；特征提取；状态识别；结果输出"
    
    if "心率" in topic or "光信号" in topic or "检测" in topic:
        materials["parameter_ranges"] = "光源发光强度50至500流明；采样频率20Hz至200Hz；信号增益10dB至60dB；检测波长500nm至900nm"
        materials["alternative_implementations"] = "可替代采用光电二极管、光电三极管、CMOS图像传感器或PPG光电容积脉搏波传感器"
        materials["sub_steps"] = "包括：滤波去噪；峰值检测；信号归一化；心率计算；质量评估"
        materials["combination_ways"] = "与运动状态信息采用加权融合算法进行联合处理，权重系数根据运动强度动态调整"
    
    if "光学" in topic or "光源" in topic or "二极管" in topic:
        materials["parameter_ranges"] = "发光波长600nm至900nm；相邻元件间距2mm至5mm；驱动电流10mA至100mA；发光角度15度至60度"
        materials["structural_details"] = "以环形阵列方式均匀分布，圆心与检测区域重合，阵列直径8mm至15mm"
        materials["alternative_implementations"] = "可替代采用激光二极管、有机发光二极管OLED或垂直腔面发射激光器VCSEL"
    
    if "算法" in topic or "处理" in topic or "计算" in topic:
        materials["sub_steps"] = "包括：预处理；特征提取；模式匹配；决策判断；后处理"
        materials["parameter_ranges"] = "算法迭代次数10至100次；收敛阈值1e-6至1e-3；计算精度16位至32位"
    
    if "智能手表" in topic or "装置" in topic or "系统" in topic:
        materials["structural_details"] = "传感器模块设置在表带内侧靠近手腕脉搏处，处理器模块位于表体中央，通信模块支持蓝牙5.0及以上版本"
        materials["combination_ways"] = "各模块通过柔性电路板连接，电源模块为传感器和处理器提供独立供电"
    
    if claim_type == "parameter_refinement" and not materials["parameter_ranges"]:
        materials["parameter_ranges"] = "相关参数取值范围根据实际应用场景合理设定，通常包含至少两个数量级的调节空间"
    
    if claim_type == "alternative_impl" and not materials["alternative_implementations"]:
        materials["alternative_implementations"] = "可采用本领域技术人员熟知的其他等效实现方式"
    
    if claim_type == "processing_step" and not materials["sub_steps"]:
        materials["sub_steps"] = "包括多个子步骤，每个子步骤执行特定的操作或处理逻辑"
    
    if claim_type == "combination" and not materials["combination_ways"]:
        materials["combination_ways"] = "与其他相关技术特征进行协同处理或联合控制"
    
    if claim_type == "structural_detail" and not materials["structural_details"]:
        materials["structural_details"] = "具有特定的结构布局和连接关系，以实现预期的技术效果"
    
    return materials


def _assign_claim_types(feature_list: List[str]) -> List[Dict[str, str]]:
    type_order = ["parameter_refinement", "alternative_impl", "processing_step", "combination", "structural_detail", "risk_mitigation"]
    assigned = []
    for idx, feature in enumerate(feature_list[:10], start=2):
        type_key = type_order[(idx - 2) % len(type_order)]
        pattern_info = CLAIM_TYPE_PATTERNS[type_key]
        materials = _generate_drafting_materials(feature, type_key)
        assigned.append({
            "claim_number": idx,
            "topic": feature,
            "claim_type": type_key,
            "type_description": pattern_info["description"],
            "writing_pattern": pattern_info["pattern"],
            "example": pattern_info["example"],
            "drafting_materials": materials,
        })
    return assigned


def _build_hierarchical_dependencies(feature_list: List[str]) -> Dict[str, List[str]]:
    dependencies = {"1": []}
    max_claims = min(len(feature_list), 10)
    
    for i in range(2, max_claims + 2):
        if i == 2:
            dependencies[str(i)] = ["1"]
        elif i <= 5:
            dependencies[str(i)] = ["1", str(i - 1)]
        elif i <= 8:
            dependencies[str(i)] = ["1", str(i - 2), str(i - 1)]
        else:
            dependencies[str(i)] = ["1", str(i - 3), str(i - 1)]
    
    return dependencies


class ClaimDrafterTool(HermesTool):
    """权利要求撰写工具"""
    name = "claim_drafter"
    description = "根据技术特征生成权利要求撰写骨架和特征组织建议"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "features": HermesToolParameter(
                    type="string",
                    description="技术特征列表或描述",
                    required=True,
                ),
                "protection_scope": HermesToolParameter(
                    type="string",
                    description="期望的保护范围说明",
                    required=False,
                ),
            },
        )

    async def execute(
        self, features: str, protection_scope: str = "尽可能宽泛", **kwargs
    ) -> Dict[str, Any]:
        """生成权利要求结构骨架；正式权利要求正文由专利撰写 Agent LLM 完成。"""
        start_time = datetime.now()
        logger.info("Drafting patent claims")

        try:
            feature_list = _split_features(features)
            if not feature_list:
                return make_tool_output(
                    tool_name=self.name,
                    data={
                        "objective_findings": [
                            {
                                "issue_type": "input_missing",
                                "description": "claim_drafter 未收到可识别的当前发明技术特征",
                                "suggestion": "由专利撰写 Agent 基于需求分析和检索报告提炼真实技术特征后重新调用。",
                            }
                        ]
                    },
                    success=False,
                    error="缺少当前发明技术特征，不能使用默认权利要求骨架。",
                    start_time=start_time,
                )

            claim_types = _assign_claim_types(feature_list)
            hierarchical_deps = _build_hierarchical_dependencies(feature_list)

            data = {
                "claim_outline": {
                    "independent_claim_focus": [
                        "以方法独立权利要求按3步或4步覆盖输入获取、核心处理、结果输出等必要技术特征。",
                        "以系统/装置权利要求覆盖与方法步骤对应的功能模块或结构单元。",
                        "是否需要其他权利要求类型由专利撰写 Agent 结合已确认事实和申请策略判断。",
                    ],
                    "dependent_claim_topics": feature_list[:10],
                    "claim_dependency_plan": hierarchical_deps,
                    "dependent_claim_types": claim_types,
                    "dependent_claim_patterns": {
                        "parameter_refinement": {
                            "description": "参数细化型",
                            "usage": "用于限定具体数值范围、阈值条件、参数配置，提高权利要求的确定性",
                            "structure": "根据权利要求N所述的……，其特征在于，所述[技术特征]的[参数]为[范围/条件]；",
                            "example": "根据权利要求1所述的心率检测方法，其特征在于，所述采样频率为10Hz至100Hz；所述光源发光强度为50至500流明。",
                        },
                        "alternative_impl": {
                            "description": "替代实现型",
                            "usage": "用于提供同一技术特征的多种替代方案，扩大保护范围的覆盖度",
                            "structure": "根据权利要求N所述的……，其特征在于，所述[技术特征]包括[替代方案1]、[替代方案2]或[替代方案3]；",
                            "example": "根据权利要求3所述的心率检测方法，其特征在于，所述光学传感器包括光电二极管、光电三极管或CMOS图像传感器。",
                        },
                        "processing_step": {
                            "description": "处理步骤型",
                            "usage": "用于细化核心处理步骤的具体操作逻辑、算法流程或子步骤",
                            "structure": "根据权利要求N所述的……，其特征在于，所述[处理步骤]包括：[子步骤1]；[子步骤2]；[子步骤3]；",
                            "example": "根据权利要求1所述的心率检测方法，其特征在于，所述对心率光信号进行处理包括：滤波去噪；峰值检测；信号归一化；心率计算。",
                        },
                        "combination": {
                            "description": "组合特征型",
                            "usage": "用于将多个技术特征进行特定组合，形成协同效果或限定组合方式",
                            "structure": "根据权利要求N所述的……，其特征在于，所述[特征A]与所述[特征B]按照[组合方式]进行协同[处理/控制/操作]；",
                            "example": "根据权利要求2所述的心率检测方法，其特征在于，所述运动状态信息与所述心率光信号采用加权融合算法进行联合处理。",
                        },
                        "structural_detail": {
                            "description": "结构细节型",
                            "usage": "用于补充装置或系统的具体结构、连接关系、布局方式或物理形态",
                            "structure": "根据权利要求N所述的……，其特征在于，所述[结构部件]以[布局方式]设置，且[连接关系/技术效果]；",
                            "example": "根据权利要求8所述的智能手表，其特征在于，所述多个发光二极管以环形阵列方式均匀分布在传感器探头周围，相邻发光二极管之间的间距为2mm至5mm。",
                        },
                        "risk_mitigation": {
                            "description": "风险规避型",
                            "usage": "用于针对潜在侵权风险或新颖性缺陷，增加特定限定特征",
                            "structure": "根据权利要求N所述的……，其特征在于，所述[技术特征]进一步满足[限定条件]，以[技术效果]；",
                            "example": "根据权利要求6所述的心率检测方法，其特征在于，所述运动状态信息由加速度计和陀螺仪共同获取，其中加速度计采样频率高于陀螺仪采样频率，以提高运动状态识别精度。",
                        },
                    },
                    "dependency_strategy": {
                        "level_1": "直接引用权利要求1，对独立权利要求的某一技术特征进行直接限定",
                        "level_2": "引用权利要求1和上一条从权，在上一条从权基础上进一步细化",
                        "level_3": "引用权利要求1和多条相关从权，形成组合限定",
                        "guidance": "优先采用递进式引用（权3引权2，权4引权3），而非全部引用权1，以构建多层次保护网",
                    },
                },
                "protection_breadth": protection_scope,
                "drafting_notes": (
                    "工具仅提供结构骨架、特征顺序、保护层级和撰写模式建议；"
                    "正式权利要求文本必须由专利撰写 Agent 的 LLM 自行判断并输出。"
                    "从属权利要求应按参数细化→替代实现→处理步骤→组合特征→结构细节→风险规避的顺序递进，"
                    "并采用分层引用策略构建多层次保护网。"
                ),
                "features_used": feature_list,
            }

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=json.dumps(data, ensure_ascii=False),
                start_time=start_time,
            )

        except Exception as e:
            logger.error(f"Claim drafting failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
