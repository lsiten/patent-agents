# -*- coding: utf-8 -*-
"""WorkflowExecutionMixin methods split from the workflow engine."""
from .shared import *


class WorkflowExecutionMixin:
    async def execute_full_workflow(
        self,
        context: WorkflowContext,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None | Awaitable[None]]] = None,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        agent_event_callback: Optional[Callable[[Dict[str, Any]], None | Awaitable[None]]] = None,
        checkpoint_callback: Optional[Callable[[WorkflowContext, str], None | Awaitable[None]]] = None,
        force_start_from: Optional[WorkflowState] = None,
    ) -> WorkflowContext:
        """Execute the patent workflow through the official LangGraph runtime."""
        if context.metadata.get("_langgraph_runtime_active"):
            return await self._execute_langgraph_domain_pipeline(
                context,
                phase_callback=phase_callback,
                event_callback=event_callback,
                agent_event_callback=agent_event_callback,
                checkpoint_callback=checkpoint_callback,
                force_start_from=force_start_from,
            )

        from src.core.workflow.graph import PatentWorkflowGraphRuntime

        runtime = PatentWorkflowGraphRuntime(self)
        return await runtime.run(
            context,
            phase_callback=phase_callback,
            event_callback=event_callback,
            agent_event_callback=agent_event_callback,
            checkpoint_callback=checkpoint_callback,
            force_start_from=force_start_from,
        )

    async def _execute_langgraph_domain_pipeline(
        self,
        context: WorkflowContext,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None | Awaitable[None]]] = None,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        agent_event_callback: Optional[Callable[[Dict[str, Any]], None | Awaitable[None]]] = None,
        checkpoint_callback: Optional[Callable[[WorkflowContext, str], None | Awaitable[None]]] = None,
        force_start_from: Optional[WorkflowState] = None,
    ) -> WorkflowContext:
        """
        执行完整工作流 — 顺序调用各专业 Agent

        每个阶段由对应的专业 Agent 直接执行，确保各阶段有实际输出。
        patent_writer 使用分段生成策略（权利要求+说明书+摘要）。
        """
        self._logger.info("Starting workflow", task_id=context.task_id)
        original_event_callback = event_callback

        def emit_workflow_event(
            agent_name: str,
            event_type: str,
            message: str,
            data: Optional[Dict[str, Any]] = None,
        ) -> None:
            enriched = self._agui_metadata(context, agent_name, event_type, message, data or {})
            if original_event_callback:
                original_event_callback(agent_name, event_type, message, enriched)
            if event_type in {
                "workflow.phase_round.started",
                "workflow.phase_round.completed",
                "workflow.quality_gate.completed",
                "workflow.shared_facts.updated",
                "workflow.human_input.requested",
                "workflow.run.started",
                "workflow.run.finished",
            }:
                self._persist_graph_checkpoint(
                    context,
                    event_type,
                    node=enriched.get("state_delta", {}).get("current_node"),
                    round_index=enriched.get("state_delta", {}).get("current_round"),
                    event={
                        "agent_name": agent_name,
                        "event_type": event_type,
                        "message": message,
                        "data": enriched,
                    },
                )

        event_callback = emit_workflow_event

        if event_callback:
            event_callback(
                "CEO Agent",
                "workflow.run.started",
                "工作流开始执行",
                {"phase": getattr(context.current_phase, "value", str(context.current_phase))},
            )

        async def emit_agent_work_event(event: Dict[str, Any]) -> None:
            if agent_event_callback is None:
                return
            event.setdefault("task_id", context.task_id)
            event.setdefault("timestamp", datetime.now().isoformat())
            result = agent_event_callback(event)
            if asyncio.iscoroutine(result):
                await result

        async def checkpoint(reason: str) -> None:
            context.metadata["latest_checkpoint"] = {
                "reason": reason,
                "phase": str(getattr(context.current_phase, "value", context.current_phase)),
                "iteration_count": context.iteration_count,
                "timestamp": datetime.now().isoformat(),
            }
            self._persist_graph_checkpoint(context, reason)
            if checkpoint_callback is None:
                return
            result = checkpoint_callback(context, reason)
            if asyncio.iscoroutine(result):
                await result

        try:
            service = _get_agent_factory()

            phases = [
                ("requirement_analyst", "patent.requirement_analyst.v1", "requirement_analysis", WorkflowState.REQUIREMENT_ANALYSIS, WorkflowPhase.REQUIREMENT),
                ("retrieval_analyst", "patent.retrieval_analyst.v1", "retrieval_report", WorkflowState.RETRIEVAL_ANALYSIS, WorkflowPhase.RETRIEVAL),
                ("patent_writer", "patent.writer.v1", "patent_draft", WorkflowState.PATENT_WRITING, WorkflowPhase.WRITING),
                ("quality_reviewer", "patent.quality_reviewer.v1", "review_report", WorkflowState.QUALITY_REVIEW, WorkflowPhase.REVIEW),
            ]
            if force_start_from:
                start_index = next(
                    (
                        index
                        for index, (_, _, _, phase_state, _) in enumerate(phases)
                        if phase_state == force_start_from
                    ),
                    0,
                )
                phases = phases[start_index:]
                context.current_phase = WorkflowState.ITERATION
                context.iteration_count += 1

            for agent_id, profile_id, context_field, phase_state, phase_enum in phases:
                if context.metadata.get("cancel_requested") or context.current_phase == WorkflowState.CANCELLED:
                    raise asyncio.CancelledError()
                if phase_state == WorkflowState.PATENT_WRITING:
                    ready_to_write = await self._ensure_prewriting_ready(
                        context,
                        event_callback=event_callback,
                        phase_callback=phase_callback,
                        checkpoint_callback=checkpoint_callback,
                    )
                    if not ready_to_write:
                        await self._persist_loop_and_sediment_skills(
                            context,
                            "awaiting_user_decision",
                            event_callback,
                        )
                        await checkpoint("prewriting_gate_waiting")
                        return context
                phase_started_at = time.perf_counter()
                context.current_phase = phase_state
                await self._publish_progress_event(context, phase_state, "running")
                await checkpoint(f"{phase_state.value}_running")
                phase_node = self._node_for_context_field(context_field)
                phase_round = self._phase_round_index(context, phase_node)

                # Agent 显示名映射
                agent_display_name = SPECIALIST_AGENT_NAMES.get(agent_id, agent_id)
                agent_action = SPECIALIST_AGENT_ACTIONS.get(agent_id, agent_id)

                # 构建任务 prompt
                task_desc = self._build_phase_prompt(context, phase_state)
                await emit_agent_work_event({
                    "event_type": "agent.work.started",
                    "agent_id": agent_id,
                    "agent_name": agent_display_name,
                    "profile_id": profile_id,
                    "action": agent_action,
                    "status": "running",
                    "data": {"task": agent_action, "phase": phase_state.value},
                })
                if event_callback:
                    event_callback(
                        agent_display_name,
                        "workflow.phase_round.started",
                        f"{agent_display_name} 第{phase_round}轮开始",
                        {
                            "phase": phase_state.value,
                            "phase_node": phase_node,
                            "round": phase_round,
                            "context_field": context_field,
                            "input_contract": self._phase_contract_summary(context_field),
                        },
                    )
                self._logger.info(f"Executing phase: {agent_id}")

                # ═══ 失败自动重试（最多重试 max_retries 次）═══
                max_retries = 2
                last_error = None
                phase_success = False
                context_data: Dict[str, Any] = {}
                agent_text = ""

                for attempt in range(1 + max_retries):
                    try:
                        if attempt > 0:
                            self._logger.info(
                                f"Retrying phase {agent_id} (attempt {attempt + 1}/{1 + max_retries})"
                            )
                            if event_callback:
                                event_callback("CEO Agent", "agent.thinking",
                                    f"⚠️ {agent_display_name} 执行失败，正在重试（第{attempt + 1}次）...",
                                    {"agent_name": "CEO Agent", "thought": f"重试 {agent_display_name}", "step": attempt})
                            # 短暂延迟后重试
                            await asyncio.sleep(2 * attempt)

                        # 发射 CEO 调度事件
                        if event_callback:
                            event_callback("CEO Agent", "agent.dispatch",
                                f"🎯 调度 → {agent_display_name}: {task_desc[:100]}",
                                {"from_agent": "CEO Agent", "to_agent": agent_display_name, "task_description": task_desc[:300]})
                        else:
                            await publish_event(AgentDispatchEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                from_agent="CEO Agent",
                                to_agent=agent_display_name,
                                task_description=task_desc[:300],
                            ))

                        # patent_writer must use the sectioned writer path even when Hermes
                        # streaming is available; otherwise one long turn hides writing progress
                        # and delays persisted stage output until the whole draft finishes.
                        if agent_id == "patent_writer":
                            # 发射分段生成进度事件
                            if event_callback:
                                event_callback(agent_display_name, "agent.thinking",
                                    "💭 开始分段生成专利文件（权利要求 → 说明书 → 摘要）",
                                    {"agent_name": agent_display_name, "thought": "分段生成专利文件", "step": 1})
                            context_data = await asyncio.wait_for(
                                self._generate_patent_in_sections(
                                    service,
                                    profile_id,
                                    task_desc,
                                    context,
                                    event_callback=event_callback,
                                ),
                                timeout=_configured_timeout_seconds(
                                    "writer_initial_timeout_seconds",
                                    WRITER_INITIAL_TIMEOUT_SECONDS,
                                ),
                            )
                            if isinstance(context_data, dict):
                                context_data = await self._ensure_required_patent_drawings(
                                    context,
                                    context_data,
                                    event_callback=event_callback,
                                )
                                context_data = self._apply_patent_manual_normalization(
                                    context_data,
                                    context_title=context.title,
                                )
                                context_data = await self._refresh_working_draft_docx(
                                    context,
                                    context_data,
                                    checkpoint="分段撰写",
                                    event_callback=event_callback,
                                )
                                context_data = self._clear_stale_writer_failure_if_reviewable(
                                    context_data
                                )
                                context_data["_writer_postprocessed"] = True
                            agent_text = json.dumps(context_data, ensure_ascii=False)[:500] if isinstance(context_data, dict) else str(context_data)[:500]
                        elif agent_id == "quality_reviewer":
                            agent_text, context_data = await self._run_quality_review_with_timeout(
                                service,
                                profile_id,
                                task_desc,
                                context,
                                event_callback=event_callback,
                            )
                            agent_tool_results = []
                        else:
                            # 流式调用 Agent（发射 thinking/tool_call 事件）
                            agent_result = await self._run_agent_stream(
                                service, profile_id, task_desc,
                                context, agent_name=agent_display_name,
                                event_callback=event_callback,
                            )
                            agent_text = agent_result.get("text", "")
                            agent_tool_results = agent_result.get("tool_results", [])
                            context_data = self._build_context_data_from_agent_response(
                                agent_id,
                                agent_text,
                                agent_tool_results,
                                agent_result.get("structured_result"),
                            )


                        context_data = self._normalize_phase_output(context_field, context_data)
                        if context_field == "patent_draft":
                            context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        contract_issues = self._validate_phase_contract(
                            context_field,
                            context_data,
                        )
                        if contract_issues:
                            last_error = RuntimeError("；".join(contract_issues[:5]))
                            if attempt >= max_retries:
                                context_data = self._build_phase_contract_error(
                                    context_field,
                                    context_data,
                                    contract_issues,
                                )
                                break
                            raise last_error
                        if isinstance(context_data, dict) and context_data.get("_agent_failed") is True:
                            agent_error = str(
                                context_data.get("_agent_error") or "Agent execution failed"
                            )[:500]
                            last_error = RuntimeError(agent_error)
                            if attempt >= max_retries:
                                break
                            raise last_error

                        phase_success = True
                        last_error = None
                        break  # 成功，退出重试循环

                    except (LLMError, Exception) as e:
                        last_error = e
                        self._logger.warning(
                            f"Phase {agent_id} attempt {attempt + 1} failed: {e}"
                        )
                        if attempt >= max_retries:
                            # 所有重试都失败
                            raise

                # 发射 Agent 输出完成事件
                if event_callback:
                    event_callback(agent_display_name, "agent.message.start",
                        f"{agent_display_name} 输出开始",
                        {"agent_name": agent_display_name, "phase": phase_state.value})
                    event_callback(agent_display_name, "agent.content",
                        f"📄 输出",
                        {"agent_name": agent_display_name, "content": agent_text if agent_text else "", "phase": phase_state.value})
                    event_callback(agent_display_name, "agent.message.end",
                        f"{agent_display_name} 输出结束",
                        {"agent_name": agent_display_name, "phase": phase_state.value})
                else:
                    await publish_event(AgentContentEvent(
                        task_id=context.task_id,
                        user_id=context.user_id,
                        agent_name=agent_display_name,
                        content=agent_text if agent_text else "",
                        phase=phase_state.value,
                    ))

                # 存储结果（适配前端期望的数据格式）
                setattr(context, context_field, context_data)
                previous_shared_facts_version = int(context.metadata.get("shared_facts_version") or 0)
                self._update_shared_context_from_phase(context, context_field, context_data)
                if event_callback and int(context.metadata.get("shared_facts_version") or 0) != previous_shared_facts_version:
                    event_callback(
                        agent_display_name,
                        "workflow.shared_facts.updated",
                        f"{agent_display_name} 更新了公共事实",
                        {
                            "phase": phase_state.value,
                            "phase_node": phase_node,
                            "round": phase_round,
                            "shared_facts_version": context.metadata.get("shared_facts_version"),
                            "shared_facts_delta": self._summarize_for_checkpoint(
                                context_data.get("shared_facts_delta") if isinstance(context_data, dict) else {},
                                limit=3000,
                            ),
                        },
                    )
                if (
                    agent_id == "patent_writer"
                    and isinstance(context_data, dict)
                    and context_data.get("_writer_postprocessed") is not True
                ):
                    context_data = await self._ensure_required_patent_drawings(
                        context,
                        context_data,
                        event_callback=event_callback,
                    )
                    context_data = self._apply_patent_manual_normalization(
                        context_data,
                        context_title=context.title,
                    )
                    context_data = await self._refresh_working_draft_docx(
                        context,
                        context_data,
                        checkpoint="附图补齐",
                        event_callback=event_callback,
                    )
                    context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                    setattr(context, context_field, context_data)
                    previous_shared_facts_version = int(context.metadata.get("shared_facts_version") or 0)
                    self._update_shared_context_from_phase(context, context_field, context_data)
                    if event_callback and int(context.metadata.get("shared_facts_version") or 0) != previous_shared_facts_version:
                        event_callback(
                            agent_display_name,
                            "workflow.shared_facts.updated",
                            f"{agent_display_name} 更新了公共事实",
                            {
                                "phase": phase_state.value,
                                "phase_node": phase_node,
                                "round": phase_round,
                                "shared_facts_version": context.metadata.get("shared_facts_version"),
                                "shared_facts_delta": self._summarize_for_checkpoint(
                                    context_data.get("shared_facts_delta") if isinstance(context_data, dict) else {},
                                    limit=3000,
                                ),
                            },
                        )

                agent_failed = (
                    isinstance(context_data, dict)
                    and context_data.get("_agent_failed") is True
                )
                agent_error = ""
                if agent_failed:
                    agent_error = str(
                        context_data.get("_agent_error") or "Agent execution failed"
                    )[:500]

                phase_duration = time.perf_counter() - phase_started_at
                if isinstance(context_data, dict):
                    context_data.setdefault("_phase_duration_seconds", phase_duration)

                # 持久化阶段结果到对应子目录
                saved_path = None
                try:
                    saved_path = _persist_phase_result(
                        context.task_id, context_field,
                        context_data if isinstance(context_data, dict) else {"output": str(context_data)},
                    )
                    self._logger.info(f"Phase result persisted: {saved_path}")
                except Exception as e:
                    self._logger.warning(f"Failed to persist phase result: {e}")

                if agent_failed:
                    round_record = self._record_phase_round(
                        context,
                        node=phase_node,
                        context_field=context_field,
                        status="failed",
                        output=context_data,
                        duration_seconds=phase_duration,
                        issues=[agent_error] if agent_error else [],
                        artifact_path=saved_path,
                    )
                    if event_callback:
                        event_callback(
                            agent_display_name,
                            "workflow.phase_round.completed",
                            f"{agent_display_name} 第{phase_round}轮失败",
                            {
                                "phase": phase_state.value,
                                "phase_node": phase_node,
                                "round": phase_round,
                                "round_record": round_record,
                                "issues": [agent_error] if agent_error else [],
                            },
                        )
                    context.add_phase_result(PhaseResult(
                        phase=phase_enum,
                        success=False,
                        duration_seconds=phase_duration,
                        output=context_data,
                        issues=[agent_error] if agent_error else [],
                    ))
                    await self._publish_progress_event(context, phase_state, "failed")
                    context.current_phase = WorkflowState.FAILED
                    await self._publish_progress_event(context, WorkflowState.FAILED, "failed")
                    await checkpoint(f"{phase_state.value}_failed")
                    await emit_agent_work_event({
                        "event_type": "agent.work.failed",
                        "agent_id": agent_id,
                        "agent_name": agent_display_name,
                        "profile_id": profile_id,
                        "action": agent_action,
                        "status": "failed",
                        "error": agent_error,
                        "data": {"task": agent_action, "phase": phase_state.value},
                    })
                    self._logger.error(
                        f"Workflow phase failed: {agent_id}: {agent_error}",
                        task_id=context.task_id,
                    )
                    await self._persist_loop_and_sediment_skills(
                        context,
                        "failed",
                        event_callback,
                    )
                    return context

                self._invalidate_downstream_outputs(
                    context,
                    phase_state,
                    reason="upstream_phase_completed",
                    preserve_fields=self._preserve_downstream_fields_after_phase(
                        phase_state,
                        context_data,
                    ),
                )

                # 记录阶段完成
                context.add_phase_result(PhaseResult(
                    phase=phase_enum,
                    success=True,
                    duration_seconds=phase_duration,
                    output=context_data if isinstance(context_data, dict) else {},
                ))
                round_record = self._record_phase_round(
                    context,
                    node=phase_node,
                    context_field=context_field,
                    status="completed",
                    output=context_data,
                    duration_seconds=phase_duration,
                    artifact_path=saved_path,
                )
                if event_callback:
                    event_callback(
                        agent_display_name,
                        "workflow.phase_round.completed",
                        f"{agent_display_name} 第{phase_round}轮完成",
                        {
                            "phase": phase_state.value,
                            "phase_node": phase_node,
                            "round": phase_round,
                            "round_record": round_record,
                            "output_contract": self._phase_contract_summary(context_field),
                        },
                    )
                await self._publish_progress_event(context, phase_state, "completed")
                await checkpoint(f"{phase_state.value}_completed")
                await emit_agent_work_event({
                    "event_type": "agent.work.completed",
                    "agent_id": agent_id,
                    "agent_name": agent_display_name,
                    "profile_id": profile_id,
                    "action": agent_action,
                    "status": "completed",
                    "summary": agent_text[:300] if agent_text else "",
                    "data": {"task": agent_action, "phase": phase_state.value},
                })

                if phase_callback:
                    if asyncio.iscoroutinefunction(phase_callback):
                        await phase_callback(phase_state, context.phase_history[-1])
                    else:
                        phase_callback(phase_state, context.phase_history[-1])

            # ═══ 质量门循环：审查撰写内容 → 修正 → 再审查 → 通过后生成 docx ═══
            max_iterations = context.max_iterations  # 自动修正软提示阈值
            safety_limit = int(
                context.metadata.get(
                    "quality_remediation_safety_limit",
                    QUALITY_REMEDIATION_SAFETY_LIMIT,
                )
                or QUALITY_REMEDIATION_SAFETY_LIMIT
            )
            review_passed = False

            if context.review_report:
                needs_remediation = self._needs_quality_remediation(context.review_report)
                if not needs_remediation:
                    review_passed = True
                context.latest_review_score = self._extract_normalized_review_score(context.review_report) or 0.0

            while not review_passed:
                if context.review_report:
                    # 审查未通过 — 提取问题并进入补救分流
                    context.iteration_count += 1
                    active_review_report = (
                        context.review_report if isinstance(context.review_report, dict) else {}
                    )
                    review_issues = self._extract_review_issues(active_review_report)
                    context.latest_revision_suggestions = review_issues
                    context.latest_review_score = (
                        self._extract_normalized_review_score(active_review_report) or 0.0
                    )
                    last_writer_failure = context.metadata.get("last_writer_failure")
                    force_writer_retry = (
                        isinstance(last_writer_failure, dict)
                        and last_writer_failure.get("needs_same_agent_retry") is True
                    )
                    if force_writer_retry:
                        # A transport/tool execution failure is not a new patent-quality
                        # conclusion. Retry the responsible writer Agent with the same
                        # review feedback instead of rerouting to requirement/retrieval.
                        remediation_path = "WRITE_MORE"
                        last_writer_failure["needs_same_agent_retry"] = False
                        context.metadata["last_writer_failure"] = last_writer_failure
                    else:
                        remediation_path = self._classify_remediation_path(
                            active_review_report,
                            context,
                        )
                    if event_callback:
                        event_callback(
                            "质量审查 Agent",
                            "workflow.quality_gate.completed",
                            f"质量门未通过，路由：{remediation_path}",
                            {
                                "phase": "quality_review",
                                "phase_node": "quality_review",
                                "round": context.iteration_count,
                                "passed": False,
                                "score": context.latest_review_score,
                                "issues": review_issues,
                                "route_to": remediation_path,
                                "review_report": self._summarize_for_checkpoint(
                                    active_review_report,
                                    limit=8000,
                                ),
                            },
                        )

                    self._logger.info(
                        f"Quality review requires remediation (round {context.iteration_count}, path={remediation_path})",
                        task_id=context.task_id,
                    )
                    if event_callback:
                        event_callback("CEO Agent", "agent.thinking",
                            f"⚠️ 质量审查发现问题，启动修正迭代（第{context.iteration_count}轮）",
                            {"agent_name": "CEO Agent", "thought": "质量审查未通过，需要修正"})
                        issue_summary = "\n".join(
                            f"{index}. {issue}"
                            for index, issue in enumerate(review_issues[:12], start=1)
                        ) or "审查报告要求继续优化，但未返回结构化问题明细。"
                        event_callback(
                            "CEO Agent",
                            "agent.content",
                            f"📋 第{context.iteration_count}轮审查问题\n{issue_summary}",
                            {
                                "agent_name": "CEO Agent",
                                "content": issue_summary,
                                "phase": "quality_review",
                                "iteration_count": context.iteration_count,
                                "review_score": context.latest_review_score,
                                "remediation_path": remediation_path,
                            },
                        )

                    # max_iterations 只是软提示阈值；质量未达标时默认继续自动修复。
                    if context.iteration_count >= max_iterations:
                        self._logger.warning(
                            f"Automatic remediation exceeded soft threshold ({max_iterations}); continuing",
                            task_id=context.task_id,
                        )
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.thinking",
                                f"⚠️ 已连续自动修正 {max_iterations} 轮仍未通过质量检测，将继续自动修复并复审",
                                {
                                    "agent_name": "CEO Agent",
                                    "thought": "auto_remediation_soft_threshold_reached",
                                    "iteration_count": context.iteration_count,
                                    "max_iterations": max_iterations,
                                },
                            )

                    if context.iteration_count >= safety_limit:
                        self._logger.error(
                            f"Automatic remediation reached safety limit ({safety_limit})",
                            task_id=context.task_id,
                        )
                        remediation_path = "TERMINAL_FAILURE"

                    if remediation_path == "TERMINAL_FAILURE":
                        break

                    if remediation_path == "NEEDS_USER_INPUT":
                        self._enter_quality_remediation_hold(
                            context,
                            active_review_report,
                            remediation_path,
                        )
                        context.current_phase = WorkflowState.AWAITING_USER_DECISION
                        if event_callback:
                            remediation = context.metadata.get("quality_remediation", {})
                            missing_information = remediation.get("missing_information", [])
                            detail = "；".join(str(item) for item in missing_information) if missing_information else "缺少额外信息"

                            event_callback(
                                "CEO Agent",
                                "workflow.human_input.requested",
                                f"需要用户补充：{detail}",
                                {
                                    "phase": "quality_review",
                                    "phase_node": "user_interrupt",
                                    "missing_information": missing_information,
                                    "resume_phase": remediation.get("resume_phase"),
                                    "interrupt_type": "quality_remediation",
                                },
                            )
                            event_callback(
                                "CEO Agent",
                                "agent.content",
                                f"⏸️ 质量审查指出存在必须由用户确认的信息，流程已暂停：{detail}",
                                {
                                    "agent_name": "CEO Agent",
                                    "phase": "quality_review",
                                    "content": detail,
                                    "missing_information": missing_information,
                                },
                            )
                        await self._publish_progress_event(
                            context,
                            WorkflowState.AWAITING_USER_DECISION,
                            "waiting",
                        )
                        await self._persist_loop_and_sediment_skills(
                            context,
                            "awaiting_user_decision",
                            event_callback,
                        )
                        return context

                    if remediation_path == "ANALYZE_MORE":
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.dispatch",
                                f"🎯 调度 → 需求分析 Agent（根据审查问题补充方案，第{context.iteration_count}轮）",
                                {
                                    "from_agent": "CEO Agent",
                                    "to_agent": _PHASE_DISPLAY_NAMES.get(WorkflowState.REQUIREMENT_ANALYSIS, "需求分析 Agent"),
                                    "task_description": "\n".join(review_issues[:8]),
                                    "iteration_count": context.iteration_count,
                                },
                            )
                        await self._execute_remediation_phase(
                            context,
                            WorkflowState.REQUIREMENT_ANALYSIS,
                            event_callback=event_callback,
                            phase_callback=phase_callback,
                            checkpoint_callback=checkpoint_callback,
                        )
                    elif remediation_path == "SEARCH_MORE":
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.dispatch",
                                f"🎯 调度 → 检索分析 Agent（根据审查问题补充检索，第{context.iteration_count}轮）",
                                {
                                    "from_agent": "CEO Agent",
                                    "to_agent": _PHASE_DISPLAY_NAMES.get(WorkflowState.RETRIEVAL_ANALYSIS, "检索分析 Agent"),
                                    "task_description": "\n".join(review_issues[:8]),
                                    "iteration_count": context.iteration_count,
                                },
                            )
                        await self._execute_remediation_phase(
                            context,
                            WorkflowState.RETRIEVAL_ANALYSIS,
                            event_callback=event_callback,
                            phase_callback=phase_callback,
                            checkpoint_callback=checkpoint_callback,
                        )

                    ready_to_write = await self._ensure_prewriting_ready(
                        context,
                        event_callback=event_callback,
                        phase_callback=phase_callback,
                        checkpoint_callback=checkpoint_callback,
                    )
                    if not ready_to_write:
                        await self._persist_loop_and_sediment_skills(
                            context,
                            "awaiting_user_decision",
                            event_callback,
                        )
                        await checkpoint("quality_remediation_waiting")
                        return context

                    # ── 修正撰写 ──
                    revision_started_at = time.perf_counter()
                    context.current_phase = WorkflowState.PATENT_WRITING
                    await self._publish_progress_event(context, WorkflowState.PATENT_WRITING, "running")
                    writing_node = self._node_for_context_field("patent_draft")
                    writing_round = self._phase_round_index(context, writing_node)
                    if event_callback:
                        event_callback(
                            "专利撰写 Agent",
                            "workflow.phase_round.started",
                            f"专利撰写 Agent 第{writing_round}轮修正开始",
                            {
                                "phase": WorkflowState.PATENT_WRITING.value,
                                "phase_node": writing_node,
                                "round": writing_round,
                                "context_field": "patent_draft",
                                "input_contract": self._phase_contract_summary("patent_draft"),
                                "remediation": True,
                                "quality_iteration": context.iteration_count,
                                "remediation_path": remediation_path,
                            },
                        )
                    await checkpoint(
                        f"quality_revision_writing_round_{context.iteration_count}_running"
                    )

                    review_requires_drawing_changes = self._review_requires_drawing_changes(
                        active_review_report
                    )
                    revision_prompt = self._build_revision_prompt(
                        context,
                        review_issues,
                        allow_drawing_generation=review_requires_drawing_changes,
                    )

                    if event_callback:
                        event_callback("CEO Agent", "agent.dispatch",
                            f"🎯 调度 → 专利撰写 Agent（修正迭代第{context.iteration_count}轮）",
                            {"from_agent": "CEO Agent", "to_agent": "专利撰写 Agent", "task_description": revision_prompt[:300]})

                    try:
                        context_data = await asyncio.wait_for(
                            self._generate_patent_in_sections(
                                service,
                                "patent.writer.v1",
                                revision_prompt,
                                context,
                                event_callback=event_callback,
                                allow_drawing_generation=review_requires_drawing_changes,
                            ),
                            timeout=int(
                                context.metadata.get(
                                    "writer_revision_timeout_seconds",
                                    WRITER_REVISION_TIMEOUT_SECONDS,
                                )
                                or WRITER_REVISION_TIMEOUT_SECONDS
                            ),
                        )
                        agent_text = json.dumps(context_data, ensure_ascii=False)[:500]
                        agent_tool_results = []
                    except asyncio.TimeoutError:
                        timeout_seconds = int(
                            context.metadata.get(
                                "writer_revision_timeout_seconds",
                                WRITER_REVISION_TIMEOUT_SECONDS,
                            )
                            or WRITER_REVISION_TIMEOUT_SECONDS
                        )
                        self._logger.warning(
                            f"Patent writer revision timed out after {timeout_seconds}s; marking draft failed",
                            task_id=context.task_id,
                        )
                        agent_text = ""
                        agent_tool_results = []
                        context_data = {
                            "_agent_failed": True,
                            "_incomplete_output": True,
                            "_agent_error": (
                                f"专利撰写 Agent 修正第{context.iteration_count}轮超过 "
                                f"{timeout_seconds}s 未完成，不能继续生成最终DOCX。"
                            ),
                            "claims": {},
                            "description": {},
                            "abstract": "",
                            "drawings": [],
                            "docx_path": "",
                        }
                    except Exception as exc:
                        self._logger.warning(
                            f"Patent writer revision failed; marking draft for Agent-led retry: {exc}",
                            task_id=context.task_id,
                        )
                        agent_text = ""
                        agent_tool_results = []
                        context_data = {
                            "failed": True,
                            "completed": False,
                            "error": str(exc),
                            "structured_result": {
                                "failed": True,
                                "completed": False,
                                "error": str(exc),
                            },
                        }

                    if event_callback:
                        event_callback("专利撰写 Agent", "agent.content",
                            f"📄 输出（修正第{context.iteration_count}轮）",
                            {"agent_name": "专利撰写 Agent", "content": agent_text[:500] if agent_text else "", "phase": "patent_writing"})

                    context_data = self._normalize_phase_output("patent_draft", context_data)
                    if not isinstance(context_data, dict):
                        context_data = {
                            "_agent_failed": True,
                            "_incomplete_output": True,
                            "_agent_error": "专利撰写 Agent 修正结果不是结构化对象。",
                            "claims": {},
                            "description": {},
                            "abstract": "",
                            "drawings": [],
                            "docx_path": "",
                        }
                    if isinstance(context_data, dict) and context_data.get("_agent_failed") is not True:
                        context_data = self._apply_review_suggestions_to_draft(
                            context,
                            context_data,
                            review_issues,
                            event_callback=event_callback,
                        )
                        context_data = self._merge_reusable_revision_drawings(
                            context,
                            context_data,
                            review_issues,
                        )
                        context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        context_data = await self._ensure_required_patent_drawings(
                            context,
                            context_data,
                            event_callback=event_callback,
                        )
                        context_data = self._apply_patent_manual_normalization(
                            context_data,
                            context_title=context.title,
                        )
                        context_data = await self._refresh_working_draft_docx(
                            context,
                            context_data,
                            checkpoint=f"修正第{context.iteration_count}轮",
                            event_callback=event_callback,
                        )
                        context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        context_data["_writer_postprocessed"] = True
                        contract_issues = self._validate_phase_contract("patent_draft", context_data)
                        if contract_issues:
                            context_data = self._build_phase_contract_error(
                                "patent_draft",
                                context_data,
                                contract_issues,
                            )
                    else:
                        context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        contract_issues = self._validate_phase_contract("patent_draft", context_data)
                        if contract_issues:
                            context_data = self._build_phase_contract_error(
                                "patent_draft",
                                context_data,
                                contract_issues,
                            )
                    revision_duration = time.perf_counter() - revision_started_at
                    if isinstance(context_data, dict):
                        context_data.setdefault("_phase_duration_seconds", revision_duration)
                    writer_failed = (
                        isinstance(context_data, dict)
                        and context_data.get("_agent_failed") is True
                    )
                    saved_path = None
                    if not writer_failed:
                        context.patent_draft = context_data
                        self._update_shared_context_from_phase(context, "patent_draft", context_data)
                        # 持久化修正后的撰写结果。失败/超时输出不能覆盖上一轮有效草稿。
                        try:
                            saved_path = _persist_phase_result(context.task_id, "patent_draft", context_data if isinstance(context_data, dict) else {"output": str(context_data)})
                        except Exception:
                            pass
                        context.metadata.pop("last_writer_failure", None)
                    else:
                        context.metadata["last_writer_failure"] = {
                            "iteration_count": context.iteration_count,
                            "error": str(context_data.get("_agent_error") or "专利撰写 Agent 修正失败"),
                            "duration_seconds": revision_duration,
                            "needs_same_agent_retry": True,
                        }
                    writing_round_record = self._record_phase_round(
                        context,
                        node=writing_node,
                        context_field="patent_draft",
                        status="failed" if writer_failed else "completed",
                        output=context_data if isinstance(context_data, dict) else {"output": str(context_data)},
                        duration_seconds=revision_duration,
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if writer_failed and isinstance(context_data, dict) else [],
                        artifact_path=saved_path,
                    )
                    if event_callback:
                        event_callback(
                            "专利撰写 Agent",
                            "workflow.phase_round.completed",
                            f"专利撰写 Agent 第{writing_round_record.get('round')}轮修正{'失败' if writer_failed else '完成'}",
                            {
                                "phase": WorkflowState.PATENT_WRITING.value,
                                "phase_node": writing_node,
                                "round": writing_round_record.get("round"),
                                "round_record": writing_round_record,
                                "output_contract": self._phase_contract_summary("patent_draft"),
                                "remediation": True,
                                "quality_iteration": context.iteration_count,
                            },
                        )
                    context.add_phase_result(PhaseResult(
                        phase=WorkflowPhase.WRITING,
                        success=not writer_failed,
                        duration_seconds=revision_duration,
                        output=context_data if isinstance(context_data, dict) else {},
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if writer_failed else [],
                    ))
                    await self._publish_progress_event(
                        context,
                        WorkflowState.PATENT_WRITING,
                        "failed" if writer_failed else "completed",
                    )
                    if phase_callback:
                        last_result = context.phase_history[-1]
                        if asyncio.iscoroutinefunction(phase_callback):
                            await phase_callback(WorkflowState.PATENT_WRITING, last_result)
                        else:
                            phase_callback(WorkflowState.PATENT_WRITING, last_result)
                    await checkpoint(
                        f"quality_revision_writing_round_{context.iteration_count}_"
                        f"{'failed' if writer_failed else 'completed'}"
                    )
                    if writer_failed:
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.thinking",
                                "⚠️ 专利撰写 Agent 本轮修正未完成，已保留上一轮有效草稿，继续调度撰写 Agent 基于原审查意见修复",
                                {
                                    "agent_name": "CEO Agent",
                                    "thought": "writer_revision_failed_preserve_previous_draft",
                                    "iteration_count": context.iteration_count,
                                },
                            )
                        continue

                    # ── 重新审查 ──
                    review_started_at = time.perf_counter()
                    context.current_phase = WorkflowState.QUALITY_REVIEW
                    await self._publish_progress_event(context, WorkflowState.QUALITY_REVIEW, "running")
                    review_node = self._node_for_context_field("review_report")
                    review_round = self._phase_round_index(context, review_node)
                    if event_callback:
                        event_callback(
                            "质量审查 Agent",
                            "workflow.phase_round.started",
                            f"质量审查 Agent 第{review_round}轮复审开始",
                            {
                                "phase": WorkflowState.QUALITY_REVIEW.value,
                                "phase_node": review_node,
                                "round": review_round,
                                "context_field": "review_report",
                                "input_contract": self._phase_contract_summary("review_report"),
                                "remediation": True,
                                "quality_iteration": context.iteration_count,
                            },
                        )
                    await checkpoint(
                        f"quality_review_round_{context.iteration_count + 1}_running"
                    )

                    review_prompt = self._build_phase_prompt(context, WorkflowState.QUALITY_REVIEW)

                    if event_callback:
                        event_callback("CEO Agent", "agent.dispatch",
                            f"🎯 调度 → 质量审查 Agent（第{context.iteration_count + 1}轮审查）",
                            {"from_agent": "CEO Agent", "to_agent": "质量审查 Agent", "task_description": review_prompt[:300]})

                    agent_text, context_data = await self._run_quality_review_with_timeout(
                        service,
                        "patent.quality_reviewer.v1",
                        review_prompt,
                        context,
                        event_callback=event_callback,
                        round_label=f"第{context.iteration_count + 1}轮",
                    )

                    if event_callback:
                        event_callback("质量审查 Agent", "agent.content",
                            f"📄 审查结果（第{context.iteration_count + 1}轮）",
                            {"agent_name": "质量审查 Agent", "content": agent_text[:500] if agent_text else "", "phase": "quality_review"})

                    context_data = self._normalize_phase_output("review_report", context_data)
                    contract_issues = self._validate_phase_contract("review_report", context_data)
                    if contract_issues:
                        context_data = self._build_phase_contract_error(
                            "review_report",
                            context_data,
                            contract_issues,
                        )
                    review_duration = time.perf_counter() - review_started_at
                    if isinstance(context_data, dict):
                        context_data.setdefault("_phase_duration_seconds", review_duration)
                    context.review_report = context_data
                    self._update_shared_context_from_phase(context, "review_report", context_data)
                    # 持久化审查结果
                    review_saved_path = None
                    try:
                        review_saved_path = _persist_phase_result(context.task_id, "review_report", context_data if isinstance(context_data, dict) else {"output": str(context_data)})
                    except Exception:
                        pass
                    review_failed = (
                        isinstance(context_data, dict)
                        and context_data.get("_agent_failed") is True
                    )
                    review_round_record = self._record_phase_round(
                        context,
                        node=review_node,
                        context_field="review_report",
                        status="failed" if review_failed else "completed",
                        output=context_data if isinstance(context_data, dict) else {"output": str(context_data)},
                        duration_seconds=review_duration,
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if review_failed and isinstance(context_data, dict) else [],
                        artifact_path=review_saved_path,
                    )
                    if event_callback:
                        event_callback(
                            "质量审查 Agent",
                            "workflow.phase_round.completed",
                            f"质量审查 Agent 第{review_round_record.get('round')}轮复审{'失败' if review_failed else '完成'}",
                            {
                                "phase": WorkflowState.QUALITY_REVIEW.value,
                                "phase_node": review_node,
                                "round": review_round_record.get("round"),
                                "round_record": review_round_record,
                                "output_contract": self._phase_contract_summary("review_report"),
                                "remediation": True,
                                "quality_iteration": context.iteration_count,
                            },
                        )
                    context.add_phase_result(PhaseResult(
                        phase=WorkflowPhase.REVIEW,
                        success=not review_failed,
                        duration_seconds=review_duration,
                        output=context_data if isinstance(context_data, dict) else {},
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if review_failed else [],
                    ))
                    await self._publish_progress_event(context, WorkflowState.QUALITY_REVIEW, "completed")
                    if phase_callback:
                        last_result = context.phase_history[-1]
                        if asyncio.iscoroutinefunction(phase_callback):
                            await phase_callback(WorkflowState.QUALITY_REVIEW, last_result)
                        else:
                            phase_callback(WorkflowState.QUALITY_REVIEW, last_result)
                    await checkpoint(f"quality_review_round_{context.iteration_count + 1}_completed")

                # 检查审查是否通过
                needs_remediation = self._needs_quality_remediation(context.review_report)
                context.latest_review_score = self._extract_normalized_review_score(context.review_report) or 0.0
                if not needs_remediation:
                    review_passed = True
                    context.metadata.pop("quality_remediation", None)
                    self._logger.info("Quality review passed", task_id=context.task_id)
                    if event_callback:
                        event_callback(
                            "质量审查 Agent",
                            "workflow.quality_gate.completed",
                            "质量门通过",
                            {
                                "phase": "quality_review",
                                "phase_node": "quality_review",
                                "round": context.iteration_count + 1,
                                "passed": True,
                                "score": context.latest_review_score,
                                "route_to": "complete",
                                "review_report": self._summarize_for_checkpoint(
                                    context.review_report,
                                    limit=8000,
                                ),
                            },
                        )
                        event_callback("CEO Agent", "agent.thinking",
                            "✅ 质量审查通过，准备生成最终文档",
                            {"agent_name": "CEO Agent", "thought": "审查通过"})
                else:
                    # 关键优化 (避免无限循环): 当 writer 和 reviewer 连续失败
                    # 且错误相同时 (例如 LLM API 一直不可用),继续迭代没有意义。
                    # 立即跳出,以 FAILED 状态结束,节省时间和资源。
                    if self._iteration_making_no_progress(context):
                        self._logger.error(
                            f"Iteration making no progress: writer/reviewer keep failing "
                            f"with same error. Breaking out early. "
                            f"task_id={context.task_id}, iteration_count={context.iteration_count}",
                            task_id=context.task_id,
                        )
                        if event_callback:
                            event_callback("CEO Agent", "agent.thinking",
                                "❌ 修正迭代未取得进展（同一错误重复出现），提前终止",
                                {"agent_name": "CEO Agent", "thought": "iteration_no_progress"})
                        break
                    if context.iteration_count == max_iterations:
                        self._logger.warning(
                            f"Soft remediation iteration threshold ({max_iterations}) reached; continuing until quality passes",
                            task_id=context.task_id,
                        )
                        if event_callback:
                            event_callback("CEO Agent", "agent.thinking",
                                f"⚠️ 已达建议修正轮次({max_iterations})，但质量未达标，将继续自动补充和复审",
                                {"agent_name": "CEO Agent", "thought": "继续质量修正"})

            # ═══ 质量审查通过（或达到最大迭代次数）→ 生成最终 .docx 文件 ═══
            # 关键修复 (Bug #1 用户可见层): 在生成 .docx 之前,必须先确认
            # patent_draft 真的有内容、review 没有未解决的关键问题。
            # 如果有问题,流程必须以 FAILED 结束,而不是 COMPLETED。
            if context.current_phase == WorkflowState.AWAITING_USER_DECISION:
                self._logger.info(
                    "Workflow paused for user decision before final document generation",
                    task_id=context.task_id,
                )
                await self._persist_loop_and_sediment_skills(
                    context,
                    "awaiting_user_decision",
                    event_callback,
                )
                await checkpoint("awaiting_user_decision_before_final_docx")
                return context

            if self._has_unresolved_critical_issues(context):
                self._logger.error(
                    "Workflow cannot complete: unresolved critical issues remain "
                    "(patent_draft incomplete OR review has critical issues). "
                    f"task_id={context.task_id}, iteration_count={context.iteration_count}",
                    task_id=context.task_id,
                )
                
                # 详细分析失败原因
                failure_details = self._analyze_workflow_failure(context)
                
                if event_callback:
                    # 发布主错误信息
                    msg = f"❌ 流程未能完成: {failure_details['main_reason']}"
                    event_callback("CEO Agent", "agent.thinking", msg, {
                        "agent_name": "CEO Agent",
                        "thought": "workflow_failed_unresolved_critical_issues",
                        "failure_phase": failure_details["phase"],
                        "failure_reason": failure_details["main_reason"],
                    })
                    
                    # 发布详细的失败分析
                    if failure_details["phase"]:
                        event_callback("CEO Agent", "agent.thinking", 
                            f"📍 失败阶段: {failure_details['phase_display']}", {
                                "agent_name": "CEO Agent",
                                "thought": "failure_phase",
                                "phase": failure_details["phase"],
                                "phase_display": failure_details["phase_display"],
                            })
                    
                    # 发布具体问题列表
                    for issue in failure_details["issues"]:
                        event_callback("CEO Agent", "agent.thinking", 
                            f"⚠️ {issue['message']}", {
                                "agent_name": "CEO Agent",
                                "thought": "failure_issue",
                                "issue_type": issue["type"],
                                "severity": issue["severity"],
                            })
                    
                    # 发布优化建议
                    event_callback("CEO Agent", "agent.thinking", 
                        "💡 优化建议:", {
                            "agent_name": "CEO Agent",
                            "thought": "optimization_tips_start",
                        })
                    for tip in failure_details["suggestions"]:
                        event_callback("CEO Agent", "agent.thinking", 
                            f"   • {tip}", {
                                "agent_name": "CEO Agent",
                                "thought": "optimization_tip",
                            })
                
                context.current_phase = WorkflowState.FAILED
                await self._publish_progress_event(context, WorkflowState.FAILED, "failed")
                
                # 发布详细的失败事件
                await emit_agent_work_event({
                    "event_type": "workflow.failed",
                    "task_id": context.task_id,
                    "phase": failure_details["phase"],
                    "phase_display": failure_details["phase_display"],
                    "main_reason": failure_details["main_reason"],
                    "issues": failure_details["issues"],
                    "suggestions": failure_details["suggestions"],
                    "status": "failed",
                })
                
                await self._persist_loop_and_sediment_skills(
                    context,
                    "failed",
                    event_callback,
                )
                if event_callback:
                    event_callback(
                        "CEO Agent",
                        "workflow.run.finished",
                        "工作流失败",
                        {
                            "phase": "failed",
                            "status": "failed",
                            "failure_details": failure_details,
                        },
                    )
                self._logger.warning("Workflow ended in FAILED state (unresolved critical issues)", task_id=context.task_id)
                return context

            if context.patent_draft and isinstance(context.patent_draft, dict):
                if event_callback:
                    event_callback("CEO Agent", "agent.thinking",
                        "📝 正在生成最终专利文档 (.docx)...",
                        {"agent_name": "CEO Agent", "thought": "生成最终文档"})

                try:
                    from src.agents.hermes.tools.patent_docx_generator import PatentDocxGeneratorTool

                    draft = context.patent_draft
                    draft = self._apply_patent_manual_normalization(
                        draft,
                        context_title=context.title,
                    )
                    context.patent_draft = draft
                    claims_data = draft.get("claims", {})
                    description_data = draft.get("description", {})
                    abstract_text = draft.get("abstract", "")

                    docx_tool = PatentDocxGeneratorTool()
                    docx_result = await docx_tool.execute(
                        title=draft.get("title") or draft.get("patent_title") or context.title,
                        claims=claims_data,
                        description=description_data,
                        abstract=abstract_text,
                        task_id=context.task_id,
                        tech_description=self._build_confirmed_writer_context(context, limit=12000),
                        drawings=draft.get("drawings", []),
                        output_stage="final",
                    )
                    if docx_result.get("success"):
                        docx_path = docx_result.get("file_path", "")
                        context.patent_draft["docx_path"] = docx_path
                        if docx_result.get("figures"):
                            context.patent_draft["docx_figures"] = docx_result.get("figures")
                        context.patent_draft["final_document"] = {
                            "file_path": docx_path,
                            "filename": _Path(docx_path).name if docx_path else "",
                            "download_url": f"/api/v1/workflows/{context.task_id}/export/docx",
                        }
                        context.metadata["final_document_path"] = docx_path
                        try:
                            _persist_phase_result(context.task_id, "patent_draft", context.patent_draft)
                        except Exception as persist_exc:
                            self._logger.warning(
                                f"Failed to persist final patent draft metadata: {persist_exc}",
                                task_id=context.task_id,
                            )
                        self._logger.info(f"Final DOCX generated after quality review: {docx_path}")
                        if event_callback:
                            event_callback("CEO Agent", "agent.content",
                                f"✅ 最终专利文档已生成: {docx_path}",
                                {"agent_name": "CEO Agent", "content": f"文档路径: {docx_path}", "phase": "completed"})
                    else:
                        self._logger.error(f"DOCX generation failed: {docx_result}")
                except Exception as e:
                    self._logger.error(f"Failed to generate final DOCX: {e}", exc_info=True)

            # 完成
            context.current_phase = WorkflowState.COMPLETED
            await self._publish_progress_event(context, WorkflowState.COMPLETED, "completed")
            await checkpoint("workflow_completed")
            await self._persist_loop_and_sediment_skills(
                context,
                "completed",
                event_callback,
            )
            context.brainstorming_output = {"summary": "专利申请流程已完成。需求分析→检索→撰写→审查全部通过，已生成最终文档。"}
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "workflow.run.finished",
                    "工作流完成",
                    {
                        "phase": "completed",
                        "status": "completed",
                        "final_document_path": context.metadata.get("final_document_path"),
                    },
                )
            self._logger.info("Workflow completed", task_id=context.task_id)
            return context

        except asyncio.CancelledError:
            context.current_phase = WorkflowState.CANCELLED
            raise
        except Exception as e:
            context.current_phase = WorkflowState.FAILED
            self._logger.error("Workflow failed", task_id=context.task_id, error=str(e), exc_info=True)
            await self._persist_loop_and_sediment_skills(
                context,
                "failed",
                event_callback,
            )
            raise

    async def execute_phase(
        self,
        context: WorkflowContext,
        phase: WorkflowState,
    ) -> PhaseResult:
        """执行单个阶段 — 直接调用对应专业 Agent"""
        start_time = datetime.now()
        profile_id = _PHASE_TO_PROFILE.get(phase)
        workflow_phase = _PHASE_TO_WORKFLOW_PHASE.get(phase, WorkflowPhase.BRAINSTORM)

        if not profile_id:
            return PhaseResult(
                phase=workflow_phase,
                success=False,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                issues=[f"No profile mapped for phase: {phase}"],
            )

        try:
            service = _get_agent_factory()
            prompt = self._build_phase_prompt(context, phase)

            result_text = await _run_agent_conversation(profile_id, prompt)
            if isinstance(result_text, dict):
                result_text = result_text.get("final_response", "") or result_text.get("content", "") or json.dumps(result_text, ensure_ascii=False)
            else:
                result_text = str(result_text) if result_text else ""

            duration = (datetime.now() - start_time).total_seconds()

            # 尝试解析 JSON 输出
            output = self._try_parse_json(result_text)

            return PhaseResult(
                phase=workflow_phase,
                success=True,
                duration_seconds=duration,
                output=output,
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self._logger.error(f"Phase {phase.value} failed: {e}", exc_info=True)
            return PhaseResult(
                phase=workflow_phase,
                success=False,
                duration_seconds=duration,
                issues=[str(e)],
            )

    async def add_chat_message(
        self,
        task_id: str,
        role: str,
        content: str,
    ) -> Dict[str, Any]:
        """添加聊天消息到工作流（用于头脑风暴阶段）"""
        context = self.get_workflow(task_id)
        if not context:
            raise ValueError(f"Workflow not found: {task_id}")

        context.add_message(role, content)

        # 如果是用户消息，通过 CEO 生成回复
        if role == "user" and context.current_phase in [
            WorkflowState.INITIALIZED,
            WorkflowState.BRAINSTORMING,
        ]:
            service = _get_agent_factory()

            # 构建对话历史（文件类消息用标签包裹）
            def _fmt_msg(m: dict) -> str:
                role = m["role"].upper()
                if m.get("type") == "file":
                    fname = m.get("metadata", {}).get("filename", "文件")
                    return f"{role} [上传文件: {fname}]:\n---文件内容开始---\n{m['content']}\n---文件内容结束---"
                return f"{role}: {m['content']}"

            history_text = "\n\n".join([
                _fmt_msg(m)
                for m in context.message_history[-10:]
            ])

            prompt = f"""
基于以下对话历史，继续与用户讨论专利申请方案：

{history_text}

请基于你的专业知识主动分析，对能确定的信息直接给出判断让用户确认（使用"是否"问句），
仅对确实无法从知识库获取的信息才提问让用户补充。
"""

            response = await _run_agent_conversation("patent.brainstorm_partner.v1", prompt)
            if isinstance(response, dict):
                response_text = response.get("final_response", "") or response.get("content", "") or str(response)
            else:
                response_text = str(response) if response else ""
            context.add_message("assistant", response_text)

            return {
                "role": "assistant",
                "content": response_text,
                "phase": context.current_phase.value,
            }

        return {"status": "added"}

    def cancel_workflow(self, task_id: str) -> bool:
        """取消工作流"""
        context = self._running_workflows.get(task_id)
        if context:
            context.metadata["cancel_requested"] = True
            context.current_phase = WorkflowState.CANCELLED
            self._logger.info("Workflow cancelled", task_id=task_id)
            return True
        return False

    # ============ 内部辅助方法 ============
