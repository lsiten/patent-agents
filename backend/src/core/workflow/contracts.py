# -*- coding: utf-8 -*-
"""WorkflowContractMixin methods split from the workflow engine."""
from .shared import *


class WorkflowContractMixin:
    def _build_context_data_from_agent_response(
        self,
        agent_id: str,
        agent_text: Any,
        agent_tool_results: List[Dict[str, Any]],
        structured_result: Any = None,
    ) -> Dict[str, Any]:
        """Build normalized phase input from text plus optional structured agent result."""
        text = agent_text if isinstance(agent_text, str) else ""

        if isinstance(structured_result, dict):
            context_data = dict(structured_result)
        else:
            parsed = self._try_parse_json(text)
            if "raw_output" not in parsed:
                context_data = parsed
            else:
                context_data = {"agent": agent_id, "output": text, "summary": text[:500]}

        if agent_tool_results:
            context_data["tool_results"] = agent_tool_results
        return self._unwrap_agent_envelope(context_field="", data=context_data)

    def _unwrap_agent_envelope(self, context_field: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured JSON from Hermes Agent response envelopes.

        Hermes returns the Agent's natural final answer inside fields such as
        final_response/message/content. The workflow contract must validate that
        inner answer, while preserving tool traces for the UI. This is parsing
        only; it never invents missing phase fields.
        """
        if not isinstance(data, dict) or not data:
            return data
        if data.get("failed") is True or data.get("_agent_failed") is True:
            return data

        envelope_keys = ("final_response", "message", "content", "text", "output")
        for key in envelope_keys:
            raw_value = data.get(key)
            if not isinstance(raw_value, str) or not raw_value.strip():
                continue
            parsed = self._try_parse_json(raw_value.strip())
            if not parsed or "raw_output" in parsed:
                continue
            normalized = dict(parsed)
            for preserve_key in (
                "tool_results",
                "_agent_tool_results",
                "events",
                "steps",
                "agent",
            ):
                if preserve_key in data and preserve_key not in normalized:
                    normalized[preserve_key] = data[preserve_key]
            normalized["_agent_envelope_normalized"] = True
            normalized["_raw_final_response"] = raw_value[:2000]
            if context_field:
                normalized["_context_field"] = context_field
            return normalized

        return data

    def _has_contract_value(self, value: Any) -> bool:
        if isinstance(value, dict):
            return any(self._has_contract_value(v) for v in value.values())
        if isinstance(value, list):
            return any(self._has_contract_value(v) for v in value)
        return bool(str(value or "").strip())

    def _validate_phase_contract(self, context_field: str, data: Any) -> List[str]:
        """Deterministic input/output contract gate for phase artifacts.

        This only checks structure and artifact presence. It must not decide
        patentability, creativity, claim scope, or writing quality.
        """
        if not isinstance(data, dict) or not data:
            return [f"{context_field} 未返回结构化对象"]
        if data.get("_agent_failed") is True:
            return [str(data.get("_agent_error") or f"{context_field} Agent 执行失败")]

        required_by_field = {
            "requirement_analysis": [
                "tech_field",
                "core_principle",
                "technical_problem",
                "beneficial_effects",
                "key_innovative_features",
                "application_scenarios",
                "patent_type_recommendation",
                "claim_skeleton",
            ],
            "retrieval_report": [
                "retrieval_strategy",
            ],
            "patent_draft": [
                "claims",
                "description",
                "abstract",
            ],
            "review_report": [
                "recommendation",
                "review_summary",
            ],
        }
        issues: List[str] = []
        for field_name in required_by_field.get(context_field, []):
            if not self._has_contract_value(data.get(field_name)):
                issues.append(f"{context_field} 缺少必需字段：{field_name}")

        if context_field == "retrieval_report":
            strategy = data.get("retrieval_strategy")
            keywords = data.get("retrieval_keywords")
            if isinstance(strategy, dict):
                keywords = strategy.get("keywords") or keywords
            if not self._has_contract_value(keywords):
                issues.append("retrieval_report 缺少实际检索关键词")

        if context_field == "patent_draft":
            claims = data.get("claims") if isinstance(data.get("claims"), dict) else {}
            if not self._has_contract_value(claims.get("independent_claim")):
                issues.append("patent_draft 缺少独立权利要求")
            if not self._has_contract_value(claims.get("dependent_claims")):
                issues.append("patent_draft 缺少从属权利要求")
            description = data.get("description") if isinstance(data.get("description"), dict) else {}
            for section in (
                "technical_field",
                "background_art",
                "summary_of_invention",
                "detailed_description",
            ):
                if not self._has_contract_value(description.get(section)):
                    issues.append(f"patent_draft 说明书缺少章节：{section}")
            for draft_issue in self._validate_patent_draft_completeness(data):
                if draft_issue in {
                    "patent_draft_agent_failed",
                    "patent_draft_incomplete_output",
                    "independent_claim_missing",
                    "dependent_claims_missing",
                    "claims_missing",
                    "description_missing",
                    "abstract_missing",
                }:
                    continue
                issues.append(f"patent_draft 硬规则不合格：{draft_issue}")
            working_docx_path = str(
                data.get("working_docx_path")
                or data.get("docx_draft_path")
                or data.get("draft_docx_path")
                or ""
            ).strip()
            if not working_docx_path:
                issues.append("patent_draft 缺少工作草稿 DOCX 路径：working_docx_path")

        if context_field == "review_report" and self._check_review_needs_revision(data):
            root_cause = str(data.get("root_cause") or "").strip()
            if root_cause not in {
                "content_incomplete",
                "requirement_unclear",
                "evidence_missing",
                "external_info_missing",
                "system_failure",
            }:
                issues.append("review_report 未通过时必须包含合法 root_cause")
            for issue in self._extract_review_issue_records(data):
                severity = str(issue.get("severity") or issue.get("likelihood") or "").lower()
                if severity not in {"high", "critical"}:
                    continue
                responsible_phase = str(
                    issue.get("responsible_phase")
                    or issue.get("target_phase")
                    or issue.get("route_to")
                    or ""
                ).strip()
                if responsible_phase not in {
                    "requirement_analysis",
                    "retrieval_analysis",
                    "patent_writing",
                    "user_input",
                    "system_failure",
                }:
                    issues.append("review_report high/critical 问题缺少合法 responsible_phase")
                    break

        return issues

    def _build_phase_contract_error(
        self,
        context_field: str,
        data: Any,
        issues: List[str],
    ) -> Dict[str, Any]:
        return {
            "_agent_failed": True,
            "_contract_failed": True,
            "_context_field": context_field,
            "_agent_error": "阶段输出不符合输入/输出契约：" + "；".join(issues[:8]),
            "_contract_issues": issues,
            "_raw_output": json.dumps(data, ensure_ascii=False, default=str)[:3000],
            "responsible_phase": context_field,
        }

    def _normalize_phase_output(self, context_field: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """将 Agent 输出规范化为前端期望的数据格式

        不同阶段的 Agent 输出字段名可能与前端渲染器期望的不完全匹配，
        此方法做必要的字段映射和结构转换。

        关键：检测 Agent 自身执行失败 (failed: True) — 这种情况下必须明确
        标记 _agent_failed=True，让下游 iteration loop 知道需要重试。
        不要用 "待生成" 之类的占位符掩盖失败。
        """
        if not isinstance(data, dict):
            return data

        data = self._unwrap_agent_envelope(context_field, data)

        if context_field == "review_report" and (
            isinstance(data.get("final_response"), str)
            or isinstance(data.get("message"), str)
        ):
            normalized_review = self._build_review_report_from_agent_envelope(data)
            if normalized_review:
                data = normalized_review

        # ═══ 检测 Agent 自身执行失败 (LLM API 错误等) ═══
        # 当 run_conversation 返回 {"failed": True, "error": "..."} 时
        # 必须显式标记 _agent_failed=True，否则 _check_review_needs_revision
        # 会读到空的 recommendation / issues 并误判为"没有问题"
        if data.get("failed") is True or data.get("completed") is False and data.get("error"):
            agent_error = data.get("error", "Agent execution failed")
            error_preview = str(agent_error)[:500]
            self._logger.warning(
                f"Agent failure detected in {context_field}: {error_preview}"
            )
            return self._build_agent_output_error(
                context_field=context_field,
                output_text=json.dumps(data, ensure_ascii=False),
                reason=error_preview,
            )

        # ═══ 处理 {agent, output, summary} 格式 ═══
        # 当 JSON 解析失败时，数据会被包装成这种格式
        # 需要尝试从 output 字段中提取结构化数据
        raw_output_text = None
        if "output" in data and "agent" in data and isinstance(data.get("output"), str):
            raw_output_text = data["output"]
            # 尝试从 output 中解析 JSON
            parsed = self._try_parse_json(raw_output_text)
            if "raw_output" not in parsed and parsed:
                # 成功解析出结构化数据，使用解析结果
                data = parsed

        # ═══ 无法解析时只返回失败信息，不生成阶段内容 ═══
        if "raw_output" in data or ("agent" in data and "output" in data):
            output_text = raw_output_text or data.get("output", "") or data.get("raw_output", "")
            return self._build_agent_output_error(
                context_field=context_field,
                output_text=output_text,
                reason=f"{context_field} Agent 输出无法解析为当前要求的结构化数据",
            )

        if context_field == "patent_draft" and isinstance(data.get("tool_results"), list):
            normalized_from_tools = self._normalize_patent_draft_tool_results(data["tool_results"])
            if normalized_from_tools:
                normalized_from_tools["full_response"] = str(
                    data.get("final_response") or data.get("message") or data.get("text") or ""
                )
                return normalized_from_tools

        if context_field == "requirement_analysis":
            # tech_field: 如果是嵌套对象，提取 primary_domain 作为字符串
            tf = data.get("tech_field")
            if isinstance(tf, dict):
                data["tech_field"] = tf.get("primary_domain", "")

            # key_innovative_features: 规范化字段名（feature_name → name）
            features = data.get("key_innovative_features") or data.get("key_features", [])
            if isinstance(features, list) and features:
                normalized = []
                for f in features:
                    if isinstance(f, dict):
                        normalized.append({
                            "name": f.get("feature_name", "") or f.get("name", ""),
                            "description": f.get("description", ""),
                            "technical_significance": f.get("technical_significance", "")
                                or ("核心创新" if f.get("is_core") else
                                    "创新特征" if f.get("is_innovative") else ""),
                        })
                    elif isinstance(f, str):
                        normalized.append({"name": f, "description": "", "technical_significance": ""})
                data["key_innovative_features"] = normalized

            # application_scenarios: 如果是对象列表，提取 scenario 字段为字符串列表
            scenarios = data.get("application_scenarios", [])
            if isinstance(scenarios, list) and scenarios and isinstance(scenarios[0], dict):
                data["application_scenarios"] = [
                    s.get("scenario", "") or s.get("name", "") or str(s)
                    for s in scenarios if isinstance(s, dict)
                ]

            # beneficial_effects: 如果是对象列表，提取 effect 字段为字符串列表
            effects = data.get("beneficial_effects", [])
            if isinstance(effects, list) and effects and isinstance(effects[0], dict):
                data["beneficial_effects"] = [
                    e.get("effect", "") or e.get("description", "") or str(e)
                    for e in effects if isinstance(e, dict)
                ]

            # information_gaps: 如果是对象列表，提取 gap 字段为字符串列表
            gaps = data.get("information_gaps", [])
            if isinstance(gaps, list) and gaps and isinstance(gaps[0], dict):
                data["information_gaps"] = [
                    g.get("gap", "") or g.get("description", "") or str(g)
                    for g in gaps if isinstance(g, dict)
                ]

            # patent_type_recommendation: 保持为对象 {suggested_type, rationale}
            if "patent_type" in data and "patent_type_recommendation" not in data:
                data["patent_type_recommendation"] = {
                    "suggested_type": data.get("patent_type", ""),
                    "rationale": data.get("recommendation_rationale", ""),
                }
            # 如果 patent_type_recommendation 已经存在但格式正确，保留原样

        elif context_field == "retrieval_report":
            # ═══ patentability_scores → novelty_assessment / inventive_step_assessment / utility_assessment ═══
            scores = data.get("patentability_scores", {})
            if isinstance(scores, dict):
                if "novelty" in scores and "novelty_assessment" not in data:
                    n = scores["novelty"]
                    if isinstance(n, dict):
                        data["novelty_assessment"] = {
                            "rating": n.get("rating", "unknown"),
                            "rationale": n.get("details", "") or n.get("rationale", ""),
                        }
                if "inventive_step" in scores and "inventive_step_assessment" not in data:
                    i = scores["inventive_step"]
                    if isinstance(i, dict):
                        data["inventive_step_assessment"] = {
                            "rating": i.get("rating", "unknown"),
                            "rationale": i.get("details", "") or i.get("rationale", ""),
                        }
                if "utility" in scores and "utility_assessment" not in data:
                    u = scores["utility"]
                    if isinstance(u, dict):
                        data["utility_assessment"] = {
                            "rating": u.get("rating", "unknown"),
                            "rationale": u.get("details", "") or u.get("rationale", ""),
                        }
            # ═══ similarity_results → prior_art_references / similar_patents ═══
            sim_results = data.get("similarity_results", [])
            if isinstance(sim_results, list) and sim_results and "prior_art_references" not in data:
                refs = []
                for p in sim_results:
                    if not isinstance(p, dict):
                        continue
                    score = p.get("similarity_score", 0)
                    if isinstance(score, (int, float)) and score >= 0.7:
                        relevance = "high"
                    elif isinstance(score, (int, float)) and score >= 0.4:
                        relevance = "medium"
                    else:
                        relevance = "low"
                    
                    patent_id = p.get("patent_id", "")
                    source = p.get("source", "")
                    url = self._build_patent_url(patent_id, source)
                    
                    # 提取区别特征
                    diff_features = p.get("distinguishing_features", [])
                    differences = "; ".join(diff_features) if isinstance(diff_features, list) else str(diff_features)
                    
                    refs.append({
                        "title": p.get("title", ""),
                        "reference_id": patent_id,
                        "source": source,
                        "relevance": relevance,
                        "abstract": p.get("abstract", ""),
                        "differences": differences,
                        "url": url,
                        "applicant": p.get("applicant", ""),
                        "publication_date": p.get("publication_date", ""),
                        "similarity_score": score,
                        "matching_features": p.get("matching_features", []),
                    })
                if refs:
                    data["prior_art_references"] = refs
                    data["similar_patents"] = refs  # 保留给既有前端字段读取

            # ═══ risk_assessment.risk_factors → risk_factors ═══
            risk_assess = data.get("risk_assessment", {})
            if isinstance(risk_assess, dict) and "risk_factors" not in data:
                data["risk_factors"] = risk_assess.get("risk_factors", [])
                data["overall_risk_level"] = risk_assess.get("overall_risk_level", "unknown")

            # retrieval_strategy.keywords → retrieval_keywords (顶层)
            strategy = data.get("retrieval_strategy", {})
            if isinstance(strategy, dict):
                if "retrieval_keywords" not in data and strategy.get("keywords"):
                    data["retrieval_keywords"] = strategy["keywords"]
                if "retrieval_databases" not in data and strategy.get("databases_used"):
                    data["retrieval_databases"] = strategy["databases_used"]

            # similar_patents → prior_art_references (front-end normalized format)
            if "similar_patents" in data and "prior_art_references" not in data:
                patents = data.get("similar_patents", [])
                if isinstance(patents, list):
                    refs = []
                    for p in patents:
                        if not isinstance(p, dict):
                            continue
                        # 根据 similarity_score 或 risk_level 映射为 relevance
                        score = p.get("similarity_score", 0)
                        risk = p.get("risk_level", "")
                        if risk == "high" or (isinstance(score, (int, float)) and score >= 0.7):
                            relevance = "high"
                        elif risk == "medium" or (isinstance(score, (int, float)) and score >= 0.4):
                            relevance = "medium"
                        else:
                            relevance = "low"

                        # 构造 URL（基于 source + patent_id）
                        patent_id = p.get("patent_id", "")
                        source = p.get("source", "")
                        url = self._build_patent_url(patent_id, source)

                        refs.append({
                            "title": p.get("title", ""),
                            "reference_id": patent_id,
                            "source": source,
                            "relevance": relevance,
                            "abstract": p.get("abstract", ""),
                            "differences": "; ".join(p.get("key_differences", []))
                                if isinstance(p.get("key_differences"), list)
                                else p.get("key_differences", ""),
                            "url": url,
                            "applicant": p.get("applicant", ""),
                            "publication_date": p.get("publication_date", ""),
                            "similarity_score": score,
                        })
                    if refs:
                        data["prior_art_references"] = refs

            # novelty + novelty_rationale → novelty_assessment
            if "novelty" in data and "novelty_assessment" not in data:
                data["novelty_assessment"] = {
                    "rating": data.get("novelty", ""),
                    "rationale": data.get("novelty_rationale", ""),
                }
            # inventive_step + inventive_step_rationale → inventive_step_assessment
            if "inventive_step" in data and "inventive_step_assessment" not in data:
                data["inventive_step_assessment"] = {
                    "rating": data.get("inventive_step", ""),
                    "rationale": data.get("inventive_step_rationale", ""),
                }
            # utility + utility_rationale → utility_assessment
            if "utility" in data and "utility_assessment" not in data:
                data["utility_assessment"] = {
                    "rating": data.get("utility", ""),
                    "rationale": data.get("utility_rationale", ""),
                }

            # ===== 结构化字段归一化：兼容 Agent 输出中的等价字段名 =====

            # 1. 关键词字段: keywords_cn/keywords_en → retrieval_keywords
            if not data.get("retrieval_keywords"):
                keywords_fb = data.get("keywords_cn") or data.get("keywords_en") or data.get("query")
                if isinstance(keywords_fb, list):
                    data["retrieval_keywords"] = keywords_fb
                elif isinstance(keywords_fb, str) and keywords_fb.strip():
                    data["retrieval_keywords"] = [keywords_fb.strip()]

            # 2. 风险因素字段: risks → risk_factors
            if "risk_factors" not in data and "risks" in data:
                risks = data["risks"]
                if isinstance(risks, list):
                    normalized = []
                    for r in risks:
                        if isinstance(r, dict):
                            normalized.append({
                                "type": r.get("risk_type", "") or r.get("type", ""),
                                "description": r.get("description", ""),
                                "severity": r.get("severity", "medium"),
                                "mitigation": r.get("mitigation", "") or r.get("mitigation_strategy", ""),
                            })
                    data["risk_factors"] = normalized

            # 3. 新颖性字段: novelty_score + novelty_rationale → novelty_assessment
            if "novelty_assessment" not in data:
                score = data.get("novelty_score")
                rationale = data.get("novelty_rationale")
                if score is not None or rationale:
                    rating = "unknown"
                    if isinstance(score, (int, float)):
                        if score >= 0.7:
                            rating = "high"
                        elif score >= 0.4:
                            rating = "medium"
                        else:
                            rating = "low"
                    data["novelty_assessment"] = {
                        "rating": rating,
                        "rationale": str(rationale) if rationale else "",
                    }

            # 4. 创造性字段: inventive_step_score + inventive_step_rationale → inventive_step_assessment
            if "inventive_step_assessment" not in data:
                score = data.get("inventive_step_score")
                rationale = data.get("inventive_step_rationale")
                if score is not None or rationale:
                    rating = "unknown"
                    if isinstance(score, (int, float)):
                        if score >= 0.7:
                            rating = "high"
                        elif score >= 0.4:
                            rating = "medium"
                        else:
                            rating = "low"
                    data["inventive_step_assessment"] = {
                        "rating": rating,
                        "rationale": str(rationale) if rationale else "",
                    }

            # 5. 实用性字段: utility_score + utility_rationale → utility_assessment
            if "utility_assessment" not in data:
                score = data.get("utility_score")
                rationale = data.get("utility_rationale")
                if score is not None or rationale:
                    rating = "unknown"
                    if isinstance(score, (int, float)):
                        if score >= 0.7:
                            rating = "high"
                        elif score >= 0.4:
                            rating = "medium"
                        else:
                            rating = "low"
                    data["utility_assessment"] = {
                        "rating": rating,
                        "rationale": str(rationale) if rationale else "",
                    }

            # 6. 专利列表字段: similar_patents（字符串列表）→ prior_art_references
            if not data.get("prior_art_references"):
                pat_ids = data.get("similar_patents") or data.get("prior_art_list")
                if isinstance(pat_ids, list) and pat_ids:
                    refs = []
                    for pid in pat_ids:
                        if isinstance(pid, str) and pid.strip():
                            refs.append({
                                "title": "",
                                "reference_id": pid.strip(),
                                "source": "",
                                "relevance": "",
                                "abstract": "",
                                "differences": "",
                                "url": "",
                                "applicant": "",
                                "publication_date": "",
                            })
                    if refs:
                        data["prior_art_references"] = refs

            # 6b. 真实检索工具常见字段 → prior_art_references
            # 这里仅做结构归一，不生成或补造检索结论。
            if not data.get("prior_art_references"):
                candidate_items: List[Any] = []
                for key in (
                    "key_references",
                    "references",
                    "search_results",
                    "patent_results",
                    "retrieved_patents",
                    "citations",
                ):
                    value = data.get(key)
                    if isinstance(value, list):
                        candidate_items.extend(value)
                for nested_key in ("retrieval_results", "results"):
                    nested = data.get(nested_key)
                    if isinstance(nested, dict):
                        for key in ("references", "results", "patents"):
                            value = nested.get(key)
                            if isinstance(value, list):
                                candidate_items.extend(value)
                    elif isinstance(nested, list):
                        candidate_items.extend(nested)

                refs = []
                seen_ref_ids: set[str] = set()
                for item in candidate_items:
                    if isinstance(item, str):
                        patent_id = item.strip()
                        if not patent_id:
                            continue
                        source = ""
                        ref = {
                            "title": patent_id,
                            "reference_id": patent_id,
                            "source": source,
                            "relevance": "",
                            "abstract": "",
                            "differences": "",
                            "url": self._build_patent_url(patent_id, source) if source else "",
                            "applicant": "",
                            "publication_date": "",
                        }
                    elif isinstance(item, dict):
                        patent_id = str(
                            item.get("reference_id")
                            or item.get("patent_id")
                            or item.get("patent_number")
                            or item.get("publication_number")
                            or item.get("document_id")
                            or ""
                        ).strip()
                        title = str(item.get("title") or item.get("name") or patent_id).strip()
                        if not patent_id and not title:
                            continue
                        source = str(item.get("source") or item.get("database") or "").strip()
                        score = item.get("similarity_score", item.get("score", 0))
                        risk = str(item.get("risk_level") or item.get("relevance") or "").strip()
                        if not risk:
                            if isinstance(score, (int, float)) and score >= 0.7:
                                risk = "high"
                            elif isinstance(score, (int, float)) and score >= 0.4:
                                risk = "medium"
                            else:
                                risk = ""
                        differences = (
                            item.get("key_differences")
                            or item.get("differences")
                            or item.get("distinguishing_features")
                            or ""
                        )
                        if isinstance(differences, list):
                            differences = "；".join(str(part) for part in differences if str(part).strip())
                        applicant = (
                            item.get("applicant")
                            or item.get("assignee")
                            or item.get("applicants")
                            or ""
                        )
                        if isinstance(applicant, list):
                            applicant = "、".join(str(part) for part in applicant if str(part).strip())
                        ref = {
                            "title": title,
                            "reference_id": patent_id,
                            "source": source,
                            "relevance": risk,
                            "abstract": item.get("abstract") or item.get("summary") or item.get("snippet") or "",
                            "differences": differences,
                            "url": item.get("url") or self._build_patent_url(patent_id, source),
                            "applicant": applicant,
                            "publication_date": item.get("publication_date") or item.get("publicationDate") or "",
                            **({"similarity_score": score} if isinstance(score, (int, float)) else {}),
                            "matching_features": item.get("matching_features") or item.get("key_features") or [],
                        }
                    else:
                        continue
                    dedupe_key = str(ref.get("reference_id") or ref.get("title") or "")
                    if dedupe_key in seen_ref_ids:
                        continue
                    seen_ref_ids.add(dedupe_key)
                    refs.append(ref)
                if refs:
                    data["prior_art_references"] = refs
                    data["similar_patents"] = refs

            # 7. 数据源字段: databases（顶层）→ retrieval_databases
            if "retrieval_databases" not in data:
                dbs = data.get("databases")
                if isinstance(dbs, list) and dbs:
                    data["retrieval_databases"] = dbs

            if "confirmed_sources" not in data:
                confirmed_sources: List[Dict[str, Any]] = []
                seen_sources: set[str] = set()

                def add_source(item: Any, default_type: str = "") -> None:
                    if isinstance(item, dict):
                        title = str(item.get("title") or item.get("name") or item.get("reference_id") or item.get("url") or "").strip()
                        url = str(item.get("url") or item.get("source_url") or "").strip()
                        source = str(item.get("source") or item.get("source_type") or item.get("database") or default_type).strip()
                        excerpt = str(
                            item.get("key_excerpt")
                            or item.get("abstract")
                            or item.get("summary")
                            or item.get("snippet")
                            or item.get("rationale")
                            or ""
                        ).strip()
                        why = str(item.get("why_it_matters") or item.get("differences") or item.get("relevance") or "").strip()
                    else:
                        title = str(item or "").strip()
                        url = ""
                        source = default_type
                        excerpt = ""
                        why = ""
                    if not (title or url):
                        return
                    key = f"{source}|{title}|{url}"
                    if key in seen_sources:
                        return
                    seen_sources.add(key)
                    confirmed_sources.append({
                        "title": title,
                        "url": url,
                        "source": source,
                        "key_excerpt": excerpt,
                        "why_it_matters": why,
                    })

                for field_name, default_type in (
                    ("prior_art_references", "patent"),
                    ("similar_patents", "patent"),
                    ("web_evidence", "web"),
                    ("non_patent_prior_art", "non_patent"),
                    ("evidence_sources", "evidence"),
                ):
                    for item in self._as_nonempty_list(data.get(field_name)):
                        add_source(item, default_type)

                for assessment_key in ("novelty_assessment", "inventive_step_assessment"):
                    assessment = data.get(assessment_key)
                    if not isinstance(assessment, dict):
                        continue
                    for item in self._as_nonempty_list(assessment.get("related_prior_art")):
                        add_source(item, "non_patent")

                if confirmed_sources:
                    data["confirmed_sources"] = confirmed_sources
            data.setdefault("evidence_gaps", [])

        elif context_field == "review_report":
            summary = data.get("review_summary")
            if isinstance(summary, dict):
                if "recommendation" not in data and summary.get("recommendation"):
                    data["recommendation"] = summary.get("recommendation")
                if "overall_score" not in data and summary.get("overall_score") is not None:
                    data["overall_score"] = summary.get("overall_score")
            # score → overall_score (如果 Agent 用了 score 字段)
            if "score" in data and "overall_score" not in data:
                data["overall_score"] = data["score"]
            target_agent_phase_map = {
                "patent_writer": "patent_writing",
                "writer": "patent_writing",
                "requirement_analyst": "requirement_analysis",
                "brainstorm_partner": "requirement_analysis",
                "retrieval_analyst": "retrieval_analysis",
                "quality_reviewer": "system_failure",
                "ceo": "system_failure",
            }
            for section_key in (
                "formal_compliance_review",
                "claims_review",
                "description_review",
                "consistency_review",
                "drawing_review",
                "drawings_review",
                "figure_review",
            ):
                section = data.get(section_key)
                if not isinstance(section, dict):
                    continue
                issues = section.get("issues")
                if not isinstance(issues, list):
                    continue
                for issue in issues:
                    if not isinstance(issue, dict) or issue.get("responsible_phase"):
                        continue
                    target_agent = str(issue.get("target_agent") or "").strip().lower()
                    responsible_phase = target_agent_phase_map.get(target_agent)
                    if responsible_phase:
                        issue["responsible_phase"] = responsible_phase
            for risk in data.get("examination_risks", []) or []:
                if not isinstance(risk, dict) or risk.get("responsible_phase"):
                    continue
                target_agent = str(risk.get("target_agent") or "").strip().lower()
                responsible_phase = target_agent_phase_map.get(target_agent)
                if not responsible_phase:
                    risk_text = " ".join(
                        str(risk.get(key) or "")
                        for key in (
                            "risk_type",
                            "description",
                            "mitigation_suggestion",
                            "mitigation",
                            "suggestion",
                        )
                    )
                    if any(token in risk_text for token in ("检索", "证据", "现有技术", "背景技术", "公开文献")):
                        responsible_phase = "retrieval_analysis"
                    elif any(token in risk_text for token in ("用户", "补充交底", "业务约束")):
                        responsible_phase = "user_input"
                    else:
                        responsible_phase = "patent_writing"
                if responsible_phase:
                    risk["responsible_phase"] = responsible_phase
            # issues → 按类型分组到 formal_compliance / claims_review / description_review
            if "issues" in data and isinstance(data["issues"], list):
                if "formal_compliance" not in data:
                    formal = [i for i in data["issues"] if isinstance(i, dict) and i.get("type", "").startswith("form")]
                    claims = [i for i in data["issues"] if isinstance(i, dict) and "claim" in i.get("type", "").lower()]
                    desc = [i for i in data["issues"] if isinstance(i, dict) and i not in formal and i not in claims]
                    if formal:
                        data["formal_compliance"] = {"issues": formal}
                    if claims:
                        data["claims_review"] = {"issues": claims}
                    if desc:
                        data["description_review"] = {"issues": desc}

        return data

    def _normalize_patent_draft_tool_results(
        self,
        tool_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build patent draft data from real Hermes tool results only."""
        claims_data: Dict[str, Any] = {}
        description_data: Dict[str, Any] = {}
        abstract_text = ""
        docx_path = ""
        drawings_data: List[Dict[str, Any]] = []

        for result in tool_results:
            if not isinstance(result, dict):
                continue
            tool_name = str(result.get("tool") or result.get("name") or "")
            payload = self._parse_tool_result_payload(
                result.get("result")
                or result.get("content")
                or result.get("output")
                or result
            )
            if not payload:
                continue
            if not tool_name:
                tool_name = str(payload.get("tool") or "")
            tool_data = payload.get("data", {})
            if not isinstance(tool_data, dict):
                tool_data = {}
            if payload.get("success") is False:
                continue

            if tool_name == "claim_drafter":
                candidate_claims = self._normalize_claims_payload(
                    tool_data,
                    raw_response=payload.get("raw_response"),
                )
                if candidate_claims.get("independent_claim"):
                    claims_data = candidate_claims
            elif tool_name == "description_writer":
                section_type = str(tool_data.get("section_type") or "")
                content = str(tool_data.get("content") or "").strip()
                if not content:
                    continue
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
            elif tool_name == "patent_drawing_generator":
                drawings = tool_data.get("drawings", [])
                if isinstance(drawings, list):
                    drawings_data.extend(item for item in drawings if isinstance(item, dict))
            elif tool_name == "patent_docx_generator":
                docx_path = str(tool_data.get("file_path") or docx_path)
                abstract_text = str(tool_data.get("abstract") or abstract_text)

        if not (claims_data or description_data or abstract_text or drawings_data or docx_path):
            return {}

        return {
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
            "docx_path": docx_path,
        }

    def _build_review_report_from_agent_envelope(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recover a structured quality review from the Agent final response only.

        Tool results are retained as trace data for the UI, but the workflow must not
        convert tool signals into a review conclusion. Subjective quality judgment
        belongs to the quality reviewer Agent LLM.
        """
        raw_text = str(data.get("final_response") or data.get("message") or "")
        parsed: Dict[str, Any] = {}
        if raw_text.strip():
            parsed_candidate = self._try_parse_json(raw_text)
            if parsed_candidate:
                parsed = parsed_candidate
            else:
                parsed = self._build_agent_output_error(
                    context_field="review_report",
                    output_text=raw_text,
                    reason="审查 Agent 最终回复无法解析为当前要求的结构化审查意见",
                )

        if not parsed:
            parsed = self._build_agent_output_error(
                context_field="review_report",
                output_text=raw_text,
                reason="审查 Agent 未返回当前要求的结构化审查意见",
            )

        parsed.setdefault("formal_compliance_review", {"issues": []})
        parsed.setdefault("claims_review", {"issues": []})
        parsed.setdefault("description_review", {"issues": []})
        parsed.setdefault("consistency_review", {"issues": []})
        parsed.setdefault("examination_risks", [])
        parsed.setdefault("detailed_revision_suggestions", [])

        summary = parsed.get("review_summary")
        if isinstance(summary, dict):
            if "recommendation" not in parsed and summary.get("recommendation"):
                parsed["recommendation"] = summary.get("recommendation")
            if "overall_score" not in parsed and summary.get("overall_score") is not None:
                parsed["overall_score"] = summary.get("overall_score")

        tool_results = data.get("tool_results", [])
        if isinstance(tool_results, list) and tool_results:
            parsed["_agent_tool_results"] = tool_results

        parsed["_raw_final_response"] = raw_text[:2000] if raw_text else ""
        parsed["_agent_envelope_normalized"] = True
        return parsed

    def _parse_tool_result_payload(self, result: object) -> Dict[str, Any]:
        """解析 Hermes tool_complete result 字段为 dict。"""
        if isinstance(result, dict):
            return result
        if not isinstance(result, str):
            return {}
        content_text = result
        if "[TOOL_OUTPUT_SAVED_TO]:" in content_text:
            content_text = content_text.split("[TOOL_OUTPUT_SAVED_TO]:", 1)[0].strip()
        try:
            parsed = json.loads(content_text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _build_agent_output_error(
        self,
        context_field: str,
        output_text: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Return explicit Agent failure metadata without synthesizing stage content."""
        error_msg = str(reason or "Agent 输出不符合当前结构化要求")[:500]
        raw_output = str(output_text or "")
        self._logger.warning(
            "Agent output rejected for %s: %s",
            context_field,
            error_msg[:200],
        )
        return {
            "_agent_failed": True,
            "_incomplete_output": True,
            "_context_field": context_field,
            "_agent_error": error_msg,
            "_raw_output": raw_output[:3000],
        }

    def _build_patent_url(self, patent_id: str, source: str) -> str:
        """根据专利号和来源构造可点击跳转的 URL"""
        if not patent_id:
            return ""

        source_lower = source.lower() if source else ""
        pid = patent_id.strip()

        if source_lower in ("uspto", "美国专利商标局"):
            clean_id = pid.replace("/", "").replace(" ", "")
            return f"https://patents.google.com/patent/{clean_id}"
        elif source_lower in ("google_patents", "google patents"):
            clean_id = pid.replace(" ", "")
            return f"https://patents.google.com/patent/{clean_id}"
        elif source_lower in ("arxiv", "arxiv 学术论文"):
            return f"https://arxiv.org/abs/{pid}"
        return ""

    def _try_parse_json(self, text: Any) -> Dict[str, Any]:
        """尝试从文本中解析 JSON，支持处理截断的 JSON 和混合格式"""
        import re

        if isinstance(text, dict):
            return text
        if isinstance(text, list):
            return {"results": text}
        if not isinstance(text, str):
            return {"raw_output": "" if text is None else str(text)}
        if not text:
            return {"raw_output": ""}

        # 尝试直接解析
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试从 markdown code block 中提取 — 支持多个代码块合并
        triple = chr(96) * 3  # ```
        # 修改正则以支持未闭合的代码块（结束标签可选）
        pattern = re.escape(triple) + r"(?:json)?\s*\n?(.*?)(?:\s*" + re.escape(triple) + r"|$)"
        matches = re.findall(pattern, text, re.DOTALL)

        if matches:
            merged = {}
            all_failed = True
            for json_str in matches:
                json_str = json_str.strip()
                if not json_str:
                    continue
                # 尝试直接解析
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                        all_failed = False
                except json.JSONDecodeError:
                    pass
                # 尝试修复截断的 JSON（补充缺失的闭合括号）
                if all_failed or not merged:
                    repaired = self._repair_truncated_json(json_str)
                    if repaired:
                        try:
                            parsed = json.loads(repaired)
                            if isinstance(parsed, dict):
                                merged.update(parsed)
                                all_failed = False
                        except json.JSONDecodeError:
                            pass
            if not all_failed and merged:
                return merged

        # 尝试从 <tool_response> 标签中提取 JSON（Agent 可能输出这种格式）
        tool_response_pattern = r'<tool_response>\s*([\s\S]*?)\s*</tool_response>'
        tool_matches = re.findall(tool_response_pattern, text)
        if tool_matches:
            merged = {}
            for json_str in tool_matches:
                json_str = json_str.strip()
                if not json_str:
                    continue
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                    elif isinstance(parsed, list) and parsed:
                        # 如果是列表，尝试合并第一层
                        if isinstance(parsed[0], dict):
                            merged["results"] = parsed
                except json.JSONDecodeError:
                    # 尝试修复
                    repaired = self._repair_truncated_json(json_str)
                    if repaired:
                        try:
                            parsed = json.loads(repaired)
                            if isinstance(parsed, dict):
                                merged.update(parsed)
                        except json.JSONDecodeError:
                            pass
            if merged:
                return merged

        # 尝试找文本中第一个 { 到最后一个 } 的范围
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                # 尝试修复截断的 JSON
                repaired = self._repair_truncated_json(text[first_brace:last_brace + 1])
                if repaired:
                    try:
                        return json.loads(repaired)
                    except json.JSONDecodeError:
                        pass

        # 返回原始文本
        return {"raw_output": text}

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """尝试修复被截断的 JSON（补充缺失的闭合括号和引号）"""
        if not isinstance(json_str, str) or not json_str:
            return None

        # 统计未闭合的括号
        open_braces = json_str.count("{") - json_str.count("}")
        open_brackets = json_str.count("[") - json_str.count("]")

        if open_braces <= 0 and open_brackets <= 0:
            return None  # 不需要修复

        # 截断到最后一个完整的 key-value 对（最后一个逗号或冒号后的值）
        # 去掉最后一个不完整的值
        repaired = json_str.rstrip()

        # 去掉尾部不完整的内容（截断可能停在字符串中间）
        # 找到最后一个完整的行
        lines = repaired.split("\n")
        while lines:
            last_line = lines[-1].strip()
            # 如果最后一行看起来不完整（没有闭合引号、逗号等），去掉它
            if last_line and not last_line.endswith((",", "}", "]", '"', "true", "false", "null")) and not last_line[-1].isdigit():
                lines.pop()
            else:
                break

        repaired = "\n".join(lines)

        # 移除尾部悬挂的逗号
        repaired = repaired.rstrip().rstrip(",")

        # 补充闭合括号
        open_braces = repaired.count("{") - repaired.count("}")
        open_brackets = repaired.count("[") - repaired.count("]")
        repaired += "]" * open_brackets + "}" * open_braces

        return repaired

