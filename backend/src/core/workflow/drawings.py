# -*- coding: utf-8 -*-
"""WorkflowDrawingMixin methods split from the workflow engine."""
from .shared import *


class WorkflowDrawingMixin:
    def _extract_review_issues(self, review_report: Dict[str, Any]) -> List[str]:
        """提取质量审查中的严重/高级别问题列表"""
        issues = []

        for section_key in (
            "formal_compliance_review",
            "claims_review",
            "description_review",
            "consistency_review",
            "drawing_review",
            "drawings_review",
            "figure_review",
        ):
            section = review_report.get(section_key, {})
            if isinstance(section, dict):
                for issue in section.get("issues", []):
                    if isinstance(issue, dict) and issue.get("severity") in ("critical", "high"):
                        desc = issue.get("description", "")
                        suggestion = issue.get("suggestion", "")
                        location = issue.get("location", "")
                        issues.append(f"[{location}] {desc}。建议：{suggestion}")

        for risk in review_report.get("examination_risks", []):
            if isinstance(risk, dict) and risk.get("likelihood") in ("critical", "high"):
                risk_type = risk.get("risk_type") or risk.get("type") or "examination_risk"
                desc = risk.get("description", "")
                suggestion = risk.get("mitigation_suggestion") or risk.get("mitigation") or ""
                issues.append(f"[{risk_type}] {desc}。建议：{suggestion}")

        # 详细修改建议
        for suggestion in review_report.get("detailed_revision_suggestions", []):
            if isinstance(suggestion, dict):
                section = suggestion.get("section", "")
                reason = suggestion.get("reason", "")
                suggested = suggestion.get("suggested_content", "")
                issues.append(f"[{section}] {reason}。建议修改为：{suggested[:200]}")

        return issues[:10]  # 最多取10个问题

    def _extract_review_issue_records(self, review_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract structured review issues for CEO routing without judging quality."""
        if not isinstance(review_report, dict):
            return []

        records: List[Dict[str, Any]] = []
        for section_key in (
            "formal_compliance_review",
            "claims_review",
            "description_review",
            "consistency_review",
            "drawing_review",
            "drawings_review",
            "figure_review",
        ):
            section = review_report.get(section_key, {})
            if not isinstance(section, dict):
                continue
            for issue in section.get("issues", []):
                if isinstance(issue, dict):
                    record = dict(issue)
                    record.setdefault("section", section_key)
                    records.append(record)

        for risk in review_report.get("examination_risks", []):
            if isinstance(risk, dict):
                record = dict(risk)
                record.setdefault("section", "examination_risks")
                records.append(record)

        for suggestion in review_report.get("detailed_revision_suggestions", []):
            if isinstance(suggestion, dict):
                record = dict(suggestion)
                record.setdefault("section", suggestion.get("section") or "revision_suggestions")
                records.append(record)

        return records

    def _extract_referenced_figure_numbers(self, draft: Dict[str, Any]) -> List[str]:
        """Return normalized figure numbers referenced by the draft text."""
        if not isinstance(draft, dict):
            return []
        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}
        texts = [
            str(description.get("drawings_description") or ""),
            str(description.get("description_of_drawings") or ""),
        ]
        for drawing in draft.get("drawings", []) or []:
            if isinstance(drawing, dict):
                texts.append(str(drawing.get("description") or ""))
        combined = "\n".join(text for text in texts if text)
        numbers = sorted({int(match) for match in re.findall(r"图\s*([0-9]{1,2})", combined)})
        return [f"图{number}" for number in numbers]

    def _draft_requires_drawings(self, draft: Dict[str, Any]) -> bool:
        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}

        drawing_texts = (
            description.get("drawings_description", ""),
            description.get("description_of_drawings", ""),
        )
        if any(isinstance(text, str) and text.strip() for text in drawing_texts):
            return True
        if draft.get("drawings_expected") is True or draft.get("requires_drawings") is True:
            return True

        expected_drawings = draft.get("expected_drawings")
        if isinstance(expected_drawings, int) and expected_drawings > 0:
            return True
        if isinstance(expected_drawings, list) and expected_drawings:
            return True

        return False

    def _draft_has_drawing_artifact(self, draft: Dict[str, Any]) -> bool:
        drawings = draft.get("drawings", [])
        if not isinstance(drawings, list):
            return False
        return any(
            isinstance(drawing, dict)
            and self._drawing_artifact_is_accessible(drawing)
            for drawing in drawings
        )

    def _drawing_artifact_is_accessible(self, drawing: Dict[str, Any]) -> bool:
        """Return True when a drawing has a workflow-accessible artifact reference."""
        artifact_url = drawing.get("artifact_url") or drawing.get("artifactUrl")
        if artifact_url:
            return True
        file_path = drawing.get("file_path") or drawing.get("path")
        if not file_path:
            return False
        try:
            return _Path(str(file_path)).exists()
        except (OSError, ValueError):
            return False

    def _missing_drawing_references(self, draft: Dict[str, Any]) -> List[str]:
        planned_specs = self._planned_drawing_specs(draft)
        referenced = [spec["figure_number"] for spec in planned_specs]
        if not referenced:
            return []

        drawings = draft.get("drawings", [])
        if not isinstance(drawings, list):
            drawings = []
        generated = {
            str(drawing.get("figure_number") or "").replace(" ", "")
            for drawing in drawings
            if isinstance(drawing, dict)
            and self._drawing_artifact_is_accessible(drawing)
        }
        return [figure for figure in referenced if figure not in generated]

    def _planned_drawing_specs(self, draft: Dict[str, Any]) -> List[Dict[str, str]]:
        """Return figure specs explicitly provided by the Agent draft.

        The workflow must not invent drawing content. It only normalizes figures
        that already appear in the writer's drawing metadata or drawing-description
        section, then asks the writer Agent to generate missing artifacts.
        """
        if not isinstance(draft, dict):
            return []

        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}
        specs_by_number: Dict[str, Dict[str, str]] = {}

        drawings = draft.get("drawings", [])
        if isinstance(drawings, list):
            for item in drawings:
                if not isinstance(item, dict):
                    continue
                figure_number = str(item.get("figure_number") or item.get("figure") or "").replace(" ", "")
                if not re.fullmatch(r"图\d+", figure_number):
                    continue
                title = str(item.get("title") or f"{figure_number}附图").strip()
                desc = str(item.get("description") or item.get("caption") or "").strip()
                specs_by_number[figure_number] = {
                    "figure_number": figure_number,
                    "title": title,
                    "description": desc,
                }

        drawing_text = str(
            description.get("drawings_description")
            or description.get("description_of_drawings")
            or ""
        )
        for match in re.finditer(r"(图\d+)[^\n。；;]*[。；;\n]?", drawing_text):
            sentence = match.group(0).strip(" \n；;。")
            figure_number = match.group(1).replace(" ", "")
            if not sentence:
                continue
            existing = specs_by_number.get(figure_number, {})
            title = existing.get("title") or sentence
            if len(title) > 30:
                title = f"{figure_number}附图"
            specs_by_number[figure_number] = {
                "figure_number": figure_number,
                "title": title,
                "description": existing.get("description") or sentence,
            }

        def _figure_sort_key(item: Dict[str, str]) -> int:
            digits = re.sub(r"\D+", "", item.get("figure_number", ""))
            return int(digits or 0)

        return sorted(specs_by_number.values(), key=_figure_sort_key)

    async def _ensure_required_patent_drawings(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Generate missing drawing artifacts before the quality reviewer sees the draft."""
        if not isinstance(draft, dict):
            return draft
        if not self._draft_requires_drawings(draft):
            return draft
        planned_specs = self._planned_drawing_specs(draft)
        if self._draft_requires_drawings(draft) and not planned_specs:
            draft["_drawing_plan_required"] = {
                "issue": "需要附图，但专利撰写 Agent 未给出逐图附图说明和绘图内容",
                "required_action": "请专利撰写 Agent 先补齐每张附图的图号、标题、具体绘图内容，再调用生图工具。",
            }
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "agent.content",
                    "🧭 需要附图但缺少逐图绘图方案，已交回专利撰写 Agent 补齐",
                    {
                        "agent_name": "CEO Agent",
                        "phase": "patent_writing",
                        "content": json.dumps(draft["_drawing_plan_required"], ensure_ascii=False),
                    },
                )
            return draft
        draft["drawings"] = self._normalize_drawing_metadata(
            draft.get("drawings", []),
            planned_specs=planned_specs,
        )
        missing_figures = self._missing_drawing_references(draft)
        if not missing_figures:
            return draft
        spec_by_number = {spec["figure_number"]: spec for spec in planned_specs}

        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}
        drawing_description = str(
            description.get("drawings_description")
            or description.get("description_of_drawings")
            or ""
        )
        if event_callback:
            event_callback(
                "专利撰写 Agent",
                "agent.thinking",
                f"🖼️ 草稿需要补齐附图（{', '.join(missing_figures)}），正在调用生图工具...",
                {"agent_name": "专利撰写 Agent", "thought": "生成专利附图", "phase": "patent_writing", "missing_figures": missing_figures},
            )

        try:
            drawing_specs = [spec_by_number.get(number, {"figure_number": number}) for number in missing_figures]
            agent_prompt = f"""你是专利撰写 Agent。当前草稿引用了附图，但缺少可访问的附图文件。

请你基于当前专利草稿中已经写明的逐图附图说明，通过 Hermes 工具 `patent_drawing_generator` 分别生成缺失附图。
工作流只负责把缺失图号和草稿上下文交给你，不能代替你决定图中技术内容或调用生图工具。

【任务 ID】
{context.task_id}

【缺失附图规格】
{json.dumps(drawing_specs, ensure_ascii=False, indent=2)}

【附图说明上下文】
{drawing_description}

【已确认技术方案上下文】
{self._build_confirmed_writer_context(context, limit=12000)}

【权利要求摘要】
{json.dumps(draft.get("claims", {}), ensure_ascii=False)[:1800]}

【严格要求】
1. 必须由你调用 `patent_drawing_generator` 生成每一个缺失图号对应的附图。
2. 每张图的 `description` 必须是该图具体绘图内容，不能为空，不能只写“图X为……示意图”。
3. 每张图必须主题不同，不能只换标题而复用相同内容。
4. 图号、标题、说明必须与专利草稿一致。
5. 不要生成最终 DOCX。
6. 最终只输出严格 JSON：
{{
  "drawings": [
    {{
      "figure_number": "图1",
      "title": "当前草稿中该图的真实附图标题",
      "description": "当前草稿中该图必须表达的具体对象、结构、步骤、连接关系或状态变化。",
      "file_path": "/absolute/path/to/figure.png",
      "artifact_url": "/api/v1/workflows/{context.task_id}/artifacts/...",
      "mime_type": "image/png"
    }}
  ]
}}"""
            agent_result = await asyncio.wait_for(
                _run_agent_conversation(
                    profile_id="patent.writer.v1",
                    prompt=agent_prompt,
                    session_id=f"{context.task_id}:patent_drawing_repair",
                    timeout_seconds=WRITER_DRAWING_REPAIR_TIMEOUT_SECONDS,
                ),
                timeout=WRITER_DRAWING_REPAIR_TIMEOUT_SECONDS,
            )
            parsed: Dict[str, Any] = {}
            if isinstance(agent_result, dict):
                parsed = self._try_parse_json(
                    agent_result.get("structured_result")
                    or agent_result.get("final_response")
                    or agent_result.get("response")
                    or agent_result
                )
            else:
                parsed = self._try_parse_json(agent_result)
            generated_drawings = [
                item for item in (parsed.get("drawings") or [])
                if isinstance(item, dict)
            ]

            if generated_drawings:
                existing = draft.get("drawings", [])
                if not isinstance(existing, list):
                    existing = []
                draft["drawings"] = self._normalize_drawing_metadata(
                    [*existing, *generated_drawings],
                    planned_specs=planned_specs,
                )
                draft["drawings_generated_by"] = "patent_writer_agent"
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.content",
                        f"✅ 撰写 Agent 已生成/补齐 {len(generated_drawings)} 张专利附图",
                        {
                            "agent_name": "专利撰写 Agent",
                            "content": json.dumps(generated_drawings, ensure_ascii=False),
                            "phase": "patent_writing",
                        },
                    )
        except Exception as exc:
            self._logger.warning(f"Failed to generate required patent drawings: {exc}")
            draft.setdefault("_drawing_generation_error", str(exc)[:500])
            if self._missing_drawing_references(draft):
                draft["_agent_failed"] = True
                draft["_agent_error"] = (
                    "专利撰写 Agent 未能在限定时间内补齐必要附图；"
                    "需要 CEO 继续调度撰写 Agent 基于现有草稿和附图反馈补齐。"
                )

        return draft

    async def _refresh_working_draft_docx(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        checkpoint: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Refresh draft/working_draft.docx after section writing or drawing generation.

        This is a non-final working document. The final DOCX is still generated only
        after the quality review passes.
        """
        if not isinstance(draft, dict) or draft.get("_agent_failed") is True:
            return draft
        try:
            from src.agents.hermes.tools.patent_docx_generator import PatentDocxGeneratorTool

            docx_result = await PatentDocxGeneratorTool().execute(
                title=draft.get("title") or draft.get("patent_title") or context.title,
                claims=draft.get("claims", {}),
                description=draft.get("description", {}),
                abstract=draft.get("abstract", ""),
                task_id=context.task_id,
                tech_description=self._build_confirmed_writer_context(context, limit=12000),
                drawings=draft.get("drawings", []),
                output_stage="draft",
                file_name="working_draft.docx",
            )
            if isinstance(docx_result, dict) and docx_result.get("success"):
                draft["working_docx_path"] = docx_result.get("file_path", "")
                if docx_result.get("figures"):
                    draft["working_docx_figures"] = docx_result.get("figures")
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.content",
                        f"📝 已刷新工作草稿 DOCX：{checkpoint}",
                        {
                            "agent_name": "专利撰写 Agent",
                            "phase": "patent_writing",
                            "checkpoint": checkpoint,
                            "content": json.dumps(
                                {
                                    "working_docx_path": draft.get("working_docx_path"),
                                    "figures": draft.get("working_docx_figures", []),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    )
        except Exception as exc:
            self._logger.warning(
                f"Failed to refresh working draft DOCX at {checkpoint}: {exc}",
                task_id=context.task_id,
            )
            draft["_working_docx_error"] = str(exc)[:500]
        return draft

    def _apply_review_suggestions_to_draft(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        review_issues: List[str],
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Attach reviewer feedback and deterministic formatting before re-review.

        The workflow engine must not synthesize patent substance locally. Subjective
        remediation belongs to the responsible Hermes Agent via its LLM; this method only
        preserves the current draft, normalizes objective formatting, and records what the
        CEO needs to route back into the loop.
        """
        if not isinstance(draft, dict):
            draft = {}
        repaired = dict(draft)
        claims = repaired.get("claims")
        if isinstance(claims, dict):
            repaired["claims"] = normalize_claims_payload_linebreaks(claims)

        repaired["drawings"] = self._normalize_drawing_metadata(
            repaired.get("drawings", []),
            planned_specs=self._planned_drawing_specs(repaired),
        )
        repaired["_remediation_required"] = {
            "round": context.iteration_count,
            "source": "quality_review_suggestions",
            "issues": review_issues[:12],
            "required_action": (
                "CEO must dispatch the responsible Hermes Agent to revise patent substance; "
                "the workflow engine only normalizes objective formatting."
            ),
        }
        repaired["_needs_agent_rewrite"] = True

        if event_callback:
            event_callback(
                "CEO Agent",
                "agent.content",
                "🧭 已汇总审查问题，继续调度对应 Agent 修复",
                {
                    "agent_name": "CEO Agent",
                    "phase": "patent_writing",
                    "content": json.dumps(repaired.get("_remediation_required"), ensure_ascii=False),
                },
            )
        return repaired

    def _merge_reusable_revision_drawings(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        review_issues: List[str],
    ) -> Dict[str, Any]:
        """Preserve usable drawings across writer revision rounds.

        Revision rounds should build on the previous draft. If the writer returns
        only changed text and omits unchanged drawing metadata, the workflow must
        not treat every prior figure as missing and regenerate them. Figures
        explicitly mentioned in review feedback remain eligible for regeneration.
        """
        if not isinstance(draft, dict):
            return draft
        previous = context.patent_draft if isinstance(context.patent_draft, dict) else {}
        previous_drawings = previous.get("drawings") if isinstance(previous, dict) else []
        current_drawings = draft.get("drawings") if isinstance(draft.get("drawings"), list) else []
        if not isinstance(previous_drawings, list) or not previous_drawings:
            return draft

        issue_text = "\n".join(str(issue or "") for issue in review_issues)
        mentioned_figures = {
            f"图{number}" for number in re.findall(r"图\s*([0-9]{1,2})", issue_text)
        }
        planned_specs = self._planned_drawing_specs(draft)
        current_by_number: Dict[str, Dict[str, Any]] = {}
        for item in current_drawings:
            if not isinstance(item, dict):
                continue
            number = str(item.get("figure_number") or "").replace(" ", "")
            if re.fullmatch(r"图\d+", number):
                current_by_number[number] = dict(item)

        merged = list(current_by_number.values())
        existing_numbers = set(current_by_number)
        for item in previous_drawings:
            if not isinstance(item, dict):
                continue
            number = str(item.get("figure_number") or "").replace(" ", "")
            if not re.fullmatch(r"图\d+", number):
                continue
            if number in existing_numbers or number in mentioned_figures:
                continue
            if not self._drawing_artifact_is_accessible(item):
                continue
            merged_item = dict(item)
            merged.append(merged_item)
            existing_numbers.add(number)

        if len(merged) != len(current_drawings):
            draft["drawings"] = self._normalize_drawing_metadata(
                merged,
                planned_specs=planned_specs,
            )
            draft["_reused_revision_drawings"] = sorted(
                {
                    str(item.get("figure_number") or "").replace(" ", "")
                    for item in draft.get("drawings", [])
                    if isinstance(item, dict)
                    and self._drawing_artifact_is_accessible(item)
                    and str(item.get("figure_number") or "").replace(" ", "") not in current_by_number
                }
            )
        return draft

    def _normalize_drawing_metadata(
        self,
        drawings: object,
        planned_specs: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(drawings, list):
            return []
        if planned_specs is None:
            planned_specs = []
        title_map = {spec["figure_number"]: spec["title"] for spec in planned_specs}
        description_map = {spec["figure_number"]: spec.get("description", "") for spec in planned_specs}
        allowed_numbers = set(title_map)
        normalized: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(drawings, start=1):
            if not isinstance(item, dict):
                continue
            figure_number = str(
                item.get("figure_number")
                or item.get("figureNumber")
                or item.get("number")
                or f"图{index}"
            ).strip()
            if not re.match(r"^图\d+$", figure_number):
                figure_number = f"图{index}"
            if allowed_numbers and figure_number not in allowed_numbers:
                continue
            if figure_number in seen:
                continue
            seen.add(figure_number)
            drawing = dict(item)
            drawing["figure_number"] = figure_number
            raw_title = str(drawing.get("title") or "").strip()
            raw_title = re.sub(rf"^{re.escape(figure_number)}\s*[:：、.．-]?\s*", "", raw_title).strip()
            final_title = title_map.get(figure_number) or raw_title
            if not final_title:
                continue
            drawing["title"] = final_title
            drawing["description"] = description_map.get(figure_number) or str(drawing.get("description") or "").strip()
            normalized.append(drawing)
        return normalized

