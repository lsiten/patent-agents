# -*- coding: utf-8 -*-
"""WorkflowPromptMixin methods split from the workflow engine."""
from .shared import *


class WorkflowPromptMixin:
    def _latest_phase_output(
        self,
        context: WorkflowContext,
        phase: WorkflowPhase,
        context_field: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return latest successful phase output from history, then the context snapshot field."""
        expected = getattr(phase, "value", phase)
        for result in reversed(context.phase_history or []):
            result_phase = getattr(result.phase, "value", result.phase)
            if result_phase != expected or not result.success:
                continue
            output = self._unwrap_phase_payload(result.output)
            if isinstance(output, dict) and output:
                return output
        if context_field:
            snapshot = self._unwrap_phase_payload(getattr(context, context_field, {}))
            if isinstance(snapshot, dict) and snapshot:
                return snapshot
        return {}

    def _build_phase_prompt(self, context: WorkflowContext, phase: WorkflowState, content_only: bool = False) -> str:
        """为单个阶段构建 prompt

        Args:
            context: 工作流上下文
            phase: 目标阶段
            content_only: 仅当 phase=PATENT_WRITING 时有效。
                          True 时省略 patent_docx_generator 工具调用步骤，
                          用于质量门检查前的内容生成（不生成 .docx）。
        """
        base = context.get_combined_input()

        # 阶段契约前缀：工具提供客观信号/外部产物，阶段结论必须由对应 Hermes Agent LLM 判断。
        TOOL_FORCE_PREFIX = {
            WorkflowState.REQUIREMENT_ANALYSIS: """【需求分析阶段输出契约】
你必须先加载并遵守本 profile 的需求分析 skills，最终结论由你作为需求分析 Agent 的 LLM 判断。
可调用 transcript_sanitizer、ipc_classifier、tech_feature_extractor、scenario_miner 获取客观信号；工具结果只能作为线索，不能替代技术领域、创新点、保护主题、专利类型和信息缺口判断。
如果工具信号不足，必须在输出中如实标注 `tool_signal_insufficient`，不得用本地规则或工具空结果代替 Agent 结论。
必须基于【已确认/共享公共信息】继续完善，不得忽略启动前确认的专利名称、保护主题、专利类型、公共事实和用户补充。
如果【已确认/共享公共信息】中已有检索分析结果或本轮反馈来自检索阶段，你必须复核检索证据是否已经解决需求分析指出的缺口，并输出 `retrieval_feedback_review`：
- `all_requirement_gaps_closed`: true/false
- `remaining_requirement_gaps`: 仍未补齐的需求/证据缺口数组
- `search_feedback_for_retrieval`: 需要检索 Agent 下一轮继续解决的问题数组
- `ready_for_writing`: true/false；只有存在会导致专利文本无法完整撰写的真实技术缺口、用户专属事实缺口或需求矛盾时才设为 false。
- `carried_retrieval_risks`: 已完成多轮真实检索但仍只能作为风险带入撰写/审查的证据限制数组。
如果仍有缺口，你必须把每个缺口归属到 requirement_analysis 或 retrieval_analysis：需求/方案细节缺口由你基于上一轮内容继续补齐；证据/现有技术/真伪核验缺口写入 `search_feedback_for_retrieval` 交给检索 Agent。
用户未提供真实商业产品参数、硬件型号、尺寸、身高档位、角度档位、传感器型号、算法唯一选型时，不得默认阻止撰写；如果这些信息不是发明主题成立的必要事实，必须基于已确认方案、真实检索证据、物理规律和本领域常识写成“可配置/可选/非限定实施例”，并把限制放入 `carried_retrieval_risks` 或 `implementation_assumptions`。
只有缺口无法通过可配置范围、可选结构、非限定示例或本领域常识合理表达，且会导致权利要求骨架无法成立时，才允许把 `ready_for_writing` 设为 false。
不得仅因为“未找到单一最接近现有技术”“某个检索源不可用/无结果”“还可补充产品页面、白皮书、标准或厂商公开资料”就阻止撰写；当检索 Agent 已记录真实检索式、数据源、命中/失败/无结果和可核验对比证据时，这些事项应进入 `carried_retrieval_risks` 并交由撰写和质量审查处理。
只有补证项会改变发明主题、权利要求骨架、必要技术特征或公开状态时，才能把 `ready_for_writing` 设为 false。
不得因为检索暂时失败就要求用户补充，除非缺口是用户专属事实（例如内部产品参数、尚未公开资料、明确业务选择）。
最终 JSON 必须剔除逐字稿时间戳、说话人、寒暄和会议口语。
---

""",
            WorkflowState.RETRIEVAL_ANALYSIS: """【检索分析阶段输出契约】
你必须先加载并遵守本 profile 的检索 skills，最终检索策略、相似性、专利性和风险结论由你作为检索分析 Agent 的 LLM 判断。
patent_search、similarity_analyzer、patentability_scorer、risk_analyzer、web_access_* 都是 Hermes 工具，只提供真实检索证据、客观信号或网页取证能力；工具不能替你下结论，也不能为了满足固定顺序而空跑。
应根据需求分析提出的缺口选择必要工具：需要专利证据时调用 patent_search；已有对比文件时再调用 similarity_analyzer / patentability_scorer；需要风险线索时调用 risk_analyzer；需要非专利公开或动态页面证据时调用 web_access_*。
必须基于【已确认/共享公共信息】、需求分析结果和需求分析提出的 `information_gaps` / `search_feedback_for_retrieval` 继续检索；你的职责是为需求分析缺口补充可核验证据和可写入专利的解决方案。
如果证据不足，必须先分析为什么无结果或证据不足，再更换检索条件继续搜索；最终输出 evidence_gaps 和下一轮检索策略，不得编造检索结果。
每轮检索必须继承上一轮可用证据，新增或替换无效检索式，并说明“本轮新增证据/本轮仍未解决证据缺口/下一轮检索建议”。
检索完成后，结果必须交回需求分析 Agent 复核缺口是否关闭；你不能直接判断进入撰写。
---

""",
            WorkflowState.PATENT_WRITING: """【专利撰写阶段输出契约】
你必须先加载并遵守本 profile 的撰写、权利要求、附图和规范 skills；正式专利正文由你作为专利撰写 Agent 的 LLM 分段生成。
claim_drafter、description_writer、terminology_normalizer、support_checker 只提供结构、约束和客观信号，不能替代正式权利要求、说明书和摘要。
撰写前必须确认【已确认/共享公共信息】、需求分析和检索分析已经足够支持撰写；若不足，输出明确缺口并标注 responsible_phase，不得硬写。
对真实项目参数缺失但不影响发明成立的内容，应写成可配置范围、可选部件或非限定实施例：例如身高/角度/场景映射表、执行机构、传感器、尺寸、阈值、算法策略均可列为“可以包括/可选为/在一实施例中”，不得因为没有用户私有参数就拒绝撰写。
如果发明涉及结构、装置、系统、流程、空间关系或说明书包含附图说明，必须由你调用 patent_drawing_generator 为每一张附图分别生成真实附图，且绘图输入必须来自当前专利内容。
注意：当前阶段只生成审查前的专利草稿和附图，不得调用 patent_docx_generator；最终 DOCX 必须在质量审查合格后由工作流统一生成。
---

""",
            WorkflowState.QUALITY_REVIEW: """【质量审查阶段输出契约】
你必须先加载并遵守本 profile 的质量审查 skills；最终评分、是否通过、是否需要补正和修复路径必须由你作为质量审查 Agent 的 LLM 判断。
可调用 compliance_checker、claim_quality_analyzer、support_verifier、oa_predictor 获取客观信号和审查线索；工具结果不能替代内容质量、创造性、充分公开、权利要求清楚性和附图一致性的专业判断。
必须同时审查文本、权利要求、说明书、附图是否缺失/重复、图号和附图文件可访问性。发现问题时输出可由 CEO 调度的缺陷清单。
注意：当前阶段是最终 DOCX 生成前的质量门，`docx_path` 为空不是缺陷；只有已提供最终 DOCX 路径时才审查 DOCX 插图位置。
所有 high/critical 问题必须包含 `responsible_phase`，取值只能是：requirement_analysis、retrieval_analysis、patent_writing、user_input、system_failure。
如果 recommendation 为 revise/reject 或存在 high/critical 问题，顶层必须输出 `root_cause`，取值只能是：content_incomplete、requirement_unclear、evidence_missing、external_info_missing、system_failure。
CEO 只会按这些字段路由，不会替你判断专业结论；因此必须把修复建议写成对应 Agent 可执行的反馈。
---

""",
        }

        # content_only 模式 — 用于质量门前的专利内容生成，不生成 .docx
        CONTENT_ONLY_TOOL_FORCE_PREFIX = {
            WorkflowState.PATENT_WRITING: """【专利撰写阶段输出契约】
你必须先加载并遵守本 profile 的撰写、权利要求、附图和规范 skills；正式专利正文由你作为专利撰写 Agent 的 LLM 分段生成。
claim_drafter、description_writer、terminology_normalizer、support_checker 只提供结构、约束和客观信号，不能替代正式权利要求、说明书和摘要。
撰写前必须确认【已确认/共享公共信息】、需求分析和检索分析已经足够支持撰写；若不足，输出明确缺口并标注 responsible_phase，不得硬写。
如果发明涉及结构、装置、系统、流程、空间关系或说明书包含附图说明，必须由你调用 patent_drawing_generator 为每一张附图分别生成真实附图，且绘图输入必须来自当前专利内容。
注意：工具不能替代你的专利撰写判断；不得调用 patent_docx_generator。
---

""",
        }

        if content_only and phase == WorkflowState.PATENT_WRITING:
            tool_prefix = CONTENT_ONLY_TOOL_FORCE_PREFIX.get(phase, "")
        else:
            tool_prefix = TOOL_FORCE_PREFIX.get(phase, "")

        target_country = context.metadata.get("target_country", "中国")

        country_hint_map = {
            WorkflowState.BRAINSTORMING: f"\n\n【目标申请国家】{target_country} — 默认按中国专利制度分析，除非用户明确要求其他国家。",
            WorkflowState.REQUIREMENT_ANALYSIS: f"\n\n【目标申请国家/法域】{target_country} — 分析时考虑该法域专利制度特点。",
            WorkflowState.RETRIEVAL_ANALYSIS: f"\n\n【目标申请国家/法域】{target_country} — 优先检索该国家/地区的专利数据库。",
            WorkflowState.PATENT_WRITING: f"\n\n【目标申请国家/法域】{target_country} — 严格遵循该法域的专利撰写规范和格式要求。",
            WorkflowState.QUALITY_REVIEW: f"\n\n【目标申请国家/法域】{target_country} — 依据该法域的专利法进行质量审查。",
        }

        if phase == WorkflowState.BRAINSTORMING:
            return f"""请基于你的专业专利知识分析以下技术方案，注意：
1. 先给出你能确定的分析和判断（技术领域归类、创新点初判等）
2. 使用"是否"确认问句让用户确认，而不是直接让用户补充细节
3. 仅对确实无法从专业知识和检索获取的信息，才列出问题请用户补充

请梳理这项技术发明的专利申请思路：\n\n{base}{country_hint_map[phase]}"""

        elif phase == WorkflowState.REQUIREMENT_ANALYSIS:
            retrieval_output = self._latest_phase_output(
                context, WorkflowPhase.RETRIEVAL, "retrieval_report"
            )
            retrieval_section = (
                "\n\n【最新检索分析结果，必须复核其是否关闭需求缺口】\n"
                + json.dumps(retrieval_output, ensure_ascii=False)[:6000]
                if retrieval_output
                else ""
            )
            return (
                f"{tool_prefix}对以下技术方案进行结构化需求分析，提取创新点和技术特征：\n\n"
                f"{base}{retrieval_section}{country_hint_map[phase]}"
            )

        elif phase == WorkflowState.RETRIEVAL_ANALYSIS:
            requirement_output = self._latest_phase_output(
                context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
            )
            req = json.dumps(requirement_output, ensure_ascii=False)[:1000]
            return f"""{tool_prefix}基于以下需求分析结果进行先有技术检索和专利性评估：

{req}

原始描述：{context.original_description[:500]}{country_hint_map[phase]}

【网页补充证据要求】
- 如果专利数据库结果不足以支持公开时间、产品功能、标准规范、实现细节或非专利现有技术判断，必须补充网页证据。
- 优先顺序：先 `web_access_match_site` 判断站点是否有已知模式或陷阱；不知道入口时用 `web_access_find_url`；已知公开 URL 时用 `web_access_read_page`；页面需要脚本、登录、滚动、点击时再用 `web_access_browser`。
- 网页证据只用于补强，不替代 patent_search / similarity_analyzer / patentability_scorer / risk_analyzer 的主链路。

【输出补充要求】
- 在最终 JSON 中补充以下字段：
  - `web_evidence`: 网页证据摘要列表；没有使用时返回空数组
  - `non_patent_prior_art`: 非专利现有技术来源列表；没有时返回空数组
  - `evidence_sources`: 本次实际使用的网页/标准/产品/内部来源列表；没有时返回空数组
  - `evidence_gaps`: 仍未补足的证据缺口；没有时返回空数组
- `web_evidence` 每项至少包含：`source_type`、`title`、`url`、`key_excerpt`、`why_it_matters`
- 若调用了任何 `web_access_*` 工具，上述字段不能为空数组，必须反映实际证据。
"""

        elif phase == WorkflowState.PATENT_WRITING:
            requirement_output = self._latest_phase_output(
                context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
            )
            retrieval_output = self._latest_phase_output(
                context, WorkflowPhase.RETRIEVAL, "retrieval_report"
            )
            req = json.dumps(requirement_output, ensure_ascii=False)[:500]
            ret = self._build_retrieval_summary_for_writer(retrieval_output, limit=8000)
            return f"{tool_prefix}基于需求分析和检索结果撰写专利申请文件：\n\n需求：{req}\n\n检索：{ret}{country_hint_map[phase]}"

        elif phase == WorkflowState.QUALITY_REVIEW:
            draft = self._build_quality_review_draft_summary(context.patent_draft)
            return f"{tool_prefix}对以下专利申请文件进行质量审查：\n\n{draft}{country_hint_map[phase]}"

        return base

    def _build_phase_continuation_prompt(
        self,
        context: WorkflowContext,
        phase: WorkflowState,
        base_prompt: str,
    ) -> str:
        """Wrap a remediation phase prompt so each round improves the last result.

        A remediation round must preserve valid parts from the previous round and
        only amend the issues that CEO/reviewer/gates identified. The Agent still
        returns a complete updated JSON so downstream rendering remains simple.
        """
        context_field = _PHASE_CONTEXT_FIELDS.get(phase)
        previous_output = getattr(context, context_field, {}) if context_field else {}
        suggestions = [
            str(item).strip()
            for item in (context.latest_revision_suggestions or [])
            if str(item).strip()
        ]
        has_previous = isinstance(previous_output, dict) and bool(previous_output)
        if not has_previous and not suggestions:
            return base_prompt

        previous_text = (
            json.dumps(previous_output, ensure_ascii=False, indent=2)[:12000]
            if has_previous
            else "无"
        )
        suggestions_text = "\n".join(
            f"{index}. {item}" for index, item in enumerate(suggestions[:20], start=1)
        ) or "无"

        return f"""{base_prompt}

---

【本轮是迭代补充/修正，不是重新开始】
你必须基于上一轮本阶段结果继续优化：
- 保留上一轮已经正确、已被后续阶段使用或已通过检查的内容；
- 只针对本轮反馈指出的问题补充、修正或替换；
- 如果需求分析更新导致检索依据变化，检索阶段应复用上一轮可用证据并补充新的检索证据，不得删除仍然有效的对比文件；
- 如果撰写阶段修正，必须保留未被反馈指出有问题的权利要求、说明书章节、摘要和附图，只修改需要修复的部分；
- 最终仍输出完整的本阶段 JSON，而不是只输出差异。

【上一轮本阶段结果】
{previous_text}

【本轮必须解决的反馈/缺口】
{suggestions_text}
"""

    def _build_quality_review_draft_summary(self, draft: Dict[str, Any]) -> str:
        if not isinstance(draft, dict):
            return str(draft)[:4000]

        drawing_file_validation = self._validate_drawing_files_for_review(draft)
        claims = draft.get("claims") or {}
        description = draft.get("description") or {}
        summary = {
            "title": draft.get("title") or draft.get("patent_title") or "",
            "claims": {
                "independent_claim": str(claims.get("independent_claim") or "")[:1500],
                # Quality review must see every claim. Truncating to the first
                # few dependent claims can hide a second independent system/device
                # claim and create false remediation loops.
                "dependent_claims": [str(claim)[:1200] for claim in claims.get("dependent_claims", [])[:30]],
            },
            "description": {
                "technical_field": str(description.get("technical_field") or "")[:800],
                "background_art": str(description.get("background_art") or "")[:3000],
                "summary_of_invention": str(description.get("summary_of_invention") or "")[:3000],
                "drawings_description": str(description.get("drawings_description") or "")[:3000],
                # Reviewer must inspect the full S1-S4 implementation and figure
                # correspondence. Old short truncation made complete sections look
                # cut off and caused false "content_incomplete" loops.
                "detailed_description": str(description.get("detailed_description") or "")[:12000],
            },
            "drawings": [
                {
                    "figure_number": str(drawing.get("figure_number") or drawing.get("figureNumber") or ""),
                    "title": str(drawing.get("title") or ""),
                    "description": str(drawing.get("description") or "")[:800],
                    "file_path": str(drawing.get("file_path") or ""),
                    "artifact_url": str(drawing.get("artifact_url") or drawing.get("artifactUrl") or ""),
                    "mime_type": str(drawing.get("mime_type") or ""),
                }
                for drawing in (draft.get("drawings") or [])
                if isinstance(drawing, dict)
            ][:8],
            "drawing_quality_requirements": [
                "如果说明书包含附图说明或具体实施方式引用图号，必须存在对应 drawings 元数据和可访问文件路径。",
                "审查附图是否与权利要求、附图说明、具体实施方式中的结构/流程一致。",
                "需要附图但未生成、图号不一致、附图无法访问或图文不匹配，均应判定为 high/critical 问题并要求撰写 Agent 补图或修正。",
                "当前质量审查发生在最终 DOCX 生成前，docx_path 为空不是缺陷；通过后工作流才生成最终 DOCX。",
                "本地附图文件可访问性以 drawing_file_validation 为准；不要因浏览器远程调试端口未连接而把已存在的本地附图判为 system_failure。",
            ],
            "drawing_file_validation": drawing_file_validation,
            "abstract": str(draft.get("abstract") or "")[:800],
            "docx_path": draft.get("docx_path") or "",
        }
        return json.dumps(summary, ensure_ascii=False)

