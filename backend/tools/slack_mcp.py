"""
Slack MCP Integration for WorkBrain
Uses ADK's MCPToolset to connect to Slack via Model Context Protocol
"""
import logging
import os
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams

logger = logging.getLogger(__name__)

def get_slack_mcp_toolset() -> MCPToolset:
    slack_token = os.environ.get(
        "SLACK_BOT_TOKEN",
       ""
    )
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params={
                "command": "mcp-server-slack",
                "args": [],
                "env": {
                    "SLACK_BOT_TOKEN": slack_token,
                    "SLACK_TEAM_ID": "T0AVCQXE5V0",
                    "PATH": "/usr/local/nvm/versions/node/v24.14.1/bin:/usr/bin:/bin",
                }
            }
        )
    )
