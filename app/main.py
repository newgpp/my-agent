from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.sql import router as sql_router
from app.config import get_settings
from app.mcp.runner import MCPRunner
from loguru import logger

@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI lifespan handler for MCP runner."""
    logger.info("Starting application")
    await mcp_runner.start()
    try:
        yield
    finally:
        logger.info("Stopping application")
        await mcp_runner.close()


app = FastAPI(lifespan=lifespan)

mcp_runner = MCPRunner()


app.include_router(chat_router)
app.include_router(sql_router)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
        http="h11",
    )
