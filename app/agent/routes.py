from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, List

from app.prompts.loader import load_prompt


@dataclass(frozen=True)
class RouteContext:
    name: str
    system_prompt: str
    tool_allowlist: FrozenSet[str]
    extra_system_messages: List[str]


def get_route_context(route: str) -> RouteContext:
    if route == "file_list":
        return RouteContext(
            name="file_list",
            system_prompt=load_prompt("route_file_list"),
            tool_allowlist=frozenset({"list_directory", "read_file"}),
            extra_system_messages=[],
        )
    if route == "sql_generate":
        return RouteContext(
            name="sql_generate",
            system_prompt=load_prompt("route_sql_generate"),
            tool_allowlist=frozenset(),
            extra_system_messages=[],
        )
    if route == "ledger":
        return RouteContext(
            name="ledger",
            system_prompt=load_prompt("route_ledger"),
            tool_allowlist=frozenset(
                {"ocr_receipt", "transcribe_audio", "ledger_upsert"}
            ),
            extra_system_messages=[],
        )
    return RouteContext(
        name="external_knowledge",
        system_prompt=load_prompt("route_external_knowledge"),
        tool_allowlist=frozenset({"tavily_search"}),
        extra_system_messages=[],
    )


def get_sql_route_context() -> RouteContext:
    from app.resources.provider import get_resource

    return RouteContext(
        name="sql_generate",
        system_prompt=load_prompt("text_to_sql"),
        tool_allowlist=frozenset(),
        extra_system_messages=[
            get_resource("context://db_schema"),
            get_resource("context://business_glossary"),
        ],
    )
