# -*- coding: utf-8 -*-
"""WorkflowAgentRuntimeMixin methods split from the workflow engine."""
from .shared import *


class WorkflowAgentRuntimeMixin:
    async def _run_quality_review_with_timeout(
        self,
        service,
        profile_id: str,
        review_prompt: str,
        context: WorkflowContext,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        round_label: str = "",
        timeout_seconds: int = 900,
    ) -> tuple[str, Dict[str, Any]]:
        """Run the quality reviewer with a bounded wait.

        Quality review is a required gate. If the reviewer LLM/tool chain hangs,
        return a structured non-approval result so the CEO remediation loop can
        retry or stop for human attention. Local heuristics must not approve.
        """
        label = f"（{round_label}）" if round_label else ""
        try:
            agent_result = await asyncio.wait_for(
                self._run_agent_stream(
                    service,
                    profile_id,
                    review_prompt,
                    context,
                    "质量审查 Agent",
                    event_callback=event_callback,
                ),
                timeout=timeout_seconds,
            )
            agent_text = str(agent_result.get("text") or "")
            context_data = self._build_context_data_from_agent_response(
                "quality_reviewer",
                agent_text,
                agent_result.get("tool_results", []),
                agent_result.get("structured_result"),
            )
            context_data = self._normalize_phase_output("review_report", context_data)
            context_data = self._merge_manual_compliance_into_review(context, context_data)
            context_data = self._downgrade_false_drawing_access_system_failures(
                context,
                context_data,
            )
            return agent_text[:500], context_data
        except asyncio.TimeoutError:
            reason = f"质量审查 Agent{label}超过 {timeout_seconds}s 未完成"
        except Exception as exc:
            reason = f"质量审查 Agent{label}执行异常：{str(exc)[:180]}"

        self._logger.warning(
            f"{reason}; quality review marked as not approved",
            task_id=context.task_id,
        )
        if event_callback:
            event_callback(
                "质量审查 Agent",
                "agent.thinking",
                f"⚠️ {reason}，质量审查未通过，等待 CEO 重新调度",
                {
                    "agent_name": "质量审查 Agent",
                    "thought": "quality_review_unavailable",
                    "timeout_seconds": timeout_seconds,
                },
            )

        review = self._build_agent_output_error(
            context_field="review_report",
            output_text="",
            reason=reason,
        )
        review.update({
            "failed": True,
            "completed": False,
        })
        return json.dumps(review, ensure_ascii=False)[:500], review

    async def _run_agent_stream(
        self,
        service,  # 保留参数签名兼容性，但不再使用
        profile_id: str,
        user_input: str,
        context: WorkflowContext,
        agent_name: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        流式调用 Agent 并实时发射事件到前端。
        使用 AIAgent 原生回调机制。
        返回 dict 包含:
          - text: agent 的最终文本输出
          - tool_results: 工具调用结果列表
        """
        import threading
        from src.agents.agent_config import create_ai_agent

        content_chunks: List[str] = []
        final_text = ""
        structured_result = None
        tool_results: List[Dict[str, Any]] = []
        events: List[Dict[str, Any]] = []
        events_lock = threading.Lock()
        result_holder = {"result": None, "error": None, "done": False}

        def _emit(evt_type: str, message: str, data: Dict[str, Any] = None):
            """通过callback直接发射事件"""
            if event_callback:
                event_callback(agent_name, evt_type, message, data or {})

        if hasattr(service, "run_conversation_stream"):
            async for event in service.run_conversation_stream(profile_id, user_input, user_id=context.user_id):
                event_type = event.get("type", "")
                event_data = event.get("data", {}) if isinstance(event.get("data", {}), dict) else {}

                if event_type == "tool_call_start":
                    tool_name = event_data.get("name", "")
                    params = event_data.get("parameters", {})
                    _emit("agent.tool_call_start", f"🔧 调用工具: {tool_name}", {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": params,
                    })
                elif event_type == "tool_call_end":
                    tool_name = event_data.get("name", "")
                    result = event_data.get("result", "")
                    result_str = str(result) if result else ""
                    success = event_data.get("success", True)
                    status_icon = "✅" if success else "❌"
                    _emit("agent.tool_call_result", f"{status_icon} {tool_name} 结果", {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": event_data.get("parameters", {}),
                        "result": result_str,
                        "success": success,
                    })
                    _emit("agent.tool_call_end", f"{status_icon} {tool_name} 返回", {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": event_data.get("parameters", {}),
                        "result": result_str,
                        "success": success,
                    })
                    tool_results.append({
                        "tool": tool_name,
                        "parameters": event_data.get("parameters", {}),
                        "result": result,
                        "result_preview": result_str,
                        "success": success,
                    })
                elif event_type in {"content", "done"}:
                    content = event_data.get("content")
                    if isinstance(content, str):
                        content_chunks.append(content)

            final_text = "".join(content_chunks)
            return {"text": final_text, "tool_results": tool_results}

        def on_thinking(data):
            text = str(data).strip() if data else ""
            if not text or len(text) < 5:
                return
            if text.startswith("{") or text.startswith("["):
                return
            with events_lock:
                events.append({"type": "thinking", "data": {"message": text}})

        def on_tool_start(call_id, name, args):
            params = {}
            if isinstance(args, str):
                try:
                    params = json.loads(args)
                except Exception:
                    params = {"raw": args}
            elif isinstance(args, dict):
                params = args
            with events_lock:
                events.append({"type": "tool_call_start", "data": {"name": name, "parameters": params}})

        def on_tool_complete(call_id, name, args, result):
            result_str = str(result) if result else ""
            with events_lock:
                events.append({
                    "type": "tool_call_end",
                    "data": {"name": name, "result": result, "result_preview": result_str, "success": True}
                })

        def on_stream_delta(delta):
            with events_lock:
                content_chunks.append(delta)
                events.append({"type": "content_delta", "data": {"delta": delta}})

        callbacks = {
            "thinking": on_thinking,
            "tool_start": on_tool_start,
            "tool_complete": on_tool_complete,
            "stream_delta": on_stream_delta,
        }

        def run_agent():
            try:
                agent = create_ai_agent(profile_id=profile_id, callbacks=callbacks)
                result_holder["result"] = agent.run_conversation(user_input)
            except Exception as e:
                result_holder["error"] = str(e)
            finally:
                result_holder["done"] = True

        # 在后台线程运行 Agent
        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()

        try:
            event_count = 0
            try:
                from src.core.config import settings

                configured_timeout = int(getattr(settings.workflow, "agent_timeout", 600) or 600)
            except Exception:
                configured_timeout = 600
            AGENT_TIMEOUT_SECONDS = max(60, configured_timeout)
            deadline = asyncio.get_event_loop().time() + AGENT_TIMEOUT_SECONDS
            while not result_holder["done"] or events:
                if asyncio.get_event_loop().time() > deadline:
                    self._logger.warning(
                        f"Agent {agent_name} timed out after {AGENT_TIMEOUT_SECONDS}s"
                    )
                    if not result_holder["done"]:
                        result_holder["done"] = True
                        result_holder["error"] = "timeout"
                    break
                with events_lock:
                    batch = list(events)
                    events.clear()

                for event in batch:
                    event_type = event.get("type", "")
                    event_data = event.get("data", {})
                    event_count += 1

                    if event_type == "thinking":
                        thought = event_data.get("message", "")
                        _emit("agent.thinking", f"💭 {thought}", {
                            "agent_name": agent_name,
                            "thought": thought,
                            "step": 0,
                        })
                        if not event_callback:
                            await publish_event(AgentThinkingEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                agent_name=agent_name,
                                thought=thought,
                                step=0,
                            ))

                    elif event_type == "tool_call_start":
                        tool_name = event_data.get("name", "")
                        params = event_data.get("parameters", {})
                        _emit("agent.tool_call_start", f"🔧 调用工具: {tool_name}", {
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "parameters": params,
                        })
                        if not event_callback:
                            await publish_event(AgentToolCallStartEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                agent_name=agent_name,
                                tool_name=tool_name,
                                parameters=params,
                            ))

                    elif event_type == "tool_call_end":
                        tool_name = event_data.get("name", "")
                        result = event_data.get("result", "")
                        result_str = str(result) if result else ""
                        success = event_data.get("success", True)
                        status_icon = "✅" if success else "❌"
                        _emit("agent.tool_call_result", f"{status_icon} {tool_name} 结果", {
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "parameters": event_data.get("parameters", {}),
                            "result": result_str,
                            "success": success,
                        })
                        _emit("agent.tool_call_end", f"{status_icon} {tool_name} 返回", {
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "parameters": event_data.get("parameters", {}),
                            "result": result_str,
                            "success": success,
                        })
                        tool_results.append({
                            "tool": tool_name,
                            "parameters": event_data.get("parameters", {}),
                            "result": result,
                            "result_preview": result_str,
                            "success": success,
                        })
                        if not event_callback:
                            await publish_event(AgentToolCallEndEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                agent_name=agent_name,
                                tool_name=tool_name,
                                parameters=event_data.get("parameters", {}),
                                result=result,
                                success=success,
                            ))

                if not batch and not result_holder["done"]:
                    await asyncio.sleep(0.05)

            # 处理最终结果
            if result_holder["error"]:
                self._logger.error(
                    "Agent stream error",
                    agent=agent_name,
                    error=result_holder["error"],
                )
                if result_holder["error"] == "timeout":
                    structured_result = {
                        "failed": True,
                        "completed": False,
                        "error": f"Agent {agent_name} timed out",
                    }
                    final_text = ""
                else:
                    structured_result = {
                        "failed": True,
                        "completed": False,
                        "error": result_holder["error"],
                    }
                    final_text = ""
            else:
                result = result_holder["result"]
                if isinstance(result, dict):
                    structured_result = result
                    final_text = result.get("final_response", "") or result.get("content", "") or json.dumps(result, ensure_ascii=False)
                else:
                    final_text = str(result) if result else ""

            self._logger.info(
                f"Agent stream completed: {agent_name}, events={event_count}, "
                f"content_len={len(final_text)}"
            )

        except Exception as e:
            self._logger.error(
                "Agent stream failed",
                agent=agent_name,
                error=str(e),
                exc_info=True,
            )
            structured_result = {
                "failed": True,
                "completed": False,
                "error": str(e)[:500],
            }
            final_text = ""

        # 如果有 stream delta chunks 则拼接
        if content_chunks and not final_text:
            final_text = "".join(content_chunks)

        # ═══ 补充日志：从 Agent 输出文本中提取过程性内容 ═══
        if event_callback and final_text:
            self._emit_process_logs_from_text(final_text, agent_name, event_callback)

        return {
            "text": final_text,
            "tool_results": tool_results,
            "structured_result": structured_result,
        }

    def _emit_process_logs_from_text(
        self,
        text: str,
        agent_name: str,
        event_callback: Callable[[str, str, str, Dict[str, Any]], None],
    ) -> None:
        """从 Agent 输出文本中提取过程性内容，补充发射为日志事件

        当 Agent 没有真正触发工具回调（而是用文字描述了工具调用过程）时，
        从最终输出中解析步骤、工具调用、分析结论等，让前端日志有内容展示。
        """
        import re

        lines = text.split("\n")
        step_count = 0
        current_tool = ""
        collecting_result = False
        result_lines: list = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                # 空行结束结果收集
                if collecting_result and result_lines:
                    result_text = "; ".join(result_lines)
                    event_callback(agent_name, "agent.tool_call_end",
                        f"✅ {current_tool} 返回",
                        {"agent_name": agent_name, "tool_name": current_tool,
                         "result": result_text, "success": True})
                    result_lines = []
                    collecting_result = False
                continue

            # 收集返回结果的缩进行
            if collecting_result:
                if stripped.startswith("-") or stripped.startswith("•") or line.startswith("  "):
                    clean = stripped.lstrip("-•").strip()
                    if clean:
                        result_lines.append(clean)
                    continue
                else:
                    # 非缩进行，结束收集
                    if result_lines:
                        result_text = "; ".join(result_lines)
                        event_callback(agent_name, "agent.tool_call_end",
                            f"✅ {current_tool} 返回",
                            {"agent_name": agent_name, "tool_name": current_tool,
                             "result": result_text, "success": True})
                        result_lines = []
                    collecting_result = False

            # 检测步骤标题（## 步骤N：xxx）
            step_match = re.match(r'^#{1,3}\s*(步骤|Step|阶段)\s*\d*[：:]?\s*(.+)', stripped)
            if step_match:
                step_count += 1
                step_desc = step_match.group(2).strip()
                event_callback(agent_name, "agent.thinking",
                    f"💭 {step_desc}",
                    {"agent_name": agent_name, "thought": step_desc, "step": step_count})
                continue

            # 检测工具调用（**工具调用：xxx**）— 精确匹配，避免重复
            tool_match = re.match(r'^\*{2}工具调用[：:]\s*`?(\w+)`?\*{2}', stripped)
            if tool_match:
                current_tool = tool_match.group(1)
                event_callback(agent_name, "agent.tool_call_start",
                    f"🔧 调用工具: {current_tool}",
                    {"agent_name": agent_name, "tool_name": current_tool, "parameters": {}})
                continue

            # 检测返回结果行
            result_match = re.match(r'^[-*]\s*返回结果[：:]?\s*(.*)$', stripped)
            if result_match:
                initial = result_match.group(1).strip()
                if initial:
                    result_lines.append(initial)
                collecting_result = True
                continue

            # 检测分析结论性标题
            conclusion_match = re.match(r'^#{1,3}\s*(总体评价|结论|分析结果|最终输出|综合评估)[：:]?\s*(.*)', stripped)
            if conclusion_match:
                desc = conclusion_match.group(1) + (": " + conclusion_match.group(2) if conclusion_match.group(2) else "")
                event_callback(agent_name, "agent.thinking",
                    f"💭 {desc}",
                    {"agent_name": agent_name, "thought": desc, "step": step_count + 1})

        # Flush 残留的结果
        if collecting_result and result_lines:
            result_text = "; ".join(result_lines)
            event_callback(agent_name, "agent.tool_call_end",
                f"✅ {current_tool} 返回",
                {"agent_name": agent_name, "tool_name": current_tool,
                 "result": result_text, "success": True})

    async def _publish_progress_event(
        self,
        context: WorkflowContext,
        phase: WorkflowState,
        status: str,
        result: Optional[PhaseResult] = None,
    ) -> None:
        """发布进度事件"""
        try:
            from src.core.events import EventType, TaskProgressUpdatedEvent

            event = TaskProgressUpdatedEvent(
                event_type=EventType.WORKFLOW_PROGRESS_UPDATED,
                task_id=context.task_id,
                user_id=context.user_id,
                state=phase.value,
                progress=self._calculate_progress(context, phase, status),
                message=f"Phase {phase.value} {status}",
            )

            await publish_event(event)

        except Exception as e:
            self._logger.warning("Failed to publish progress event", error=str(e))

    def _calculate_progress(self, context: WorkflowContext, current_phase: WorkflowState, status: str) -> int:
        """计算总体进度百分比"""
        if current_phase == WorkflowState.COMPLETED:
            return 100
        if current_phase not in self._default_workflow_sequence:
            return 0
        if status == "completed":
            completed_index = self._default_workflow_sequence.index(current_phase) + 1
            return int((completed_index / len(self._default_workflow_sequence)) * 100)
        else:
            current_index = self._default_workflow_sequence.index(current_phase)
            return int((current_index / len(self._default_workflow_sequence)) * 100)
