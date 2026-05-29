"""
Patent document generation module.

Architecture:
  1. feature_extractor: Analyzes 定稿文件/ docx files → extracts PatentFeatureProfile
  2. feature_profile: Data model describing all formatting/content characteristics
  3. generator: Produces docx files based on the feature profile (no direct file access)
  4. docx_parser: Low-level docx parsing utilities (used by extractor)

Workflow:
  extract_and_persist() → patent_feature_profile.json → generate_patent_docx()
"""

from src.document_gen.generator import generate_patent_docx, set_profile, reset_profile
from src.document_gen.feature_profile import (
    PatentFeatureProfile,
    load_profile,
    DEFAULT_PROFILE_PATH,
)
from src.document_gen.feature_extractor import (
    extract_profile,
    extract_and_persist,
)
from src.document_gen.docx_parser import (
    FormatMetadata,
    ParsedPatentDocx,
    ParsedDisclosure,
    FinalizedPatentEntry,
    parse_patent_docx,
    parse_disclosure_docx,
    scan_finalized_patents_dir,
    get_reference_format,
    extract_format_metadata,
)

__all__ = [
    # Generator
    "generate_patent_docx",
    "set_profile",
    "reset_profile",
    # Feature profile
    "PatentFeatureProfile",
    "load_profile",
    "DEFAULT_PROFILE_PATH",
    # Feature extraction
    "extract_profile",
    "extract_and_persist",
    # Docx parser (low-level)
    "FormatMetadata",
    "ParsedPatentDocx",
    "ParsedDisclosure",
    "FinalizedPatentEntry",
    "parse_patent_docx",
    "parse_disclosure_docx",
    "scan_finalized_patents_dir",
    "get_reference_format",
    "extract_format_metadata",
]
