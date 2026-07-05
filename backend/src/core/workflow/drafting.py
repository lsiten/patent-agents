# -*- coding: utf-8 -*-
"""WorkflowDraftingMixin methods split from the workflow engine."""
from .shared import *


class WorkflowDraftingMixin:
    def _apply_patent_manual_normalization(
        self,
        draft: Dict[str, Any],
        context_title: str = "",
    ) -> Dict[str, Any]:
        """Apply deterministic manual rules and attach objective compliance signals."""
        if not isinstance(draft, dict):
            return draft
        normalized = dict(draft)
        if not str(normalized.get("title") or normalized.get("patent_title") or "").strip():
            confirmed_title = str(context_title or "").strip()
            if confirmed_title:
                normalized["title"] = confirmed_title
                normalized["patent_title"] = confirmed_title
        claims = normalized.get("claims") or {}
        if isinstance(claims, dict):
            normalized["claims"] = normalize_claims_payload_linebreaks(claims)

        drawings = normalized.get("drawings") or []
        if isinstance(drawings, list):
            normalized["drawings"] = self._normalize_drawing_metadata(
                drawings,
                planned_specs=self._planned_drawing_specs(normalized),
            )

        claim_report = validate_claim_rules(normalized.get("claims", {}))
        document_report = validate_patent_document_structure(
            build_patent_text_from_draft(normalized),
            drawings=normalized.get("drawings", []) if isinstance(normalized.get("drawings"), list) else [],
        )
        manual_draft_report = validate_patent_manual_draft(normalized)
        normalized["manual_compliance"] = {
            "claim_rules": claim_report,
            "document_rules": document_report,
            "manual_draft_rules": manual_draft_report,
            "high_priority_issues": collect_high_priority_issues(
                claim_report,
                document_report,
                manual_draft_report,
            ),
        }
        return normalized

    def _validate_patent_draft_completeness(self, draft: Dict[str, Any]) -> List[str]:
        issues: List[str] = []

        if not draft or not isinstance(draft, dict):
            return ["patent_draft_missing"]
        if draft.get("_agent_failed") is True:
            issues.append("patent_draft_agent_failed")
        if draft.get("_incomplete_output") is True:
            issues.append("patent_draft_incomplete_output")

        claims = draft.get("claims", {}) or {}
        if not isinstance(claims, dict):
            issues.append("claims_missing")
            claims = {}

        independent_claim = claims.get("independent_claim", "")
        if not isinstance(independent_claim, str) or not independent_claim.strip():
            issues.append("independent_claim_missing")

        dependent_claims = claims.get("dependent_claims", [])
        has_dependent_claim = False
        if isinstance(dependent_claims, list):
            has_dependent_claim = any(
                isinstance(claim, str) and claim.strip()
                for claim in dependent_claims
            )
        elif isinstance(dependent_claims, str):
            has_dependent_claim = bool(dependent_claims.strip())
        if not has_dependent_claim:
            issues.append("dependent_claims_missing")

        claim_report = validate_claim_rules(claims)
        for issue in claim_report.get("issues", []):
            if issue.get("severity") in {"critical", "high"}:
                issues.append(f"claim_rule:{issue.get('issue', '')}")

        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            issues.append("description_missing")
            description = {}

        for section_name in (
            "technical_field",
            "background_art",
            "summary_of_invention",
            "detailed_description",
        ):
            content = description.get(section_name, "")
            if not isinstance(content, str) or not content.strip():
                issues.append(f"description_{section_name}_missing")

        abstract = draft.get("abstract", "") or ""
        if not isinstance(abstract, str) or not abstract.strip():
            issues.append("abstract_missing")

        if self._draft_requires_drawings(draft):
            if not self._draft_has_drawing_artifact(draft):
                issues.append("drawing_artifacts_missing")
            missing_figures = self._missing_drawing_references(draft)
            if missing_figures:
                issues.append(f"drawing_artifacts_missing:{','.join(missing_figures)}")
            planned_figures = self._planned_drawing_specs(draft)
            drawings = draft.get("drawings", [])
            if isinstance(drawings, list):
                normalized_drawings = self._normalize_drawing_metadata(
                    drawings,
                    planned_specs=planned_figures,
                )
                titles = [
                    str(drawing.get("title") or "").strip()
                    for drawing in normalized_drawings
                    if isinstance(drawing, dict) and str(drawing.get("title") or "").strip()
                ]
                if len(titles) != len(set(titles)):
                    issues.append("drawing_titles_duplicate")
                if len(drawings) > len(normalized_drawings) and normalized_drawings:
                    issues.append("drawing_artifacts_excessive_or_duplicate")
                file_hashes: Dict[str, str] = {}
                for drawing in normalized_drawings:
                    if not isinstance(drawing, dict):
                        continue
                    file_path = drawing.get("file_path")
                    if not isinstance(file_path, str) or not file_path:
                        continue
                    path = _Path(file_path)
                    if not path.is_file():
                        continue
                    try:
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    except Exception:
                        continue
                    figure_number = str(drawing.get("figure_number") or "")
                    if digest in file_hashes:
                        issues.append(f"drawing_artifacts_duplicate_content:{file_hashes[digest]},{figure_number}")
                        break
                    file_hashes[digest] = figure_number

        document_report = validate_patent_document_structure(
            build_patent_text_from_draft(draft),
            drawings=draft.get("drawings", []) if isinstance(draft.get("drawings"), list) else [],
        )
        for issue in document_report.get("issues", []):
            if issue.get("severity") in {"critical", "high"}:
                issues.append(f"document_rule:{issue.get('issue', '')}")

        manual_draft_report = validate_patent_manual_draft(draft)
        for issue in manual_draft_report.get("issues", []):
            if issue.get("severity") in {"critical", "high"}:
                issues.append(f"manual_rule:{issue.get('issue', '')}")

        return issues

    def _reviewable_content_issues(self, draft: Dict[str, Any]) -> List[str]:
        """Return content issues while ignoring stale transport/agent failure markers."""
        if not isinstance(draft, dict):
            return ["patent_draft_missing"]
        issues = self._validate_patent_draft_completeness(draft)
        return [
            issue
            for issue in issues
            if issue not in {"patent_draft_agent_failed", "patent_draft_incomplete_output"}
        ]

    def _clear_stale_writer_failure_if_reviewable(self, draft: Any) -> Any:
        """Clear stale failure flags after the writer Agent has produced reviewable content.

        In that case the old _agent_failed marker is no longer a content failure and must
        not block the CEO quality loop or final DOCX generation.
        """
        if not isinstance(draft, dict):
            return draft
        if draft.get("_agent_failed") is not True and draft.get("_incomplete_output") is not True:
            return draft
        if self._reviewable_content_issues(draft):
            return draft
        repaired = dict(draft)
        repaired.pop("_agent_failed", None)
        repaired.pop("_incomplete_output", None)
        repaired.pop("_agent_error", None)
        repaired["_writer_agent_recovered"] = True
        return repaired

    def _merge_manual_compliance_into_review(
        self,
        context: WorkflowContext,
        review_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge deterministic manual-rule findings into the reviewer report.

        The quality reviewer remains responsible for professional judgment, but
        hard rules from the drafting manual cannot be ignored when generating
        the workflow decision.
        """
        if not isinstance(review_report, dict):
            review_report = {}
        draft = (
            self._apply_patent_manual_normalization(
                context.patent_draft,
                context_title=context.title,
            )
            if isinstance(context.patent_draft, dict)
            else {}
        )
        if draft:
            context.patent_draft = draft
        manual = draft.get("manual_compliance", {}) if isinstance(draft, dict) else {}
        claim_report = manual.get("claim_rules", {}) if isinstance(manual, dict) else {}
        doc_report = manual.get("document_rules", {}) if isinstance(manual, dict) else {}
        draft_report = manual.get("manual_draft_rules", {}) if isinstance(manual, dict) else {}

        def to_review_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
            target_agent = str(issue.get("target_agent") or "patent_writer")
            if target_agent in {"retrieval_analyst", "retrieval", "search"}:
                responsible_phase = "retrieval_analysis"
            elif target_agent in {"requirement_analyst", "requirement", "brainstorm_partner"}:
                responsible_phase = "requirement_analysis"
            else:
                responsible_phase = "patent_writing"
            return {
                "severity": issue.get("severity", "medium"),
                "location": issue.get("location", "全文"),
                "description": issue.get("issue") or issue.get("description", ""),
                "suggestion": issue.get("suggestion", ""),
                "target_agent": target_agent,
                "responsible_phase": responsible_phase,
                "source": "deterministic_manual_gate",
            }

        claim_issues = [
            to_review_issue(item)
            for item in claim_report.get("issues", [])
            if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
        ]
        doc_issues = [
            to_review_issue(item)
            for item in doc_report.get("issues", [])
            if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
        ]
        draft_issues = [
            to_review_issue(item)
            for item in draft_report.get("issues", [])
            if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
        ]
        if not claim_issues and not doc_issues and not draft_issues:
            return review_report

        merged = dict(review_report)
        merged["_hard_rule_failed"] = True
        all_hard_issues = claim_issues + doc_issues + draft_issues
        hard_routes = {
            str(issue.get("responsible_phase") or "")
            for issue in all_hard_issues
            if str(issue.get("responsible_phase") or "")
        }
        if "retrieval_analysis" in hard_routes:
            merged["_hard_rule_route"] = "retrieval_analysis"
            merged["root_cause"] = "evidence_missing"
        elif "requirement_analysis" in hard_routes:
            merged["_hard_rule_route"] = "requirement_analysis"
            merged["root_cause"] = "requirement_unclear"
        else:
            merged["_hard_rule_route"] = "patent_writing"
            merged.setdefault("root_cause", "content_incomplete")

        claims_review = dict(merged.get("claims_review") or {})
        claims_review.setdefault("issues", [])
        if isinstance(claims_review["issues"], list):
            claims_review["issues"].extend(claim_issues)
        merged["claims_review"] = claims_review

        formal_review = dict(merged.get("formal_compliance_review") or {})
        formal_review.setdefault("issues", [])
        if isinstance(formal_review["issues"], list):
            formal_review["issues"].extend(doc_issues + draft_issues)
        merged["formal_compliance_review"] = formal_review

        drawing_issues = [
            issue for issue in doc_issues
            if "图" in str(issue.get("location", "")) or "附图" in str(issue.get("location", ""))
        ]
        if drawing_issues:
            drawing_review = dict(merged.get("drawing_review") or {})
            drawing_review.setdefault("issues", [])
            if isinstance(drawing_review["issues"], list):
                drawing_review["issues"].extend(drawing_issues)
            merged["drawing_review"] = drawing_review

        merged["manual_compliance"] = manual
        return merged

    def _has_unresolved_critical_issues(self, context: WorkflowContext) -> bool:
        """检查工作流是否还有未解决的关键问题 (在 COMPLETED 之前的最后一道闸)

        关键修复 (Bug #1 用户可见层): 即便经过 max_iterations 轮修正,
        最终的 patent_draft 仍可能是 _agent_failed / 空白内容,
        最终 review_report 仍可能 recommendation="reject" 且包含 critical issue。
        这种情况必须以 FAILED 状态结束,而不是 COMPLETED,
        否则用户会看到一份"流程完成"的空专利文件。
        """
        draft_issues = self._validate_patent_draft_completeness(context.patent_draft)
        if draft_issues:
            return True

        # 2) 检查 review_report 是否有未解决的 critical issue
        review = context.review_report
        if not review or not isinstance(review, dict):
            return True
        if review.get("_agent_failed") is True:
            return True
        if self._needs_quality_remediation(review):
            return True

        return False

    def _patent_draft_has_content(self, draft: Dict[str, Any]) -> bool:
        """检查 patent_draft 是否包含任何真实可用的内容。

        用于 iteration loop 中判断是否需要重新调用 writer。
        """
        if not draft or not isinstance(draft, dict):
            return False
        if draft.get("_agent_failed") is True or draft.get("_incomplete_output") is True:
            return False
        claims = draft.get("claims", {}) or {}
        if not claims.get("independent_claim", "").strip():
            return False
        return True

    def _iteration_making_no_progress(self, context: WorkflowContext) -> bool:
        """检测 iteration loop 是否在原地踏步 (no progress)。

        当 writer 和 reviewer 连续失败,且错误相同时 (例如 LLM API
        一直不可用、key 错误、配额耗尽),继续迭代不会产生新内容。
        应立即跳出,避免无谓等待和资源浪费。

        Returns:
            True 表示应当跳出 iteration loop
        """
        # 至少跑过一轮才有意义判断
        if context.iteration_count < 1:
            return False

        # 检查最近一轮的 writer/reviewer 是否都失败
        recent_phases = [p for p in context.phase_history[-2:]]
        writer_failed = False
        reviewer_failed = False
        for p in recent_phases:
            if not isinstance(p.output, dict):
                continue
            if p.phase == WorkflowPhase.WRITING and p.output.get("_agent_failed"):
                writer_failed = True
            if p.phase == WorkflowPhase.REVIEW and p.output.get("_agent_failed"):
                reviewer_failed = True

        # 只有 writer 和 reviewer 都失败,且失败原因相同时才是 no-progress
        if not (writer_failed and reviewer_failed):
            return False

        writer_err = (context.patent_draft or {}).get("_agent_error", "")
        reviewer_err = (context.review_report or {}).get("_agent_error", "")
        if not writer_err or not reviewer_err:
            return False

        # 错误相同 (或非常相似) — 重复迭代没有意义
        # 简单比较: 错误信息的前 100 个字符相同
        return writer_err[:100] == reviewer_err[:100]

    def _analyze_workflow_failure(self, context: WorkflowContext) -> Dict[str, Any]:
        """Build a deterministic failure report for CEO routing.

        CEO only reports contracts, Agent failures, and review Agent findings.
        It does not create specialist patent conclusions or content advice.
        """
        issues: List[Dict[str, str]] = []
        suggestions: List[str] = []

        draft_contract_issues = self._validate_phase_contract("patent_draft", context.patent_draft)
        review_contract_issues = self._validate_phase_contract("review_report", context.review_report)

        draft = context.patent_draft if isinstance(context.patent_draft, dict) else {}
        review = context.review_report if isinstance(context.review_report, dict) else {}

        if draft_contract_issues:
            for issue in draft_contract_issues:
                issues.append({
                    "type": "patent_draft_contract",
                    "message": issue,
                    "severity": "critical",
                })
            suggestions.append("路由回专利撰写 Agent，基于上一轮草稿和反馈补齐专利草稿结构契约。")

        if draft.get("_agent_failed") is True:
            issues.append({
                "type": "patent_writer_failed",
                "message": str(draft.get("_agent_error") or "专利撰写 Agent 执行失败。")[:500],
                "severity": "critical",
            })
            suggestions.append("路由回专利撰写 Agent，携带失败输出和错误信息继续修正。")

        if review_contract_issues:
            for issue in review_contract_issues:
                issues.append({
                    "type": "review_report_contract",
                    "message": issue,
                    "severity": "critical",
                })
            suggestions.append("路由回质量审查 Agent，要求按审查输出契约补齐 recommendation、review_summary、root_cause 和 responsible_phase。")

        if review.get("_agent_failed") is True:
            issues.append({
                "type": "quality_reviewer_failed",
                "message": str(review.get("_agent_error") or "质量审查 Agent 执行失败。")[:500],
                "severity": "critical",
            })
            suggestions.append("路由回质量审查 Agent，携带专利草稿摘要重新审查。")

        if self._needs_quality_remediation(review):
            route = self._classify_remediation_path(review, context)
            route_display = {
                "WRITE_MORE": "专利撰写 Agent",
                "ANALYZE_MORE": "需求分析 Agent",
                "SEARCH_MORE": "检索分析 Agent",
                "NEEDS_USER_INPUT": "用户补充信息",
                "TERMINAL_FAILURE": "终止并展示不可自动恢复原因",
            }.get(route, "专利撰写 Agent")
            for issue in self._extract_review_issue_records(review)[:10]:
                description = str(
                    issue.get("description")
                    or issue.get("reason")
                    or issue.get("message")
                    or issue.get("risk_type")
                    or issue.get("section")
                    or "质量审查 Agent 标记的问题"
                )
                severity = str(issue.get("severity") or issue.get("likelihood") or "high")
                issues.append({
                    "type": str(issue.get("section") or "quality_review_issue"),
                    "message": description[:500],
                    "severity": severity if severity in {"low", "medium", "high", "critical"} else "high",
                })
            suggestions.append(f"按质量审查 Agent 的 root_cause/responsible_phase 路由到：{route_display}。")

        if draft_contract_issues or draft.get("_agent_failed") is True:
            phase = "patent_writing"
            phase_display = "专利撰写阶段"
            main_reason = "专利撰写阶段输出未满足阶段契约"
        elif review_contract_issues or review.get("_agent_failed") is True or self._needs_quality_remediation(review):
            phase = "quality_review"
            phase_display = "质量审查阶段"
            main_reason = "质量审查阶段输出未通过或未满足阶段契约"
        else:
            phase = "final_check"
            phase_display = "最终检查阶段"
            main_reason = "最终检查发现仍存在未解决契约问题"

        if not issues:
            issues.append({
                "type": "unresolved_contract",
                "message": "工作流存在未解决问题，但当前阶段未提供可路由的结构化缺陷。",
                "severity": "critical",
            })
            suggestions.append("路由回质量审查 Agent，要求输出结构化缺陷和 responsible_phase。")

        return {
            "phase": phase,
            "phase_display": phase_display,
            "main_reason": main_reason,
            "issues": issues,
            "suggestions": list(dict.fromkeys(suggestions)),
        }

    def _review_requires_drawing_changes(self, review_report: Dict[str, Any]) -> bool:
        """Return True only when review feedback specifically requires drawing changes."""
        if not isinstance(review_report, dict):
            return False
        drawing_terms = (
            "附图",
            "图号",
            "图题",
            "插图",
            "图片",
            "图文",
            "draw",
            "figure",
        )
        actionable_terms = (
            "缺失",
            "损坏",
            "不可访问",
            "重复",
            "不一致",
            "不符",
            "错误",
            "重画",
            "重新生成",
            "替换",
            "补齐",
            "新增",
        )
        concrete_drawing_problem_terms = (
            "缺失",
            "损坏",
            "不可访问",
            "重复",
            "图文不符",
            "图文不一致",
            "图号重复",
            "未生成",
            "无法访问",
            "无法打开",
            "需要重画",
            "重新生成",
            "替换图",
            "补齐图",
            "新增图",
        )
        for record in self._extract_review_issue_records(review_report):
            section = str(record.get("section") or "").lower()
            text = " ".join(
                str(record.get(key) or "")
                for key in ("location", "description", "suggestion", "reason", "suggested_content")
            ).lower()
            if not text:
                continue
            has_drawing_reference = any(term.lower() in text for term in drawing_terms) or any(
                key in section for key in ("drawing", "figure")
            )
            if not has_drawing_reference:
                continue
            if "最终docx" in text and "复核" in text and not any(
                term in text for term in ("缺", "损坏", "不可访问", "重复", "不符", "不一致")
            ):
                continue
            has_concrete_figure = bool(re.search(r"图\s*[0-9]{1,2}", text, re.IGNORECASE))
            has_concrete_problem = any(term.lower() in text for term in concrete_drawing_problem_terms)
            if has_concrete_problem and (
                has_concrete_figure
                or "附图缺失" in text
                or "未生成附图" in text
                or "drawing" in section
                or "figure" in section
            ):
                return True
        return False

    def _build_revision_prompt(
        self,
        context: WorkflowContext,
        review_issues: List[str],
        allow_drawing_generation: bool = True,
    ) -> str:
        """构建修正撰写的prompt，包含审查问题和原有草稿"""
        draft_output = self._latest_phase_output(context, WorkflowPhase.WRITING, "patent_draft")
        requirement_output = self._latest_phase_output(
            context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
        )
        retrieval_output = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        current_draft = draft_output or context.patent_draft
        draft_summary = json.dumps(current_draft, ensure_ascii=False)[:6000]
        previous_drawings = []
        if isinstance(current_draft, dict):
            previous_drawings = [
                item for item in (current_draft.get("drawings") or [])
                if isinstance(item, dict)
            ]
        previous_drawings_summary = json.dumps(previous_drawings, ensure_ascii=False)[:3000]
        drawing_revision_rule = (
            "审查意见明确涉及附图缺失、损坏、重复、图文不符或附图实施例变化；仅允许针对被点名的图号重新调用生图工具。"
            if allow_drawing_generation
            else "本轮审查未指出附图缺失、损坏、重复或图文不符；禁止调用 patent_drawing_generator，必须原样返回上一轮可访问附图元数据。"
        )
        requirement_summary = json.dumps(requirement_output, ensure_ascii=False)[:3000]
        retrieval_summary = self._build_retrieval_summary_for_writer(retrieval_output, limit=12000)
        confirmed_writer_context = self._build_confirmed_writer_context(
            context,
            requirement_output=requirement_output,
            retrieval_output=retrieval_output,
            limit=18000,
        )
        issues_text = "\n".join(f"  {i+1}. {issue}" for i, issue in enumerate(review_issues))
        draft_failed = (
            not isinstance(context.patent_draft, dict)
            or context.patent_draft.get("_agent_failed") is True
            or context.patent_draft.get("_incomplete_output") is True
        )
        failed_hint = ""
        if draft_failed:
            failed_hint = """
## 当前专利文件生成失败或不完整
当前专利文件不能作为修正依据。请以已确认撰写上下文、需求分析结果和检索分析结果为主要依据，重新生成完整专利文件。"""

        return f"""请基于质量审查意见对专利申请文件进行修正。

## 审查发现的问题（必须全部解决）：
{issues_text}
{failed_hint}

## 已确认撰写上下文：
{confirmed_writer_context}

## 需求分析结果：
{requirement_summary}

## 检索分析结果：
{retrieval_summary}

## 当前专利文件：
{draft_summary}

## 上一轮可复用附图元数据：
{previous_drawings_summary}

## 修正要求：
1. 这是基于上一轮专利文件的迭代修正，不是重新开始；上一轮已正确且未被指出问题的内容必须保留
2. 逐一解决上述所有问题；仅替换或补充需要修复的权利要求、说明书章节、摘要或附图
3. 如果需求分析或检索报告中已有明确结论，不得丢弃；如确需调整，必须与审查问题直接相关
4. 保持原有文件结构不变（权利要求书+说明书+摘要+必要附图）
5. 修正后输出完整的JSON格式专利文件，而不是只输出修改片段
6. 确保修改后权利要求与说明书、附图的一致性
7. 如果审查问题涉及背景技术或证据，背景技术必须按三段式重写，并点名引用至少两个检索报告 confirmed_sources / web_evidence / non_patent_prior_art 中的真实来源标题、论文号、公开资料名称或 URL；不得只写“公开技术”“相关研究”等泛称，不得虚构专利号
8. 若发明名称、摘要或发明内容包含“方法及系统”或“系统”，权利要求书必须包含对应系统独立权利要求；系统独权应以模块/单元承接权利要求1的方法步骤。若不增加系统独权，必须把发明名称、摘要和发明内容统一改为只保护“方法”。
9. 权利要求1仍必须只能由S1-S3或S1-S4组成，且不超过250字；系统独立权利要求不计入权利要求1步数，但必须与说明书系统结构一致。
10. 修订轮不得重画或替换未被审查指出问题且文件可访问的附图；必须原样返回上一轮可复用附图元数据。只有审查意见明确指出某张图缺失、损坏、重复、图文不符或该图实施例需要改变时，才重新调用生图工具生成该图。
11. 从属权利要求不得过于简略，每条应包含具体附加技术特征和充分限定（参数范围、替代方案、子步骤、组合方式、结构关系或技术效果），字数应在80-450字之间；若从权仅复述独权特征或过于泛化，必须补充实质性限定内容。
12. 当前附图修订判定：{drawing_revision_rule}
13. 具体实施方式不得截断；必须显式按权利要求1的 S1、S2、S3（以及 S4，如有）逐项展开；所有被审查指出的图号对应实施例必须完整补齐，不能以“补充……”或省略号结束。"""

    def _build_retrieval_summary_for_writer(self, retrieval_output: Any, limit: int = 12000) -> str:
        """Build a source-preserving retrieval summary for the writer Agent.

        This is only context packaging. It does not add evidence, invent sources,
        or make patentability judgments.
        """
        if not isinstance(retrieval_output, dict) or not retrieval_output:
            return "{}"
        keys = (
            "retrieval_strategy",
            "confirmed_sources",
            "prior_art_references",
            "similar_patents",
            "web_evidence",
            "non_patent_prior_art",
            "evidence_sources",
            "evidence_gaps",
            "novelty_assessment",
            "inventive_step_assessment",
            "utility_assessment",
            "writing_recommendations",
            "risk_factors",
            "overall_patentability",
            "overall_confidence",
            "conclusion",
        )
        compact = {key: retrieval_output.get(key) for key in keys if retrieval_output.get(key) not in (None, "", [])}
        return json.dumps(compact or retrieval_output, ensure_ascii=False, default=str)[:limit]

    def _build_confirmed_writer_context(
        self,
        context: WorkflowContext,
        requirement_output: Any = None,
        retrieval_output: Any = None,
        limit: int = 16000,
    ) -> str:
        """Build the writer-facing technical package from confirmed workflow facts.

        Raw transcript wrappers are excluded here. The writer still receives the
        sanitized source disclosure so revision rounds can preserve original
        technical facts while avoiding timestamps, speaker labels and meeting
        formatting artifacts.
        """
        shared = context.shared_agent_context if isinstance(context.shared_agent_context, dict) else {}
        safe_shared = {
            key: value
            for key, value in shared.items()
            if key
            not in {
                "user_supplements",
                "raw_disclosure",
                "original_description",
                "disclosure_text",
                "transcript",
            }
        }
        sanitized_source_disclosure = self._sanitize_disclosure_text(
            context.original_description or str(context.metadata.get("raw_disclosure") or "")
        )
        payload = {
            "task_id": context.task_id,
            "patent_title": context.title or context.metadata.get("confirmed_preflight", {}).get("patent_title", ""),
            "target_country": context.target_country,
            "patent_type_preference": context.metadata.get("patent_type_preference", ""),
            "confirmed_preflight": context.metadata.get("confirmed_preflight", {}),
            "sanitized_source_disclosure": sanitized_source_disclosure[:6000],
            "shared_confirmed_facts": safe_shared,
            "requirement_analysis": requirement_output or self._latest_phase_output(
                context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
            ),
            "retrieval_report": self._build_retrieval_summary_for_writer(
                retrieval_output
                if retrieval_output is not None
                else self._latest_phase_output(context, WorkflowPhase.RETRIEVAL, "retrieval_report"),
                limit=12000,
            ),
        }
        return json.dumps(payload, ensure_ascii=False, default=str)[:limit]

    async def _generate_patent_in_sections(
        self,
        service,
        profile_id: str,
        base_task: str,
        context,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        allow_drawing_generation: bool = True,
    ) -> Dict[str, Any]:
        """通过 Agent 工具调用生成专利文件
        
        Agent 会按照 SOUL.md 中定义的工具调用序列：
        1. claim_drafter - 获取权利要求撰写骨架和客观约束
        2. description_writer - 获取说明书章节约束和客观提示
        3. support_checker - 检查支持关系  
        4. patent_drawing_generator - 由撰写 Agent 生成必要附图
        正式专利正文由 Agent LLM 生成，最终 .docx 在质量审查通过后生成。
        
        返回前端期望的结构化 dict。
        """
        requirement_output = self._latest_phase_output(
            context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
        )
        retrieval_output = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        req_data = json.dumps(requirement_output, ensure_ascii=False)[:2000] if requirement_output else ""
        ret_data = self._build_retrieval_summary_for_writer(retrieval_output, limit=12000)
        confirmed_writer_context = self._build_confirmed_writer_context(
            context,
            requirement_output=requirement_output,
            retrieval_output=retrieval_output,
            limit=18000,
        )
        reusable_drawings = []
        if not allow_drawing_generation and isinstance(context.patent_draft, dict):
            reusable_drawings = [
                item for item in (context.patent_draft.get("drawings") or [])
                if isinstance(item, dict) and self._drawing_artifact_is_accessible(item)
            ]
        reusable_drawings_json = json.dumps(reusable_drawings, ensure_ascii=False)[:5000]
        drawing_task_rule = (
            """3. 对涉及结构、装置、系统、流程或空间关系的发明，调用 patent_drawing_generator 工具生成对应附图
    - tech_description: 依据权利要求、说明书附图说明和原始技术方案整理的绘图说明
    - task_id: 当前工作流任务ID {task_id}
    - title: 当前草稿中该图的真实附图标题
    - description: 当前草稿中该图必须表达的具体对象、结构、步骤、连接关系或状态变化"""
        ).format(task_id=context.task_id) if allow_drawing_generation else f"""3. 本轮是文字/权利要求修订，审查未要求修图，禁止调用 patent_drawing_generator。
    - 必须复用并原样返回以下上一轮可访问附图元数据。
    - 只有下一轮质量审查明确指出某张图缺失、损坏、重复、图文不符或附图实施例需要改变时，才允许重画。
    - 上一轮可复用附图元数据：
{reusable_drawings_json}"""
        task_context = str(base_task or "").strip()
        tech_content = "\n\n".join(
            part
            for part in [
                f"当前撰写任务/修正要求：\n{task_context}" if task_context else "",
                "已确认撰写上下文：\n" + confirmed_writer_context,
                json.dumps(requirement_output or {}, ensure_ascii=False),
                ret_data,
            ]
            if part
        )

        async def _emit_tool_start(tool_name: str, parameters: Dict[str, Any]) -> None:
            if event_callback:
                event_callback(
                    "专利撰写 Agent",
                    "agent.tool_call_start",
                    f"🔧 调用工具: {tool_name}",
                    {
                        "agent_name": "专利撰写 Agent",
                        "tool_name": tool_name,
                        "parameters": parameters,
                    },
                )

        async def _emit_tool_end(
            tool_name: str,
            parameters: Dict[str, Any],
            result: Any,
            success: bool = True,
        ) -> None:
            if event_callback:
                result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
                event_callback(
                    "专利撰写 Agent",
                    "agent.tool_call_end",
                    ("✅" if success else "❌") + f" {tool_name} 返回",
                    {
                        "agent_name": "专利撰写 Agent",
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "result": result_text[:1200],
                        "success": success,
                    },
                )

        async def _run_writer_tool(
            tool_name: str,
            parameters: Dict[str, Any],
            call_factory: Callable[[], Any],
            timeout_seconds: int = 75,
        ) -> Dict[str, Any]:
            """Run a writer-owned tool with progress events and a bounded wait.

            Section drafting must be real: a slow or failed LLM/tool call should be
            surfaced as a writer failure instead of being replaced by local content.
            """
            await _emit_tool_start(tool_name, parameters)
            try:
                result = await asyncio.wait_for(call_factory(), timeout=timeout_seconds)
                if not isinstance(result, dict):
                    result = {"success": True, "data": {"content": str(result)}}
                await _emit_tool_end(
                    tool_name,
                    parameters,
                    result,
                    bool(result.get("success", True)),
                )
                return result
            except Exception as exc:
                result = {
                    "success": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "data": {},
                }
                await _emit_tool_end(tool_name, parameters, result, False)
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.thinking",
                        f"⚠️ {tool_name} 调用超时或失败，停止本轮撰写并等待 CEO 重新调度",
                        {
                            "agent_name": "专利撰写 Agent",
                            "thought": "writer_tool_failed",
                            "tool_name": tool_name,
                            "error": result["error"],
                        },
                    )
                return result

        # Patent writing stays inside the Hermes Agent loop. The workflow engine only
        # builds context, captures tool events, and parses the Agent's final JSON.
        
        # 构建完整的专利撰写任务 prompt，让 Agent 通过工具调用完成
        # 注：不在此阶段生成 docx，待质量审查通过后再生成
        task_prompt = f"""请基于以下技术方案，通过调用工具生成完整的专利申请文件内容。

【发明名称】
{context.title or "待定"}

【已确认技术方案上下文】
{confirmed_writer_context}

【需求分析结果】
{req_data}

【检索分析结果】
{ret_data}

【任务要求】
请按顺序调用 Hermes 工具获取结构、约束、客观信号和附图产物；正式专利正文必须由你作为专利撰写 Agent 通过 LLM 判断并生成：

1. 调用 claim_drafter 工具获取权利要求撰写骨架
   - features: 从技术描述中提取的技术特征
   - protection_scope: 期望的保护范围
   - 注意：工具只返回骨架/特征顺序，正式权利要求由你生成
   - 硬性规范：权利要求书由独权和从权组成；权利要求1只能写成3步或4步且不超过250字；每个分号“；”和句号“。”后必须换行。
   - 如果发明名称、发明内容或保护范围包含“方法及系统”或“系统”，必须同时撰写方法独立权利要求和系统独立权利要求；系统独权应以模块/单元承接权利要求1的方法步骤。若只保护方法，则发明名称、摘要和发明内容不能写“系统”。
   - 从属权利要求深度要求：
     * 每条从权必须包含具体的附加技术特征和实质性限定，不得只写泛化限定或仅复述独权特征；
     * 附加特征应包含参数范围、替代方案、子步骤、组合方式、结构关系或技术效果中的至少一项；
     * 从权应按参数细化→替代实现→处理步骤→组合特征→结构细节→风险规避的顺序递进；
     * 采用分层递进引用策略：权2引权1，权3引权2，权4可引权1和权3，构建多层次保护网；
     * 每条从权字数应在80-450字之间，确保内容充分展开。
   
2. 调用 description_writer 工具获取说明书各章节写作约束
   - section_type="technical_field": 技术领域
   - section_type="background": 背景技术
   - section_type="summary": 发明内容（技术问题+技术方案+有益效果）
   - section_type="detailed": 具体实施方式
   - 注意：工具只返回章节约束，正式说明书正文由你生成
   
 {drawing_task_rule}

 4. 调用 support_checker 检查你生成的权利要求与说明书的支持关系

注意：本阶段仅生成专利内容和必要附图，不生成最终文档文件。请确保所有内容完整、规范。
【专利规范硬性要求】
- 不得把交底逐字稿中的时间戳、说话人、会议口语或格式性内容写入正文。
- 说明书摘要必须包含：专利名称、技术领域、简化技术方案、技术效果，且不超过300字。
- 技术领域必须具体，不能写成发明本身，也不能混入方案细节。
	- 背景技术必须基于检索报告中的真实现有技术，并避免泄露本发明的具体方案；必须点名引用至少两个 confirmed_sources / web_evidence / non_patent_prior_art 中的真实来源标题、论文号、公开资料名称或 URL，例如 arXiv 论文、Microsoft Research 项目页、官方公开资料等，并说明这些来源没有解决的具体技术问题。不得只写“公开技术”“相关研究”等泛称，不得虚构专利号。
- 发明内容必须包含技术问题、技术方案、有益效果，三者一一对应。
- 附图至少按需要规划4幅；每幅图必须表达不同主题，不能只换标题或重复图片内容。
- 附图说明不得重复图号或重复标题。
- 具体实施方式必须与权利要求和附图对应，不能使用 Markdown 标题。
- 具体实施方式必须显式按权利要求1的 S1、S2、S3（以及 S4，如有）逐项展开，不能缺少步骤编号。
- 如果题名为“方法及系统”或正文包含系统保护主题，权利要求书中必须出现对应系统独立权利要求，不能只在说明书中描述系统。
最终只输出严格 JSON，不要输出 Markdown、代码块或解释文字：
{{
  "claims": {{
    "independent_claim": "1. ...",
    "dependent_claims": ["2. ..."]
  }},
  "description": {{
    "technical_field": "...",
    "background_art": "...",
    "summary_of_invention": "...",
    "description_of_drawings": "...",
    "detailed_description": "..."
  }},
  "abstract": "...",
  "drawings": []
}}

请开始执行工具调用。"""

        self._logger.info("Patent writer: starting tool-based generation")
        if event_callback:
            for step, message, thought in (
                (1, "🧾 正在生成权利要求书...", "生成权利要求书"),
                (2, "📚 正在生成说明书各章节...", "生成说明书"),
                (3, "🔎 正在检查权利要求与说明书支持关系...", "检查支持关系"),
            ):
                event_callback(
                    "专利撰写 Agent",
                    "agent.thinking",
                    message,
                    {"agent_name": "专利撰写 Agent", "thought": thought, "step": step},
                )

        claims_data = {}
        description_data = {}
        abstract_text = ""
        docx_path = ""
        drawings_data = list(reusable_drawings)
        final_response = ""
        last_failed_result: Optional[Dict[str, Any]] = None

        def _preview(value: Any, limit: int = 220) -> str:
            text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
            return text[:limit] + ("..." if len(text) > limit else "")

        def _emit_writer_section_result(
            section_key: str,
            section_label: str,
            content: Any,
            extra: Optional[Dict[str, Any]] = None,
        ) -> None:
            if not event_callback:
                return
            preview = _preview(content)
            event_callback(
                "专利撰写 Agent",
                "agent.content",
                f"📝 {section_label}已生成" + (f"：{preview}" if preview else ""),
                {
                    "agent_name": "专利撰写 Agent",
                    "phase": "patent_writing",
                    "section": section_key,
                    "section_label": section_label,
                    "content_preview": preview,
                    **(extra or {}),
                },
            )

        for writer_attempt in range(3):
            agent_result = await _run_agent_conversation_with_timeout(
                profile_id,
                task_prompt,
                timeout_seconds=_configured_timeout_seconds(
                    "writer_initial_timeout_seconds",
                    WRITER_INITIAL_TIMEOUT_SECONDS,
                ),
            )

            if isinstance(agent_result, dict):
                final_response = agent_result.get("final_response", "") or agent_result.get("content", "") or final_response
                messages = agent_result.get("messages", [])
                agent_failed = agent_result.get("failed") is True or (
                    agent_result.get("completed") is False and bool(agent_result.get("error"))
                )
            else:
                final_response = str(agent_result) if agent_result else final_response
                messages = []
                agent_failed = False

            tool_call_names: Dict[str, str] = {}
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                for tool_call in msg.get("tool_calls", []) or []:
                    if not isinstance(tool_call, dict):
                        continue
                    call_id = str(tool_call.get("id") or "")
                    function_data = tool_call.get("function", {})
                    function_name = ""
                    if isinstance(function_data, dict):
                        function_name = str(function_data.get("name") or "")
                    function_name = function_name or str(tool_call.get("name") or "")
                    if call_id and function_name:
                        tool_call_names[call_id] = function_name

            for msg in messages:
                if isinstance(msg, dict) and msg.get("role") == "tool":
                    tool_call_id = str(msg.get("tool_call_id") or "")
                    tool_name = str(msg.get("name") or tool_call_names.get(tool_call_id, ""))
                    try:
                        content_text = msg.get("content", "{}")
                        if isinstance(content_text, str) and "[TOOL_OUTPUT_SAVED_TO]:" in content_text:
                            content_text = content_text.split("[TOOL_OUTPUT_SAVED_TO]:", 1)[0].strip()
                        tool_content = json.loads(content_text)
                        if not tool_name:
                            tool_name = str(tool_content.get("tool") or "")
                        tool_data = tool_content.get("data", {})

                        if tool_name == "claim_drafter" and tool_content.get("success"):
                            candidate_claims = self._normalize_claims_payload(
                                tool_data,
                                raw_response=tool_content.get("raw_response"),
                            )
                            if candidate_claims.get("independent_claim"):
                                claims_data = candidate_claims
                            claims_count = (
                                (1 if str(claims_data.get("independent_claim") or "").strip() else 0)
                                + len(claims_data.get("dependent_claims", []) or [])
                            )
                            self._logger.info(
                                f"Got claims from tool: {claims_count} claims"
                            )
                            if claims_count:
                                _emit_writer_section_result(
                                    "claims",
                                    "权利要求书",
                                    claims_data.get("independent_claim", ""),
                                    {"claims_count": claims_count},
                                )

                        elif tool_name == "description_writer" and tool_content.get("success"):
                            section_type = tool_data.get("section_type", "")
                            content = tool_data.get("content", "")
                            section_label = {
                                "technical_field": "技术领域",
                                "background": "背景技术",
                                "summary": "发明内容",
                                "drawings": "附图说明",
                                "drawings_description": "附图说明",
                                "detailed": "具体实施方式",
                            }.get(str(section_type), str(section_type) or "说明书章节")
                            if section_type == "technical_field":
                                description_data["technical_field"] = content
                            elif section_type == "background":
                                description_data["background_art"] = content
                            elif section_type == "summary":
                                description_data["summary_of_invention"] = content
                            elif section_type in {"drawings", "drawings_description"}:
                                description_data["drawings_description"] = content
                            elif section_type == "detailed":
                                description_data["detailed_description"] = content
                            self._logger.info(f"Got description section: {section_type}")
                            if content:
                                _emit_writer_section_result(
                                    f"description.{section_type}",
                                    section_label,
                                    content,
                                )

                        elif tool_name == "patent_docx_generator" and tool_content.get("success"):
                            docx_path = tool_data.get("file_path", "")
                            abstract_text = tool_data.get("abstract", "") or abstract_text
                            self._logger.info(f"DOCX generated: {docx_path}")
                            if abstract_text:
                                _emit_writer_section_result("abstract", "说明书摘要", abstract_text)

                        elif (
                            tool_name == "patent_drawing_generator"
                            and tool_content.get("success")
                            and allow_drawing_generation
                        ):
                            drawings = tool_data.get("drawings", [])
                            if isinstance(drawings, list):
                                drawings_data.extend(item for item in drawings if isinstance(item, dict))
                            self._logger.info(f"Got patent drawings: {len(drawings_data)} drawings")
                            if drawings_data:
                                titles = [
                                    str(item.get("figure_number") or item.get("title") or "").strip()
                                    for item in drawings_data
                                    if isinstance(item, dict)
                                ]
                                _emit_writer_section_result(
                                    "drawings",
                                    "附图清单",
                                    "、".join(title for title in titles if title),
                                    {"drawing_count": len(drawings_data)},
                                )

                    except (json.JSONDecodeError, KeyError) as e:
                        self._logger.warning(f"Failed to parse tool result: {e}")
                        continue

            agent_structured_output: Dict[str, Any] = {}
            if isinstance(agent_result, dict):
                candidate = agent_result.get("structured_result")
                if isinstance(candidate, dict):
                    agent_structured_output = candidate
            if not agent_structured_output:
                parsed_final = self._try_parse_json(final_response)
                if isinstance(parsed_final, dict) and "raw_output" not in parsed_final:
                    agent_structured_output = parsed_final

            if isinstance(agent_structured_output, dict):
                candidate_claims = agent_structured_output.get("claims")
                if isinstance(candidate_claims, dict):
                    normalized_claims = self._normalize_claims_payload(candidate_claims)
                    if normalized_claims.get("independent_claim"):
                        claims_data = normalized_claims
                        _emit_writer_section_result(
                            "claims",
                            "权利要求书",
                            normalized_claims.get("independent_claim", ""),
                            {
                                "claims_count": 1 + len(normalized_claims.get("dependent_claims") or []),
                                "source": "agent_final_json",
                            },
                        )

                candidate_description = agent_structured_output.get("description")
                if isinstance(candidate_description, dict):
                    for source_key, target_key in (
                        ("technical_field", "technical_field"),
                        ("background_art", "background_art"),
                        ("summary_of_invention", "summary_of_invention"),
                        ("description_of_drawings", "drawings_description"),
                        ("drawings_description", "drawings_description"),
                        ("detailed_description", "detailed_description"),
                    ):
                        value = candidate_description.get(source_key)
                        if isinstance(value, str) and value.strip():
                            description_data[target_key] = value.strip()
                            section_label = {
                                "technical_field": "技术领域",
                                "background_art": "背景技术",
                                "summary_of_invention": "发明内容",
                                "drawings_description": "附图说明",
                                "detailed_description": "具体实施方式",
                            }.get(target_key, "说明书章节")
                            _emit_writer_section_result(
                                f"description.{target_key}",
                                section_label,
                                value,
                                {"source": "agent_final_json"},
                            )

                if isinstance(agent_structured_output.get("abstract"), str):
                    abstract_text = agent_structured_output["abstract"].strip() or abstract_text
                    if abstract_text:
                        _emit_writer_section_result(
                            "abstract",
                            "说明书摘要",
                            abstract_text,
                            {"source": "agent_final_json"},
                        )

                candidate_drawings = agent_structured_output.get("drawings")
                if isinstance(candidate_drawings, list):
                    candidate_drawing_items = [
                        item for item in candidate_drawings if isinstance(item, dict)
                    ]
                    if allow_drawing_generation or candidate_drawing_items:
                        drawings_data = candidate_drawing_items
                    if drawings_data:
                        _emit_writer_section_result(
                            "drawings",
                            "附图清单",
                            "、".join(
                                str(item.get("figure_number") or item.get("title") or "").strip()
                                for item in drawings_data
                                if isinstance(item, dict)
                            ),
                            {"drawing_count": len(drawings_data), "source": "agent_final_json"},
                        )

            has_partial_content = bool(
                claims_data
                or any(description_data.values())
                or abstract_text
                or drawings_data
            )
            if (
                not agent_failed
                and has_partial_content
                and not claims_data.get("independent_claim", "").strip()
            ):
                agent_failed = True
                incomplete_error = "专利撰写输出不完整：缺少权利要求书"
                if isinstance(agent_result, dict):
                    agent_result = dict(agent_result)
                    agent_result["failed"] = True
                    agent_result["completed"] = False
                    agent_result["error"] = incomplete_error
                else:
                    agent_result = {
                        "failed": True,
                        "completed": False,
                        "error": incomplete_error,
                    }

            if not agent_failed:
                last_failed_result = None
                break

            last_failed_result = agent_result if isinstance(agent_result, dict) else None
            if not has_partial_content:
                failed_result: Dict[str, Any]
                if isinstance(agent_result, dict):
                    failed_result = agent_result
                else:
                    failed_result = {
                        "failed": True,
                        "completed": False,
                        "error": "专利撰写中断",
                    }
                return self._normalize_phase_output("patent_draft", failed_result)
            if writer_attempt >= 2:
                break

            completed_items = []
            if claims_data.get("independent_claim"):
                completed_items.append("权利要求书已完成，请不要重新生成权利要求书")
            if description_data.get("technical_field"):
                completed_items.append("技术领域已完成")
            if description_data.get("background_art"):
                completed_items.append("背景技术已完成")
            if description_data.get("summary_of_invention"):
                completed_items.append("发明内容已完成")
            if description_data.get("detailed_description"):
                completed_items.append("具体实施方式已完成")
            if abstract_text:
                completed_items.append("说明书摘要已完成")

            missing_items = []
            if not claims_data.get("independent_claim"):
                missing_items.append("权利要求书")
            elif not claims_data.get("dependent_claims"):
                missing_items.append("从属权利要求")
            if not description_data.get("technical_field"):
                missing_items.append("技术领域")
            if not description_data.get("background_art"):
                missing_items.append("背景技术")
            if not description_data.get("summary_of_invention"):
                missing_items.append("发明内容")
            if not description_data.get("detailed_description"):
                missing_items.append("具体实施方式")
            if not abstract_text:
                missing_items.append("说明书摘要")

            error_text = str(agent_result.get("error") or "专利撰写中断") if isinstance(agent_result, dict) else "专利撰写中断"
            task_prompt = f"""专利撰写过程中发生错误，需要从已完成内容之后继续撰写，不要从头重写。

【本次错误】
{error_text}

【已完成内容】
{chr(10).join(f"- {item}" for item in completed_items)}

【待补全内容】
{chr(10).join(f"- {item}" for item in missing_items)}

【继续要求】
1. 只调用工具补全待补全内容。
2. 已完成内容不要重新生成、不要改写、不要重复输出。
3. 补全时保持与已完成权利要求和说明书章节一致。
4. 本阶段仍然只生成专利内容，不生成最终文档文件。"""

        if last_failed_result is not None:
            repaired = await self._repair_incomplete_patent_draft_with_agent(
                context=context,
                claims_data=claims_data,
                description_data=description_data,
                abstract_text=abstract_text,
                event_callback=event_callback,
            )
            claims_data = repaired["claims"]
            description_data = repaired["description"]
            abstract_text = repaired["abstract"]

        required_sections_present = all(
            str(description_data.get(key) or "").strip()
            for key in (
                "technical_field",
                "background_art",
                "summary_of_invention",
                "detailed_description",
            )
        )
        if (
            last_failed_result is not None
            and (
                not claims_data.get("independent_claim", "").strip()
                or not required_sections_present
            )
        ):
            return {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_agent_error": str(last_failed_result.get("error") or "专利撰写中断")[:500],
                "claims": {
                    "independent_claim": claims_data.get("independent_claim", ""),
                    "dependent_claims": claims_data.get("dependent_claims", []),
                },
                "description": {
                    "technical_field": description_data.get("technical_field", ""),
                    "background_art": description_data.get("background_art", ""),
                    "summary_of_invention": description_data.get("summary_of_invention", ""),
                    "drawings_description": description_data.get("drawings_description", ""),
                    "detailed_description": description_data.get("detailed_description", ""),
                },
                "abstract": abstract_text,
                "drawings": drawings_data,
                "docx_path": "",
                "full_response": final_response,
            }
        
        # 如果 Hermes 工具调用和 Agent 结构化 JSON 都没有返回专利内容，明确失败。
        # 不再从文本中的 <tool_call> 片段伪造工具结果；工具必须由 Agent 真实调用。
        if not claims_data and not description_data:
            self._logger.warning(
                "Patent writer produced no structured Hermes tool or JSON result; marking draft incomplete"
            )
            return {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_agent_error": "专利撰写 Agent 未返回可解析的结构化专利文件，不能由本地文本解析或伪造工具结果替代。",
                "claims": {"independent_claim": "", "dependent_claims": []},
                "description": {
                    "technical_field": "",
                    "background_art": "",
                    "summary_of_invention": "",
                    "drawings_description": "",
                    "detailed_description": "",
                },
                "abstract": "",
                "drawings": drawings_data,
                "docx_path": "",
                "full_response": final_response,
            }
        
        # 组装为前端期望的结构化格式（不含 docx，待质量审查通过后生成）
        patent_result: Dict[str, Any] = {
            "title": context.title or context.metadata.get("confirmed_preflight", {}).get("patent_title", ""),
            "patent_title": context.title or context.metadata.get("confirmed_preflight", {}).get("patent_title", ""),
            "claims": {
                "independent_claim": claims_data.get("independent_claim", ""),
                "dependent_claims": claims_data.get("dependent_claims", []),
            },
            "description": {
                "technical_field": description_data.get("technical_field", ""),
                "background_art": description_data.get("background_art", ""),
                "summary_of_invention": description_data.get("summary_of_invention", ""),
                "drawings_description": description_data.get("drawings_description", ""),
                "detailed_description": description_data.get("detailed_description", ""),
            },
            "abstract": abstract_text,
            "drawings": drawings_data,
            "docx_path": "",
            "full_response": final_response,
        }
        patent_result = self._apply_patent_manual_normalization(
            patent_result,
            context_title=context.title,
        )

        claims_count = 1 + len(patent_result["claims"]["dependent_claims"]) if patent_result["claims"]["independent_claim"] else 0
        sections_count = sum(1 for v in patent_result["description"].values() if v)
        self._logger.info(f"Patent writer: content generated. Claims={claims_count}, Sections={sections_count} (DOCX deferred to post-review)")

        return patent_result

    async def _repair_incomplete_patent_draft_with_agent(
        self,
        context: WorkflowContext,
        claims_data: Dict[str, Any],
        description_data: Dict[str, Any],
        abstract_text: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Ask the patent writer Agent to repair an incomplete draft.

        Subjective drafting is intentionally kept inside the Hermes Agent LLM. The
        workflow engine may pass existing content and missing sections, but must not
        synthesize patent text or directly call writer tools outside the Agent loop.
        """
        if event_callback:
            event_callback(
                "CEO Agent",
                "agent.thinking",
                "🛠️ 撰写内容未补齐，继续调度专利撰写 Agent 补全必要章节",
                {"agent_name": "CEO Agent", "thought": "repair_incomplete_patent_draft"},
            )
        missing_items = []
        if not str((claims_data or {}).get("independent_claim") or "").strip():
            missing_items.append("权利要求书")
        for field_name, label in (
            ("technical_field", "技术领域"),
            ("background_art", "背景技术"),
            ("summary_of_invention", "发明内容"),
            ("detailed_description", "具体实施方式"),
        ):
            if not str((description_data or {}).get(field_name) or "").strip():
                missing_items.append(label)
        if not str(abstract_text or "").strip():
            missing_items.append("说明书摘要")
        requirement_output = self._latest_phase_output(
            context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
        )
        retrieval_output = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        confirmed_writer_context = self._build_confirmed_writer_context(
            context,
            requirement_output=requirement_output,
            retrieval_output=retrieval_output,
            limit=18000,
        )

        repair_prompt = f"""上一轮专利撰写输出不完整，请作为专利撰写 Agent 继续补齐，不要从头重写。

【已确认撰写上下文】
{confirmed_writer_context}

【需求分析】
{json.dumps(requirement_output or {}, ensure_ascii=False)[:3000]}

【检索报告】
{self._build_retrieval_summary_for_writer(retrieval_output, limit=12000)}

【已完成权利要求】
{json.dumps(claims_data or {}, ensure_ascii=False)[:6000]}

【已完成说明书】
{json.dumps(description_data or {}, ensure_ascii=False)[:8000]}

【已完成摘要】
{abstract_text or ""}

【待补齐内容】
{chr(10).join(f"- {item}" for item in missing_items) or "- 复核全部内容完整性"}

请按需调用 Hermes 工具获取结构、约束或支持性信号，但正式专利正文必须由你通过 LLM 生成。
最终只输出严格 JSON，格式为：
{{
  "claims": {{"independent_claim": "...", "dependent_claims": ["..."]}},
  "description": {{
    "technical_field": "...",
    "background_art": "...",
    "summary_of_invention": "...",
    "description_of_drawings": "...",
    "detailed_description": "..."
  }},
  "abstract": "...",
  "drawings": []
}}"""
        raw = await _run_agent_conversation_with_timeout(
            "patent.writer.v1",
            repair_prompt,
            timeout_seconds=_configured_timeout_seconds(
                "writer_revision_timeout_seconds",
                WRITER_REVISION_TIMEOUT_SECONDS,
            ),
        )
        if isinstance(raw, dict):
            text = raw.get("final_response", "") or raw.get("content", "") or json.dumps(raw, ensure_ascii=False)
            structured = raw.get("structured_result") if isinstance(raw.get("structured_result"), dict) else None
        else:
            text = str(raw or "")
            structured = None
        parsed = structured or self._try_parse_json(text)
        if not isinstance(parsed, dict) or "raw_output" in parsed:
            parsed = {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_agent_error": "专利撰写 Agent 补齐结果不是有效 JSON，不能由本地文本解析替代。",
                "claims": {},
                "description": {},
                "abstract": "",
            }

        repaired_claims = dict(claims_data or {})
        parsed_claims = parsed.get("claims")
        if isinstance(parsed_claims, dict):
            normalized_claims = self._normalize_claims_payload(parsed_claims)
            if normalized_claims.get("independent_claim"):
                repaired_claims = normalized_claims

        repaired_description = dict(description_data or {})
        parsed_description = parsed.get("description")
        if isinstance(parsed_description, dict):
            for source_key, target_key in (
                ("technical_field", "technical_field"),
                ("background_art", "background_art"),
                ("summary_of_invention", "summary_of_invention"),
                ("description_of_drawings", "drawings_description"),
                ("drawings_description", "drawings_description"),
                ("detailed_description", "detailed_description"),
            ):
                value = parsed_description.get(source_key)
                if isinstance(value, str) and value.strip():
                    repaired_description[target_key] = value.strip()

        repaired_abstract = abstract_text or ""
        if isinstance(parsed.get("abstract"), str) and parsed["abstract"].strip():
            repaired_abstract = parsed["abstract"].strip()

        return {
            "claims": repaired_claims,
            "description": repaired_description,
            "abstract": repaired_abstract,
        }
    
    def _normalize_claims_payload(
        self,
        payload: Any,
        raw_response: Any = None,
    ) -> Dict[str, Any]:
        """Normalize claim_drafter output from structured tool data or wrapper JSON."""
        candidates: List[Any] = []
        if isinstance(payload, dict):
            candidates.append(payload)
            if isinstance(payload.get("claims"), dict):
                candidates.append(payload["claims"])
            if isinstance(payload.get("data"), dict):
                candidates.append(payload["data"])
                if isinstance(payload["data"].get("claims"), dict):
                    candidates.append(payload["data"]["claims"])

        if isinstance(raw_response, str) and raw_response.strip():
            parsed_raw = self._try_parse_json(raw_response)
            if isinstance(parsed_raw, dict):
                candidates.append(parsed_raw)
                if isinstance(parsed_raw.get("claims"), dict):
                    candidates.append(parsed_raw["claims"])
                if isinstance(parsed_raw.get("data"), dict):
                    candidates.append(parsed_raw["data"])
                    if isinstance(parsed_raw["data"].get("claims"), dict):
                        candidates.append(parsed_raw["data"]["claims"])

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            independent = str(
                candidate.get("independent_claim")
                or candidate.get("independent_claims")
                or candidate.get("claim_1")
                or candidate.get("claim1")
                or ""
            ).strip()
            dependent_raw = candidate.get("dependent_claims") or candidate.get("dependent_claim") or []
            if isinstance(dependent_raw, str):
                dependent_claims = [dependent_raw.strip()] if dependent_raw.strip() else []
            elif isinstance(dependent_raw, list):
                dependent_claims = [
                    str(claim).strip() for claim in dependent_raw if str(claim).strip()
                ]
            else:
                dependent_claims = []

            all_claims = candidate.get("claims_list") or candidate.get("all_claims")
            if isinstance(all_claims, list):
                normalized_all = [str(claim).strip() for claim in all_claims if str(claim).strip()]
                if not independent and normalized_all:
                    independent = normalized_all[0]
                    dependent_claims.extend(normalized_all[1:])

            if independent:
                return {
                    "independent_claim": independent,
                    "dependent_claims": dependent_claims,
                    "claim_tree": candidate.get("claim_tree", {}),
                    "protection_breadth": candidate.get("protection_breadth", ""),
                    "drafting_notes": candidate.get("drafting_notes", ""),
                }

        return {"independent_claim": "", "dependent_claims": []}

