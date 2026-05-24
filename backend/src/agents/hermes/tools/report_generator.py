"""
ReportGeneratorTool - 报告生成工具
生成各阶段的标准化报告文档
"""
import json
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger

logger = get_logger(__name__)


class ReportGeneratorTool(HermesTool):
    """
    报告生成工具
    生成标准化的报告文档，支持多种格式输出
    """
    name = "report_generator"
    description = "生成标准化的报告文档，支持多种格式输出"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "report_type": HermesToolParameter(
                    type="string",
                    description="报告类型：requirement / retrieval / quality / final",
                    required=True,
                ),
                "content": HermesToolParameter(
                    type="string",
                    description="报告内容（JSON格式）",
                    required=True,
                ),
                "format": HermesToolParameter(
                    type="string",
                    description="输出格式：markdown / json / html",
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        report_type: str,
        content: str,
        format: str = "markdown",
    ) -> Dict[str, Any]:
        """生成报告"""
        logger.info("Generating report", type=report_type, format=format)

        try:
            data = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            data = {"raw_content": content}

        # 根据报告类型生成不同格式
        if format == "markdown":
            report_content = self._generate_markdown_report(report_type, data)
        elif format == "html":
            report_content = self._generate_html_report(report_type, data)
        else:
            report_content = json.dumps(data, ensure_ascii=False, indent=2)

        return {
            "report_type": report_type,
            "format": format,
            "content": report_content,
            "generated_at": datetime.now().isoformat(),
            "metadata": {
                "sections_count": len(data) if isinstance(data, dict) else 1,
                "word_count": len(report_content),
            },
        }

    def _generate_markdown_report(self, report_type: str, data: Dict) -> str:
        """生成 Markdown 格式报告"""
        title_map = {
            "requirement": "专利申请需求分析报告",
            "retrieval": "专利检索分析报告",
            "quality": "质量审查报告",
            "final": "专利申请最终报告",
        }

        title = title_map.get(report_type, "专利申请报告")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# {title}",
            "",
            f"> 生成时间：{timestamp}",
            "",
            "---",
            "",
        ]

        # 递归生成内容
        def _dict_to_markdown(d: Dict, level: int = 2) -> list:
            result = []
            for key, value in d.items():
                # 将下划线转换为空格并首字母大写
                display_key = key.replace("_", " ").title()
                prefix = "#" * level

                if isinstance(value, dict):
                    result.append(f"{prefix} {display_key}")
                    result.append("")
                    result.extend(_dict_to_markdown(value, level + 1))
                    result.append("")
                elif isinstance(value, list):
                    result.append(f"{prefix} {display_key}")
                    result.append("")
                    for i, item in enumerate(value, 1):
                        if isinstance(item, dict):
                            result.append(f"**{i}.**")
                            for k, v in item.items():
                                result.append(f"   - **{k}**: {v}")
                        else:
                            result.append(f"- {item}")
                    result.append("")
                else:
                    result.append(f"{prefix} {display_key}")
                    result.append("")
                    result.append(str(value))
                    result.append("")
            return result

        lines.extend(_dict_to_markdown(data))

        # 添加页脚
        lines.extend([
            "---",
            "",
            "> 本报告由专利申请智能体系统自动生成",
        ])

        return "\n".join(lines)

    def _generate_html_report(self, report_type: str, data: Dict) -> str:
        """生成 HTML 格式报告"""
        markdown = self._generate_markdown_report(report_type, data)

        # 简单的 Markdown 到 HTML 转换
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>专利申请报告 - {report_type}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 1000px; margin: 0 auto; padding: 2rem; }}
        h1 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 0.5rem; }}
        h2 {{ color: #202124; margin-top: 1.5rem; }}
        h3 {{ color: #3c4043; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
        th, td {{ border: 1px solid #dadce0; padding: 0.75rem; text-align: left; }}
        th {{ background-color: #f8f9fa; font-weight: 600; }}
        blockquote {{ background-color: #f8f9fa; border-left: 4px solid #1a73e8; padding: 1rem; margin: 1rem 0; }}
        code {{ background-color: #f1f3f4; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; }}
        pre {{ background-color: #f8f9fa; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
    </style>
</head>
<body>
<pre>{markdown}</pre>
</body>
</html>"""
        return html


def register(factory) -> None:
    """注册此工具到 Agent 工厂"""
    factory.register_tool_class("report_generator", ReportGeneratorTool)
