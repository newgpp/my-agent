import os
from typing import Any, Dict, Optional

from loguru import logger
from tavily import TavilyClient
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

mcp = FastMCP("tavily")
load_dotenv()


def _get_client() -> TavilyClient:
    """Create a Tavily client from environment config."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    logger.info("Tavily client initialized")
    return TavilyClient(api_key=api_key)


@mcp.tool()
def tavily_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_answer: bool = False,
    include_raw_content: bool = False,
    include_images: bool = False,
    time_range: Optional[str] = None,
) -> Dict[str, Any]:
    """Search the web with Tavily and return results."""
    logger.info("tavily_search query='{}' max_results={} depth={}", query, max_results, search_depth)
    client = _get_client()
    params: Dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
        "include_images": include_images,
    }
    if time_range:
        params["time_range"] = time_range
    return client.search(**params)


if __name__ == "__main__":
    logger.info("Starting Tavily MCP server")
    mcp.run()
