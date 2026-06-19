# -*- coding: utf-8 -*-
"""Compatibility facade for the modular workflow engine package.

The implementation lives in :mod:`src.core.workflow.engine`.  This module is
kept as an import-compatible alias while callers are migrated to the package
path.
"""
import sys

from src.core.workflow import engine as _engine
from src.core.workflow.engine import *  # noqa: F401,F403

sys.modules[__name__] = _engine
