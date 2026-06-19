# -*- coding: utf-8 -*-
"""WorkflowLifecycleMixin methods split from the workflow engine."""
from .shared import *


class WorkflowLifecycleMixin:
    def create_workflow(
        self,
        task_id: str,
        user_id: str,
        description: str,
        patent_type_preference: Optional[str] = None,
        skip_phases: Optional[List[WorkflowState]] = None,
        target_country: str = "中国",
        confirmed_preflight: Optional[Dict[str, Any]] = None,
    ) -> WorkflowContext:
        """创建新的工作流"""
        context = WorkflowContext(task_id=task_id, user_id=user_id, target_country=target_country)
        cleaned_description = self._sanitize_disclosure_text(description)
        context.original_description = cleaned_description
        context.title = self._extract_title(cleaned_description)
        context.metadata = {
            **context.metadata,
            "target_country": target_country,
            "raw_disclosure": description,
            "disclosure_sanitized": cleaned_description != description,
        }
        if confirmed_preflight:
            context.title = str(confirmed_preflight.get("patent_title") or context.title)
            context.merge_shared_agent_context("confirmed_preflight", confirmed_preflight)
            context.metadata["confirmed_preflight"] = confirmed_preflight
        if patent_type_preference is not None:
            context.metadata = {
                **context.metadata,
                "patent_type_preference": patent_type_preference,
            }

        self._running_workflows[task_id] = context

        self._logger.info(
            "Workflow created",
            task_id=task_id,
            user_id=user_id,
            target_country=target_country,
            description_length=len(description),
        )

        return context

    @staticmethod
    def _sanitize_disclosure_text(description: str) -> str:
        """Turn meeting transcripts into technical disclosure text before drafting."""
        if not description:
            return ""
        result = sanitize_transcript_text(description)
        return str(result.get("cleaned_text") or description).strip()

    @staticmethod
    def _extract_title(description: str) -> str:
        """Extract only an explicitly provided invention title.

        Meeting transcripts often begin with casual speech. Guessing a title from
        the first sentence leaks disclosure artifacts into the patent document, so
        missing titles must remain empty and be handled by the drafting/review loop.
        """
        if not description:
            return ""
        text = WorkflowLifecycleMixin._sanitize_disclosure_text(description)
        explicit_patterns = [
            r"(?:^|\n)\s*(?:发明名称|专利名称|申请名称|技术名称)\s*[:：]\s*(.+)",
            r"(?:^|\n)\s*名称\s*[:：]\s*(.+)",
        ]
        for pattern in explicit_patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            title = str(match.group(1) or "").strip()
            title = re.split(r"[\n。；;]", title, maxsplit=1)[0].strip(" ：:，,。")
            title = re.sub(r"^(一种|一项)?待命名[:：]?", "", title).strip()
            if 2 <= len(title) <= 60 and not re.search(r"\d{1,2}:\d{2}|\d{2}:\d{2}:\d{2}", title):
                return title
        return ""

    def get_workflow(self, task_id: str) -> Optional[WorkflowContext]:
        """获取工作流上下文"""
        return self._running_workflows.get(task_id)

    def list_workflows(self) -> List[WorkflowContext]:
        """列出所有工作流上下文"""
        return list(self._running_workflows.values())

    async def _persist_loop_and_sediment_skills(
        self,
        context: WorkflowContext,
        terminal_state: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Persist loop state and write per-agent Hermes skills.

        Skill sedimentation is an auxiliary learning step. It must never mask the
        workflow's real terminal result, so all exceptions are logged and swallowed.
        """
        try:
            from src.core.workflow.agent_loop import persist_patent_loop_snapshot
            from src.agents.hermes.skill_learning import sediment_workflow_skills

            snapshot = persist_patent_loop_snapshot(context, terminal_state)
            touched = sediment_workflow_skills(context, snapshot)
            context.metadata["loop_snapshot_path"] = snapshot.get("path", "")
            context.metadata["sedimented_skills"] = touched
            if event_callback:
                display_names = {
                    "ceo": "CEO Agent",
                    "requirement_analyst": "需求分析师",
                    "retrieval_analyst": "检索分析师",
                    "patent_writer": "专利撰写 Agent",
                    "quality_reviewer": "质量审查 Agent",
                }
                for item in touched:
                    agent_profile = item.get("agent_profile", "")
                    agent_name = display_names.get(agent_profile, agent_profile or "Agent")
                    event_callback(
                        agent_name,
                        "agent.skill_sedimented",
                        f"🧠 已沉淀技能：{item.get('skill', '')}",
                        {
                            "agent_name": agent_name,
                            "content": item.get("skill_path", ""),
                            "message": f"已沉淀技能：{item.get('skill', '')}",
                            "skill": item.get("skill", ""),
                            "skill_path": item.get("skill_path", ""),
                            "log_path": item.get("log_path", ""),
                        },
                    )
                event_callback(
                    "CEO Agent",
                    "agent.content",
                    f"🧠 已完成自动技能沉淀：{len(touched)} 个 Agent profile",
                    {
                        "agent_name": "CEO Agent",
                        "content": "Hermes profile-local skills updated",
                        "loop_snapshot_path": snapshot.get("path", ""),
                        "skills": touched,
                    },
                )
            return snapshot
        except Exception as exc:
            self._logger.warning(
                f"Failed to persist loop snapshot or sediment skills: {exc}",
                task_id=context.task_id,
                exc_info=True,
            )
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "agent.thinking",
                    "⚠️ 自动技能沉淀失败，不影响当前流程状态",
                    {
                        "agent_name": "CEO Agent",
                        "thought": "skill_sedimentation_failed",
                        "error": str(exc),
                    },
                )
            return {}
