import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv

from app.api.chat import router as chat_router
from app.mcp.runner import MCPRunner
from loguru import logger

load_dotenv()

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


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False, http="h11")
