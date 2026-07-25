"""Domain layer: workspace/RBAC entities and business rules.

Zero framework imports — no FastAPI, no SQLAlchemy, no Pydantic
(CLAUDE.md §5). `infrastructure/models.py` maps these to ORM rows;
`interface/schemas/` maps them to API request/response shapes. Neither
direction leaks into this module.
"""
