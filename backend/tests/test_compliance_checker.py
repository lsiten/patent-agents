import json

import pytest

from src.agents.hermes.tools.compliance_checker import ComplianceCheckerTool


@pytest.mark.asyncio
async def test_compliance_checker_reads_nested_draft_drawings(tmp_path):
    drawing_paths = []
    for index in range(1, 5):
        path = tmp_path / f"fig{index}.png"
        path.write_bytes(f"real-drawing-{index}".encode("utf-8"))
        drawing_paths.append(path)

    draft = {
        "title": "一种显示内容协同适配的方法及系统",
        "claims": {
            "independent_claim": (
                "1. 一种显示内容协同适配的方法，包括：\n"
                "S1 获取调节依据；\n"
                "S2 确定目标屏幕姿态；\n"
                "S3 控制显示单元调节；\n"
                "S4 生成适配显示内容。\n"
            ),
            "dependent_claims": ["2. 根据权利要求1所述的方法，其中，所述调节依据包括用户位置。"],
        },
        "description": {
            "technical_field": "本申请涉及显示控制技术领域。",
            "background_art": (
                "现有多屏显示技术可对多个显示面进行同步输出。\n"
                "公开资料显示，多显示面之间存在边界错位和内容遮挡问题。\n"
                "因此，现有技术需要解决姿态变化时显示内容连续性不足的问题。"
            ),
            "summary_of_invention": "本申请解决显示单元姿态变化后内容连续性不足的技术问题。",
            "drawings_description": "图1为系统结构示意图。图2为方法流程图。图3为姿态调节示意图。图4为内容适配示意图。",
            "detailed_description": "如图1至图4所示，S1获取调节依据，S2确定目标屏幕姿态，S3控制显示单元调节，S4生成适配显示内容。可以理解的是，需要说明的是，上述步骤可以由处理器执行。",
        },
        "abstract": "本申请涉及显示控制技术领域，提供一种显示内容协同适配的方法及系统，包括获取调节依据、确定目标屏幕姿态、控制显示单元调节并生成适配显示内容，从而保持画面连续性。",
        "drawings": [
            {
                "figure_number": f"图{index}",
                "title": f"图{index}示意图",
                "file_path": str(path),
            }
            for index, path in enumerate(drawing_paths, start=1)
        ],
    }
    review_package = {
        "patent_draft": draft,
        "drawing_file_validation": {
            "items": [
                {"figure_number": f"图{index}", "file_path": str(path)}
                for index, path in enumerate(drawing_paths, start=1)
            ]
        },
    }

    result = await ComplianceCheckerTool().execute(json.dumps(review_package, ensure_ascii=False))

    assert result["success"] is True
    manual_report = result["data"]["manual_rule_report"]
    assert manual_report["metrics"]["drawing_count"] == 4
    assert not any("未生成对应附图文件" in issue["issue"] for issue in manual_report["issues"])
    assert not any("缺少对应附图文件" in issue["issue"] for issue in manual_report["issues"])
