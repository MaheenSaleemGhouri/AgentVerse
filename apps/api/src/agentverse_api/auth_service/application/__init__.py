"""Application layer: use cases orchestrating the domain layer.

Depends inward on `domain` only — never on `interface` or a concrete
`infrastructure` class, only on the `Protocol` ports `domain/ports.py`
defines (CLAUDE.md §5).
"""
