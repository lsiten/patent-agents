"""LLM package.

Import concrete clients from `src.core.llm.client` and provider metadata from
`src.core.llm.providers`. Keeping this package initializer light prevents
configuration/provider imports from eagerly constructing client dependencies.
"""

__all__: list[str] = []
