from __future__ import annotations

import json

import pytest

from src.core import workflow_engine as workflow_module
from src.core.workflow_engine import PatentWorkflowEngine, WorkflowState
from src.agents import agent_config


@pytest.mark.asyncio
async def test_generate_patent_in_sections_parses_tool_output_with_saved_file_marker(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="tool-marker-draft",
        user_id="test-user",
        description="一种可根据用户身高调整屏幕角度并补偿多屏画面的沉浸式显示系统。",
    )

    claim_result = {
        "tool": "claim_drafter",
        "success": True,
        "data": {
            "independent_claim": "1. 一种沉浸式显示空间自适应调节系统，包括身高检测模块、可调屏幕组件和显示补偿模块。",
            "dependent_claims": ["2. 根据权利要求1所述的系统，其中所述可调屏幕组件通过转轴向内或向外转动。"],
        },
    }
    description_result = {
        "tool": "description_writer",
        "success": True,
        "data": {
            "section_type": "technical_field",
            "content": "本发明涉及沉浸式多屏显示控制技术领域。",
        },
    }

    async def fake_run_agent_conversation(profile_id, prompt):
        return {
            "final_response": "工具调用完成",
            "messages": [
                {
                    "role": "tool",
                    "name": "claim_drafter",
                    "content": json.dumps(claim_result, ensure_ascii=False)
                    + "\n\n[TOOL_OUTPUT_SAVED_TO]: /tmp/claim.json",
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(description_result, ensure_ascii=False)
                    + "\n\n[TOOL_OUTPUT_SAVED_TO]: /tmp/description.json",
                },
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert draft["claims"]["independent_claim"].startswith("1. 一种沉浸式显示空间")
    assert draft["claims"]["dependent_claims"]
    assert draft["description"]["technical_field"] == "本发明涉及沉浸式多屏显示控制技术领域。"
    assert draft.get("_agent_failed") is not True


@pytest.mark.asyncio
async def test_generate_patent_in_sections_preserves_agent_tool_messages(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="agent-result-tool-messages",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )

    claim_result = {
        "tool": "claim_drafter",
        "success": True,
        "data": {
            "independent_claim": "1. 一种Cave折幕视频处理方法，包括入口预配置屏幕姿态并重映射跨屏视频画面。",
            "dependent_claims": ["2. 根据权利要求1所述的方法，其中基于虚拟空间模型生成屏幕角度。"],
        },
    }
    description_result = {
        "tool": "description_writer",
        "success": True,
        "data": {
            "section_type": "technical_field",
            "content": "本发明涉及沉浸式折幕显示视频处理技术领域。",
        },
    }

    class FakeAgent:
        def run_conversation(self, prompt):
            return {
                "final_response": "专利内容已按要求通过工具生成。\n\n1. 权利要求书 `/tmp/claim.json`\n2. 技术领域 `/tmp/description.json`",
                "messages": [
                    {
                        "role": "tool",
                        "name": "claim_drafter",
                        "content": json.dumps(claim_result, ensure_ascii=False),
                    },
                    {
                        "role": "tool",
                        "name": "description_writer",
                        "content": json.dumps(description_result, ensure_ascii=False),
                    },
                ],
            }

    monkeypatch.setattr(agent_config, "create_ai_agent", lambda profile_id, session_id=None: FakeAgent())

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert draft["claims"]["independent_claim"].startswith("1. 一种Cave折幕视频处理方法")
    assert draft["claims"]["dependent_claims"]
    assert draft["description"]["technical_field"] == "本发明涉及沉浸式折幕显示视频处理技术领域。"


@pytest.mark.asyncio
async def test_generate_patent_in_sections_recovers_tool_messages_without_name(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="agent-result-tool-call-ids",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )

    claim_result = {
        "tool": "claim_drafter",
        "success": True,
        "data": {
            "independent_claim": "1. 一种Cave折幕空间视频补偿方法，包括获取相邻屏幕空间关系并识别补充处理区域。",
            "dependent_claims": ["2. 根据权利要求1所述的方法，其中基于相邻屏幕边界计算空间间隙。"],
        },
    }
    description_result = {
        "tool": "description_writer",
        "success": True,
        "data": {
            "section_type": "summary",
            "content": "系统根据姿态变化量及相邻屏幕的空间关系识别画面处理区域，避免补偿内容缺失。",
        },
    }

    async def fake_run_agent_conversation(profile_id, prompt):
        return {
            "final_response": "或者",
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "call_claim", "function": {"name": "claim_drafter", "arguments": "{}"}},
                        {"id": "call_summary", "function": {"name": "description_writer", "arguments": "{}"}},
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_claim",
                    "content": json.dumps(claim_result, ensure_ascii=False),
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_summary",
                    "content": json.dumps(description_result, ensure_ascii=False),
                },
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert draft["claims"]["independent_claim"].startswith("1. 一种Cave折幕空间视频补偿方法")
    assert draft["description"]["summary_of_invention"] == "系统根据姿态变化量及相邻屏幕的空间关系识别画面处理区域，避免补偿内容缺失。"
    assert draft["full_response"] == "或者"


@pytest.mark.asyncio
async def test_generate_patent_in_sections_collects_drawing_tool_output(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="agent-result-drawing-tool-call",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )

    claim_result = {
        "tool": "claim_drafter",
        "success": True,
        "data": {
            "independent_claim": "1. 一种Cave折幕空间视频补偿方法，包括获取相邻屏幕空间关系并识别补充处理区域。",
            "dependent_claims": ["2. 根据权利要求1所述的方法，其中基于相邻屏幕边界计算空间间隙。"],
        },
    }
    expected_drawings = [
        {
            "figure_number": "图1",
            "title": "Cave折幕空间视频补偿系统结构示意图",
            "description": "展示入口终端、姿态控制模块、相邻屏幕和视频补偿模块之间的连接关系。",
            "file_path": "/tmp/agent-result-drawing-tool-call/draft/drawings/fig1.png",
            "artifact_url": "/api/v1/workflows/agent-result-drawing-tool-call/artifacts/draft/drawings/fig1.png",
            "mime_type": "image/png",
        }
    ]
    drawing_result = {
        "tool": "patent_drawing_generator",
        "success": True,
        "data": {"drawings": expected_drawings},
    }

    async def fake_run_agent_conversation(profile_id, prompt):
        return {
            "final_response": "工具调用完成",
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "call_claim", "function": {"name": "claim_drafter", "arguments": "{}"}},
                        {"id": "call_drawing", "function": {"name": "patent_drawing_generator", "arguments": "{}"}},
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_claim",
                    "content": json.dumps(claim_result, ensure_ascii=False),
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_drawing",
                    "content": json.dumps(drawing_result, ensure_ascii=False),
                },
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert draft["drawings"] == expected_drawings


@pytest.mark.asyncio
async def test_generate_patent_in_sections_requests_drawing_generation(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-prompt-drawing-tool",
        user_id="test-user",
        description="一种包含入口终端、姿态控制模块和可调折幕组件的沉浸式显示系统。",
    )
    captured = {}

    async def fake_run_agent_conversation(profile_id, prompt):
        captured["prompt"] = prompt
        return {
            "final_response": "工具调用完成",
            "messages": [
                {
                    "role": "tool",
                    "name": "claim_drafter",
                    "content": json.dumps(
                        {
                            "tool": "claim_drafter",
                            "success": True,
                            "data": {
                                "independent_claim": "1. 一种沉浸式显示系统，包括入口终端和可调折幕组件。",
                                "dependent_claims": ["2. 根据权利要求1所述的系统，其中可调折幕组件包括驱动机构。"],
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert "patent_drawing_generator" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_patent_in_sections_preserves_drawings_description(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-drawings-description",
        user_id="test-user",
        description="一种包含入口终端、姿态控制模块和可调折幕组件的沉浸式显示系统。",
    )

    async def fake_run_agent_conversation(profile_id, prompt):
        return {
            "final_response": "工具调用完成",
            "messages": [
                {
                    "role": "tool",
                    "name": "claim_drafter",
                    "content": json.dumps(
                        {
                            "tool": "claim_drafter",
                            "success": True,
                            "data": {
                                "independent_claim": "1. 一种沉浸式显示系统，包括入口终端和可调折幕组件。",
                                "dependent_claims": ["2. 根据权利要求1所述的系统，其中可调折幕组件包括驱动机构。"],
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "drawings",
                                "content": "图1为沉浸式显示系统的结构示意图。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert draft["description"]["drawings_description"] == "图1为沉浸式显示系统的结构示意图。"


@pytest.mark.asyncio
async def test_generate_patent_in_sections_preserves_agent_failure(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-agent-truncated",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )

    async def fake_run_agent_conversation(profile_id, prompt):
        return {
            "failed": True,
            "error": "Response truncated due to output length limit",
            "completed": False,
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert draft["_agent_failed"] is True
    assert draft["_agent_error"] == "Response truncated due to output length limit"
    assert draft["claims"]["independent_claim"] == ""
    assert draft["description"]["technical_field"] == ""
    assert draft["abstract"] == ""


@pytest.mark.asyncio
async def test_generate_patent_in_sections_resumes_partial_failed_output(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-resume-partial",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )
    prompts = []

    claim_result = {
        "tool": "claim_drafter",
        "success": True,
        "data": {
            "independent_claim": "1. 一种Cave折幕视频处理方法，包括入口预配置屏幕姿态并重映射跨屏视频画面。",
            "dependent_claims": ["2. 根据权利要求1所述的方法，其中基于虚拟空间模型生成屏幕角度。"],
        },
    }
    technical_field_result = {
        "tool": "description_writer",
        "success": True,
        "data": {
            "section_type": "technical_field",
            "content": "本发明涉及沉浸式折幕显示视频处理技术领域。",
        },
    }

    async def fake_run_agent_conversation(profile_id, prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            return {
                "failed": True,
                "error": "说明书生成到背景技术时响应截断",
                "completed": False,
                "messages": [
                    {
                        "role": "tool",
                        "name": "claim_drafter",
                        "content": json.dumps(claim_result, ensure_ascii=False),
                    },
                    {
                        "role": "tool",
                        "name": "description_writer",
                        "content": json.dumps(technical_field_result, ensure_ascii=False),
                    },
                ],
            }

        assert "说明书生成到背景技术时响应截断" in prompt
        assert "不要重新生成权利要求书" in prompt
        assert "技术领域已完成" in prompt
        return {
            "final_response": "继续补全剩余说明书章节",
            "messages": [
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "background",
                                "content": "现有Cave折幕显示空间难以根据入口姿态预配置跨屏画面。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "summary",
                                "content": "系统根据入口预配置屏幕姿态重映射跨屏画面。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "detailed",
                                "content": "入口终端获取空间配置后，生成折幕姿态参数并对跨屏视频画面进行重映射。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "patent_docx_generator",
                    "content": json.dumps(
                        {
                            "tool": "patent_docx_generator",
                            "success": True,
                            "data": {
                                "file_path": "",
                                "abstract": "本发明公开一种Cave折幕视频处理方法，可预配置屏幕姿态并重映射跨屏视频画面。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert len(prompts) == 2
    assert draft.get("_agent_failed") is not True
    assert draft["claims"]["independent_claim"].startswith("1. 一种Cave折幕视频处理方法")
    assert draft["description"]["technical_field"] == "本发明涉及沉浸式折幕显示视频处理技术领域。"
    assert draft["description"]["background_art"] == "现有Cave折幕显示空间难以根据入口姿态预配置跨屏画面。"
    assert draft["description"]["summary_of_invention"] == "系统根据入口预配置屏幕姿态重映射跨屏画面。"
    assert draft["description"]["detailed_description"] == "入口终端获取空间配置后，生成折幕姿态参数并对跨屏视频画面进行重映射。"
    assert draft["abstract"].startswith("本发明公开一种Cave折幕视频处理方法")


@pytest.mark.asyncio
async def test_generate_patent_in_sections_retries_successful_but_incomplete_output(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-successful-incomplete-output",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )
    prompts = []

    async def fake_run_agent_conversation(profile_id, prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            return {
                "final_response": "请提供已完成章节，以便仅补全权利要求书和说明书摘要。",
                "messages": [
                    {
                        "role": "tool",
                        "name": "description_writer",
                        "content": json.dumps(
                            {
                                "tool": "description_writer",
                                "success": True,
                                "data": {
                                    "section_type": "technical_field",
                                    "content": "本发明涉及沉浸式折幕显示视频处理技术领域。",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "role": "tool",
                        "name": "description_writer",
                        "content": json.dumps(
                            {
                                "tool": "description_writer",
                                "success": True,
                                "data": {
                                    "section_type": "background",
                                    "content": "现有Cave折幕显示空间难以根据入口姿态预配置跨屏画面。",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "role": "tool",
                        "name": "description_writer",
                        "content": json.dumps(
                            {
                                "tool": "description_writer",
                                "success": True,
                                "data": {
                                    "section_type": "summary",
                                    "content": "系统根据入口预配置屏幕姿态重映射跨屏画面。",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "role": "tool",
                        "name": "description_writer",
                        "content": json.dumps(
                            {
                                "tool": "description_writer",
                                "success": True,
                                "data": {
                                    "section_type": "detailed",
                                    "content": "入口终端获取空间配置后，生成折幕姿态参数并对跨屏视频画面进行重映射。",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            }

        return {
            "final_response": "已补全缺失内容。",
            "messages": [
                {
                    "role": "tool",
                    "name": "claim_drafter",
                    "content": json.dumps(
                        {
                            "tool": "claim_drafter",
                            "success": True,
                            "data": {
                                "independent_claim": "1. 一种Cave折幕视频处理方法，包括入口预配置屏幕姿态并重映射跨屏视频画面。",
                                "dependent_claims": ["2. 根据权利要求1所述的方法，其中基于虚拟空间模型生成屏幕角度。"],
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "patent_docx_generator",
                    "content": json.dumps(
                        {
                            "tool": "patent_docx_generator",
                            "success": True,
                            "data": {
                                "file_path": "",
                                "abstract": "本发明公开一种Cave折幕视频处理方法，可预配置屏幕姿态并重映射跨屏视频画面。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert len(prompts) == 2
    assert "权利要求书" in prompts[1]
    assert "说明书摘要" in prompts[1]
    assert draft.get("_agent_failed") is not True
    assert draft["claims"]["independent_claim"].startswith("1. 一种Cave折幕视频处理方法")
    assert draft["description"]["technical_field"] == "本发明涉及沉浸式折幕显示视频处理技术领域。"
    assert draft["description"]["background_art"] == "现有Cave折幕显示空间难以根据入口姿态预配置跨屏画面。"
    assert draft["description"]["summary_of_invention"] == "系统根据入口预配置屏幕姿态重映射跨屏画面。"
    assert draft["description"]["detailed_description"] == "入口终端获取空间配置后，生成折幕姿态参数并对跨屏视频画面进行重映射。"
    assert draft["abstract"].startswith("本发明公开一种Cave折幕视频处理方法")


@pytest.mark.asyncio
async def test_generate_patent_in_sections_preserves_partial_output_when_resume_fails(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-resume-still-fails",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )
    prompts = []

    claim_result = {
        "tool": "claim_drafter",
        "success": True,
        "data": {
            "independent_claim": "1. 一种Cave折幕视频处理方法，包括入口预配置屏幕姿态并重映射跨屏视频画面。",
            "dependent_claims": ["2. 根据权利要求1所述的方法，其中基于虚拟空间模型生成屏幕角度。"],
        },
    }

    async def fake_run_agent_conversation(profile_id, prompt):
        prompts.append(prompt)
        return {
            "failed": True,
            "error": "说明书生成连续截断",
            "completed": False,
            "messages": [
                {
                    "role": "tool",
                    "name": "claim_drafter",
                    "content": json.dumps(claim_result, ensure_ascii=False),
                }
            ],
        }

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    draft = await engine._generate_patent_in_sections(None, "patent.writer.v1", "", context)

    assert len(prompts) == 3
    assert draft["_agent_failed"] is True
    assert draft["_agent_error"] == "说明书生成连续截断"
    assert draft["claims"]["independent_claim"].startswith("1. 一种Cave折幕视频处理方法")
    assert draft["claims"]["dependent_claims"]
    assert draft["description"]["technical_field"] == ""


@pytest.mark.asyncio
async def test_execute_full_workflow_marks_truncated_writer_stage_failed(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-truncated-phase-failure",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )

    async def fake_publish_progress_event(context, phase, status, result=None):
        return None

    async def fake_sleep(delay):
        return None

    async def fake_run_agent_stream(service, profile_id, task_desc, context, agent_name, event_callback=None):
        if profile_id == "patent.requirement_analyst.v1":
            return {
                "text": json.dumps(
                    {
                        "tech_field": "沉浸式显示",
                        "core_principle": "入口预配置屏幕姿态并补偿跨屏画面",
                        "technical_problem": "折幕空间固定屏幕难以适配不同体验者",
                        "key_innovative_features": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_results": [],
            }
        if profile_id == "patent.retrieval_analyst.v1":
            return {
                "text": json.dumps(
                    {
                        "overall_patentability": "unknown",
                        "writing_recommendations": ["突出入口预配置和跨屏补偿"],
                        "prior_art_references": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_results": [],
            }
        raise AssertionError("quality reviewer should not run after truncated writer output")

    writer_attempts = 0

    async def fake_run_agent_conversation(profile_id, prompt):
        nonlocal writer_attempts
        assert profile_id == "patent.writer.v1"
        writer_attempts += 1
        return {
            "failed": True,
            "error": "Response truncated due to output length limit",
            "completed": False,
        }

    monkeypatch.setattr(engine, "_publish_progress_event", fake_publish_progress_event)
    monkeypatch.setattr(engine, "_run_agent_stream", fake_run_agent_stream)
    monkeypatch.setattr(workflow_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    result = await engine.execute_full_workflow(context)

    assert result.current_phase == WorkflowState.FAILED
    writing_phase = next(p for p in result.phase_history if p.phase.value == "writing")
    assert writing_phase.success is False
    assert writing_phase.output["_agent_failed"] is True
    assert writing_phase.issues == ["Response truncated due to output length limit"]
    assert writer_attempts == 3
    assert all(p.phase.value != "review" for p in result.phase_history)


@pytest.mark.asyncio
async def test_execute_full_workflow_retries_writer_agent_failure(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-retry-recovers",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )
    writer_attempts = 0

    async def fake_publish_progress_event(context, phase, status, result=None):
        return None

    async def fake_sleep(delay):
        return None

    async def fake_run_agent_stream(service, profile_id, task_desc, context, agent_name, event_callback=None):
        if profile_id == "patent.requirement_analyst.v1":
            return {
                "text": json.dumps(
                    {
                        "tech_field": "沉浸式显示",
                        "core_principle": "入口预配置屏幕姿态并补偿跨屏画面",
                        "technical_problem": "折幕空间固定屏幕难以适配不同体验者",
                        "key_innovative_features": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_results": [],
            }
        if profile_id == "patent.retrieval_analyst.v1":
            return {
                "text": json.dumps(
                    {
                        "overall_patentability": "unknown",
                        "writing_recommendations": ["突出入口预配置和跨屏补偿"],
                        "prior_art_references": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_results": [],
            }
        if profile_id == "patent.quality_reviewer.v1":
            return {
                "text": json.dumps(
                    {
                        "recommendation": "approve",
                        "revision_priority": "low",
                        "review_summary": {"recommendation": "approve", "overall_rating": "good"},
                        "formal_compliance_review": {"issues": []},
                        "claims_review": {"issues": []},
                        "description_review": {"issues": []},
                        "consistency_review": {"issues": []},
                        "examination_risks": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_results": [],
            }
        raise AssertionError(f"unexpected profile {profile_id}")

    async def fake_run_agent_conversation(profile_id, prompt):
        nonlocal writer_attempts
        assert profile_id == "patent.writer.v1"
        writer_attempts += 1
        if writer_attempts == 1:
            return {
                "failed": True,
                "error": "Response truncated due to output length limit",
                "completed": False,
            }
        return {
            "final_response": "工具调用完成",
            "messages": [
                {
                    "role": "tool",
                    "name": "claim_drafter",
                    "content": json.dumps(
                        {
                            "tool": "claim_drafter",
                            "success": True,
                            "data": {
                                "independent_claim": "1. 一种Cave折幕视频处理方法，包括入口预配置屏幕姿态并重映射跨屏视频画面。",
                                "dependent_claims": ["2. 根据权利要求1所述的方法，其中基于虚拟空间模型生成屏幕角度。"],
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "technical_field",
                                "content": "本发明涉及沉浸式折幕显示视频处理技术领域。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "background",
                                "content": "现有Cave折幕显示空间难以根据入口姿态预配置跨屏画面。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "summary",
                                "content": "系统根据入口预配置屏幕姿态重映射跨屏画面。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "detailed",
                                "content": "入口终端获取空间配置后，生成折幕姿态参数并对跨屏视频画面进行重映射。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "patent_docx_generator",
                    "content": json.dumps(
                        {
                            "tool": "patent_docx_generator",
                            "success": True,
                            "data": {
                                "file_path": "",
                                "abstract": "本发明公开一种Cave折幕视频处理方法，可预配置屏幕姿态并重映射跨屏视频画面。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

    class FakeDocxGeneratorTool:
        async def execute(self, **kwargs):
            return {"success": True, "file_path": "/tmp/writer-retry-recovers.docx"}

    from src.agents.hermes.tools import patent_docx_generator

    monkeypatch.setattr(engine, "_publish_progress_event", fake_publish_progress_event)
    monkeypatch.setattr(engine, "_run_agent_stream", fake_run_agent_stream)
    monkeypatch.setattr(workflow_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)
    monkeypatch.setattr(patent_docx_generator, "PatentDocxGeneratorTool", FakeDocxGeneratorTool)

    result = await engine.execute_full_workflow(context)

    assert writer_attempts == 2
    assert result.current_phase == WorkflowState.COMPLETED
    writing_phase = next(p for p in result.phase_history if p.phase.value == "writing")
    assert writing_phase.success is True
    assert writing_phase.output.get("_agent_failed") is not True
    assert writing_phase.output["claims"]["independent_claim"].startswith("1. 一种Cave折幕视频处理方法")
    review_phase = next(p for p in result.phase_history if p.phase.value == "review")
    assert review_phase.success is True
    assert review_phase.output["review_summary"]["recommendation"] == "approve"


@pytest.mark.asyncio
async def test_generate_patent_in_sections_emits_realtime_progress_events(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="writer-progress-events",
        user_id="test-user",
        description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
    )
    events = []

    async def fake_run_agent_conversation(profile_id, prompt):
        return {
            "final_response": "工具调用完成",
            "messages": [
                {
                    "role": "tool",
                    "name": "claim_drafter",
                    "content": json.dumps(
                        {
                            "tool": "claim_drafter",
                            "success": True,
                            "data": {
                                "independent_claim": "1. 一种Cave折幕空间视频补偿方法。",
                                "dependent_claims": [],
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "tool",
                    "name": "description_writer",
                    "content": json.dumps(
                        {
                            "tool": "description_writer",
                            "success": True,
                            "data": {
                                "section_type": "technical_field",
                                "content": "本发明涉及沉浸式折幕显示视频处理技术领域。",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

    def record_event(agent_name, event_type, content, metadata):
        events.append((agent_name, event_type, content, metadata))

    monkeypatch.setattr(workflow_module, "_run_agent_conversation", fake_run_agent_conversation)

    await engine._generate_patent_in_sections(
        None,
        "patent.writer.v1",
        "",
        context,
        event_callback=record_event,
    )

    progress_messages = [content for _, event_type, content, _ in events if event_type == "agent.thinking"]
    assert any("权利要求书" in message for message in progress_messages)
    assert any("说明书" in message for message in progress_messages)
    assert any("支持关系" in message for message in progress_messages)


def test_revision_prompt_keeps_source_disclosure_when_draft_is_failed():
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="failed-draft-revision",
        user_id="test-user",
        description="入口处检测体验者身高，并根据身高映射调整Cave折幕屏幕角度。",
    )
    context.requirement_analysis = {
        "core_principle": "基于身高范围与屏幕姿态映射关系生成沉浸式显示形态",
        "technical_problem": "固定折幕空间无法适配不同体验者身高",
    }
    context.retrieval_report = {
        "writing_recommendations": ["突出身高映射、屏幕角度调整和画面补偿的组合"]
    }
    context.patent_draft = {
        "_agent_failed": True,
        "_incomplete_output": True,
        "_raw_output": "请补充技术方案后再生成专利文件",
        "claims": {"independent_claim": "", "dependent_claims": []},
        "description": {},
        "abstract": "",
    }

    prompt = engine._build_revision_prompt(context, ["独立权利要求为空"])

    assert "入口处检测体验者身高" in prompt
    assert "基于身高范围与屏幕姿态映射关系" in prompt
    assert "突出身高映射" in prompt
    assert "当前专利文件生成失败或不完整" in prompt


def test_quality_review_prompt_includes_description_after_long_claims():
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="quality-review-full-draft",
        user_id="test-user",
        description="可调Cave折幕显示系统",
    )
    context.patent_draft = {
        "claims": {
            "independent_claim": "1. 一种可调Cave折幕显示系统，包括" + "屏幕姿态控制模块；" * 120,
            "dependent_claims": [],
        },
        "description": {
            "technical_field": "本发明涉及沉浸式折幕显示技术领域。",
            "background_art": "现有Cave折幕空间屏幕角度固定。",
            "summary_of_invention": "系统根据身高映射调整屏幕姿态并补偿画面。",
            "drawings_description": "图1为系统结构示意图。",
            "detailed_description": "入口检测用户身高后驱动可动屏幕转动。",
        },
        "abstract": "本发明公开一种可调Cave折幕显示系统。",
        "docx_path": "",
    }

    prompt = engine._build_phase_prompt(context, WorkflowState.QUALITY_REVIEW)

    assert "本发明涉及沉浸式折幕显示技术领域" in prompt
    assert "本发明公开一种可调Cave折幕显示系统" in prompt


def test_patent_draft_normalizes_streamed_tool_results_instead_of_docx_envelope():
    engine = PatentWorkflowEngine()
    docx_envelope = {
        "success": True,
        "message": "专利申请文件已完成修正并生成 .docx 文件。",
        "docx_path": "/tmp/generated.docx",
        "file_name": "generated.docx",
        "tool_results": [
            {
                "tool": "claim_drafter",
                "result": json.dumps(
                    {
                        "tool": "claim_drafter",
                        "success": True,
                        "data": {
                            "independent_claim": "1. 一种沉浸式折幕显示空间姿态联动显示控制方法。",
                            "dependent_claims": ["2. 根据权利要求1所述的方法，其中检测体验者身高。"],
                        },
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
            {
                "tool": "description_writer",
                "result": json.dumps(
                    {
                        "tool": "description_writer",
                        "success": True,
                        "data": {
                            "section_type": "technical_field",
                            "content": "本发明涉及沉浸式折幕显示姿态控制技术领域。",
                        },
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
            {
                "tool": "description_writer",
                "result": json.dumps(
                    {
                        "tool": "description_writer",
                        "success": True,
                        "data": {
                            "section_type": "summary",
                            "content": "系统根据体验者身高联动调整折幕姿态并适配显示内容。",
                        },
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
            {
                "tool": "patent_docx_generator",
                "result": json.dumps(
                    {
                        "success": True,
                        "data": {
                            "file_path": "/tmp/generated.docx",
                            "abstract": "本发明公开一种沉浸式折幕显示空间姿态联动显示控制方法。",
                        },
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
        ],
    }

    normalized = engine._normalize_phase_output("patent_draft", docx_envelope)

    assert normalized["claims"]["independent_claim"].startswith("1. 一种沉浸式折幕")
    assert normalized["claims"]["dependent_claims"]
    assert normalized["description"]["technical_field"] == "本发明涉及沉浸式折幕显示姿态控制技术领域。"
    assert normalized["description"]["summary_of_invention"] == "系统根据体验者身高联动调整折幕姿态并适配显示内容。"
    assert normalized["abstract"] == "本发明公开一种沉浸式折幕显示空间姿态联动显示控制方法。"
    assert normalized["docx_path"] == "/tmp/generated.docx"
    assert "tool_results" not in normalized


def test_patent_draft_normalizes_streamed_drawing_tool_results():
    engine = PatentWorkflowEngine()
    drawing = {
        "figure_number": "图1",
        "title": "折幕空间姿态控制系统结构示意图",
        "description": "展示入口终端、姿态控制模块、折幕组件和视频补偿模块的连接关系。",
        "file_path": "/tmp/draft/drawings/fig1.png",
        "artifact_url": "/api/v1/workflows/streamed-drawings/artifacts/draft/drawings/fig1.png",
        "mime_type": "image/png",
    }
    streamed_result = {
        "success": True,
        "message": "工具调用完成",
        "tool_results": [
            {
                "tool": "claim_drafter",
                "result": json.dumps(
                    {
                        "tool": "claim_drafter",
                        "success": True,
                        "data": {
                            "independent_claim": "1. 一种折幕空间姿态控制系统，包括入口终端和姿态控制模块。",
                            "dependent_claims": ["2. 根据权利要求1所述的系统，其中姿态控制模块输出折幕角度。"],
                        },
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
            {
                "tool": "patent_drawing_generator",
                "result": json.dumps(
                    {
                        "tool": "patent_drawing_generator",
                        "success": True,
                        "data": {"drawings": [drawing]},
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
        ],
    }

    normalized = engine._normalize_phase_output("patent_draft", streamed_result)

    assert normalized["drawings"] == [drawing]


@pytest.mark.asyncio
async def test_patent_docx_generator_accepts_structured_text_values():
    from src.agents.hermes.tools.patent_docx_generator import PatentDocxGeneratorTool

    tool = PatentDocxGeneratorTool()

    result = await tool.execute(
        title={"content": "可调式沉浸显示系统及其显示控制方法"},
        claims={
            "independent_claim": {"content": "1. 一种可调式沉浸显示系统，包括入口交互终端和可调显示面。"},
            "dependent_claims": [
                {"content": "2. 根据权利要求1所述的系统，其中所述可调显示面绕预设转轴转动。"},
            ],
        },
        description={
            "technical_field": {"content": "本发明涉及沉浸式显示控制技术领域。"},
            "background_art": {"content": "现有沉浸式显示空间难以适配不同体验者。"},
            "summary_of_invention": {"technical_solution": "系统根据人体参数调整显示面姿态。"},
            "drawings_description": {"content": "图1为系统结构示意图。"},
            "detailed_description": [
                {"title": "实施例一", "content": "入口交互终端采集人体参数并生成推荐姿态。"},
            ],
        },
        abstract={"content": "本发明公开一种可调式沉浸显示系统及其显示控制方法。"},
        task_id="structured-docx-values",
        tech_description="",
    )

    assert result["success"] is True
    assert result["file_path"].endswith(".docx")
