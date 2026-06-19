# -*- coding: utf-8 -*-
"""WorkflowStateContextMixin methods split from the workflow engine."""
from .shared import *


class WorkflowStateContextMixin:
    def _node_for_state(self, phase_state: WorkflowState | str) -> str:
        value = getattr(phase_state, "value", phase_state)
        return _WORKFLOW_STATE_TO_NODE.get(str(value), str(value))

    def _node_for_context_field(self, context_field: str) -> str:
        return _CONTEXT_FIELD_TO_NODE.get(context_field, context_field)

    def _phase_round_index(self, context: WorkflowContext, node: str) -> int:
        rounds = context.metadata.setdefault("phase_rounds", {})
        if not isinstance(rounds, dict):
            context.metadata["phase_rounds"] = {}
            rounds = context.metadata["phase_rounds"]
        node_rounds = rounds.setdefault(node, [])
        if not isinstance(node_rounds, list):
            rounds[node] = []
            node_rounds = rounds[node]
        return len(node_rounds) + 1

    def _summarize_for_checkpoint(self, data: Any, limit: int = 5000) -> Any:
        """Return a bounded JSON-safe summary for checkpoint files and events."""
        if data in (None, "", [], {}):
            return data
        try:
            clean = json.loads(json.dumps(data, ensure_ascii=False, default=str))
        except Exception:
            clean = str(data)
        text = json.dumps(clean, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return clean
        return {
            "_truncated": True,
            "preview": text[:limit],
            "original_length": len(text),
        }

    def _build_workflow_snapshot(self, context: WorkflowContext) -> Dict[str, Any]:
        return {
            "task_id": context.task_id,
            "conversation_id": context.metadata.get("conversation_id"),
            "status": getattr(context.current_phase, "value", str(context.current_phase)),
            "current_node": self._node_for_state(context.current_phase),
            "current_round": context.iteration_count,
            "shared_facts_version": int(context.metadata.get("shared_facts_version") or 0),
            "shared_facts": self._summarize_for_checkpoint(context.shared_agent_context, limit=12000),
            "phase_rounds": self._summarize_for_checkpoint(
                context.metadata.get("phase_rounds", {}),
                limit=18000,
            ),
            "open_gaps": self._summarize_for_checkpoint(
                context.metadata.get("open_gaps")
                or context.shared_agent_context.get("unresolved_questions")
                or context.shared_agent_context.get("open_gaps")
                or [],
                limit=4000,
            ),
            "resolved_gaps": self._summarize_for_checkpoint(
                context.metadata.get("resolved_gaps")
                or context.shared_agent_context.get("resolved_questions")
                or [],
                limit=4000,
            ),
            "route_history": self._summarize_for_checkpoint(
                context.metadata.get("route_history", []),
                limit=8000,
            ),
            "interrupt": self._summarize_for_checkpoint(
                context.metadata.get("quality_remediation")
                or context.metadata.get("workflow_interrupt")
                or None,
                limit=4000,
            ),
        }

    def _persist_graph_checkpoint(
        self,
        context: WorkflowContext,
        reason: str,
        *,
        node: Optional[str] = None,
        round_index: Optional[int] = None,
        event: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        checkpoint = {
            "reason": reason,
            "node": node or self._node_for_state(context.current_phase),
            "round": round_index,
            "event": self._summarize_for_checkpoint(event or {}, limit=10000),
            "workflow_state": self._build_workflow_snapshot(context),
            "created_at": datetime.now().isoformat(),
        }
        try:
            path = _persist_workflow_checkpoint(context.task_id, checkpoint)
            context.metadata["latest_graph_checkpoint_path"] = path
            return path
        except Exception as exc:
            self._logger.warning(
                "Failed to persist workflow checkpoint",
                task_id=context.task_id,
                reason=reason,
                error=str(exc),
            )
            return None

    def _agui_metadata(
        self,
        context: WorkflowContext,
        agent_name: str,
        event_type: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(data or {})
        node = (
            payload.get("node")
            or payload.get("phase_node")
            or self._node_for_state(payload.get("phase") or context.current_phase)
        )
        return ensure_agui_payload(
            payload=payload,
            event_type=event_type,
            run_id=context.task_id,
            agent_name=agent_name,
            node=node,
            status=getattr(context.current_phase, "value", str(context.current_phase)),
            current_round=payload.get("round") or context.iteration_count,
            shared_facts_version=int(context.metadata.get("shared_facts_version") or 0),
            message=message,
        )

    def _record_phase_round(
        self,
        context: WorkflowContext,
        *,
        node: str,
        context_field: str,
        status: str,
        output: Any = None,
        duration_seconds: Optional[float] = None,
        issues: Optional[List[str]] = None,
        artifact_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        rounds = context.metadata.setdefault("phase_rounds", {})
        if not isinstance(rounds, dict):
            context.metadata["phase_rounds"] = {}
            rounds = context.metadata["phase_rounds"]
        node_rounds = rounds.setdefault(node, [])
        if not isinstance(node_rounds, list):
            rounds[node] = []
            node_rounds = rounds[node]
        round_index = len(node_rounds) + 1
        record = {
            "node": node,
            "context_field": context_field,
            "round": round_index,
            "status": status,
            "duration_seconds": duration_seconds,
            "issues": issues or [],
            "artifact_path": artifact_path,
            "shared_facts_version": int(context.metadata.get("shared_facts_version") or 0),
            "output": self._summarize_for_checkpoint(output, limit=8000),
            "created_at": datetime.now().isoformat(),
        }
        node_rounds.append(record)
        self._persist_graph_checkpoint(
            context,
            f"{node}_round_{round_index}_{status}",
            node=node,
            round_index=round_index,
            event=record,
        )
        return record

    def _phase_contract_summary(self, context_field: str) -> Dict[str, Any]:
        return phase_contract_summary(context_field)

    def _invalidate_downstream_outputs(
        self,
        context: WorkflowContext,
        phase_state: WorkflowState,
        reason: str,
        preserve_fields: Optional[List[str]] = None,
    ) -> None:
        """Clear current downstream artifacts after an upstream phase changes.

        Phase history is preserved for per-round UI tabs. Only current context
        fields are cleared, so an older draft/review cannot be treated as the
        latest valid output after requirement or retrieval has changed.
        """
        fields = _DOWNSTREAM_CONTEXT_FIELDS.get(phase_state, ())
        if not fields:
            return
        preserved = set(preserve_fields or [])
        invalidated: List[str] = []
        for field in fields:
            if field in preserved:
                continue
            if getattr(context, field, None):
                setattr(context, field, {})
                invalidated.append(field)
        if invalidated:
            context.metadata["stale_downstream_outputs"] = {
                "phase": phase_state.value,
                "fields": invalidated,
                "reason": reason,
                "invalidated_at": datetime.now().isoformat(),
            }

    def _preserve_downstream_fields_after_phase(
        self,
        phase_state: WorkflowState,
        phase_output: Any,
    ) -> List[str]:
        """Return downstream artifacts that remain valid after an upstream round.

        Requirement analysis has two modes in the current loop:
        1. initial analysis or substantive update before retrieval, which must
           invalidate old retrieval/writing/review artifacts;
        2. post-retrieval review confirming gaps are closed, which must preserve
           the retrieval report that was just reviewed and only invalidate stale
           draft/review artifacts.
        """
        if phase_state != WorkflowState.REQUIREMENT_ANALYSIS or not isinstance(phase_output, dict):
            return []

        retrieval_review = phase_output.get("retrieval_feedback_review")
        if isinstance(retrieval_review, dict) and self._requirement_review_allows_drafting(
            retrieval_review
        ):
            return ["retrieval_report"]

        if self._requirement_review_allows_drafting(phase_output):
            return ["retrieval_report"]

        return []

    def _update_shared_context_from_phase(
        self,
        context: WorkflowContext,
        context_field: str,
        data: Any,
    ) -> None:
        """Share confirmed phase facts with downstream Agents without hiding full artifacts."""
        if not isinstance(data, dict) or not data:
            return
        phase_key = {
            "requirement_analysis": "latest_requirement_analysis",
            "retrieval_report": "latest_retrieval_report",
            "patent_draft": "latest_patent_draft_summary",
            "review_report": "latest_quality_review",
        }.get(context_field, context_field)
        compact = json.loads(json.dumps(data, ensure_ascii=False, default=str))
        if context_field == "requirement_analysis":
            compact = self._attach_confirmed_preflight_to_requirement(context, compact)
        if context_field == "patent_draft":
            compact = self._build_quality_review_draft_summary(data)
        context.merge_shared_agent_context(phase_key, compact)

    def _attach_confirmed_preflight_to_requirement(
        self,
        context: WorkflowContext,
        requirement: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ensure requirement facts include the user-confirmed preflight package.

        Requirement analysis is allowed to focus on technical gaps, but downstream
        Agents and the preview UI still need the confirmed patent name/type and
        public facts in the same artifact instead of inferring them from chat.
        """
        if not isinstance(requirement, dict):
            return requirement
        enriched = dict(requirement)
        confirmed = (
            context.metadata.get("confirmed_preflight")
            or context.shared_agent_context.get("confirmed_preflight")
            or {}
        )
        if not isinstance(confirmed, dict):
            confirmed = {}

        patent_title = str(
            enriched.get("patent_title")
            or enriched.get("title")
            or confirmed.get("patent_title")
            or context.title
            or ""
        ).strip()
        if patent_title:
            enriched.setdefault("patent_title", patent_title)
            enriched.setdefault("title", patent_title)

        patent_type = str(
            enriched.get("patent_type")
            or confirmed.get("patent_type")
            or confirmed.get("专利类型")
            or ""
        ).strip()
        if patent_type and "patent_type" not in enriched:
            enriched["patent_type"] = patent_type

        if "confirmed_facts" not in enriched:
            facts = {
                k: v
                for k, v in confirmed.items()
                if k
                in {
                    "patent_title",
                    "patent_type",
                    "public_status",
                    "claim_mainline",
                    "technical_solution",
                    "drawing_plan",
                    "protection_focus",
                }
                and v not in (None, "", [], {})
            }
            if facts:
                enriched["confirmed_facts"] = facts
        return enriched

