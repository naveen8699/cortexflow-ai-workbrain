"""
AlloyDB MCP Toolbox Integration for WorkBrain
Uses MCP Toolbox for Databases to give ADK agents direct AlloyDB access
"""
import logging
import os
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams, SseConnectionParams

logger = logging.getLogger(__name__)

TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://localhost:5000")

def get_alloydb_mcp_toolset() -> MCPToolset:
    """
    Returns MCPToolset connected to MCP Toolbox for AlloyDB.
    Gives ADK agents direct access to AlloyDB data via MCP protocol.
    """
    return MCPToolset(
        connection_params=SseConnectionParams(
            url=f"{TOOLBOX_URL}/mcp/sse",
        )
    )
