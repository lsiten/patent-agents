# -*- coding: utf-8 -*-
"""Composed patent workflow engine.

Large workflow responsibilities live in focused mixin modules under
``src.core.workflow``. This file wires the runtime together and preserves the
public ``PatentWorkflowEngine`` entry point.
"""
from .agent_runtime import WorkflowAgentRuntimeMixin
from .contracts import WorkflowContractMixin
from .drafting import WorkflowDraftingMixin
from .drawings import WorkflowDrawingMixin
from .execution import WorkflowExecutionMixin
from .lifecycle import WorkflowLifecycleMixin
from .prompts import WorkflowPromptMixin
from .quality_gates import WorkflowQualityGateMixin
from .shared import *
from .state_context import WorkflowStateContextMixin


class PatentWorkflowEngine(
    WorkflowStateContextMixin,
    WorkflowLifecycleMixin,
    WorkflowExecutionMixin,
    WorkflowPromptMixin,
    WorkflowQualityGateMixin,
    WorkflowDrawingMixin,
    WorkflowDraftingMixin,
    WorkflowContractMixin,
    WorkflowAgentRuntimeMixin,
):
    """Patent workflow engine composed from domain mixins."""

    def __init__(self):
        self._logger = get_logger("patent_workflow")
        self._running_workflows: Dict[str, WorkflowContext] = {}
        self._default_workflow_sequence = [
            WorkflowState.BRAINSTORMING,
            WorkflowState.REQUIREMENT_ANALYSIS,
            WorkflowState.RETRIEVAL_ANALYSIS,
            WorkflowState.PATENT_WRITING,
            WorkflowState.QUALITY_REVIEW,
        ]


_global_workflow_engine: Optional[PatentWorkflowEngine] = None


def get_workflow_engine() -> PatentWorkflowEngine:
    """Return the process-wide workflow engine singleton."""
    global _global_workflow_engine
    if _global_workflow_engine is None:
        _global_workflow_engine = PatentWorkflowEngine()
    return _global_workflow_engine
