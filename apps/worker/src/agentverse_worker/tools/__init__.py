"""The central tool-execution boundary and its execution policy.

Every tool call — native, MCP-sourced, or SDK-wrapped — routes through
`boundary.execute_tool`. There is no trusted fast path (ADR-0010).
"""
