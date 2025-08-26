"""
Mattermost MCP Host - Integration between Mattermost and MCP servers
"""

import mattermost_mcp_host.config as config

import logging

__version__ = "0.1.0"

# ロギング設定
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)