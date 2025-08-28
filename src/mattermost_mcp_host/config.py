import os
from pathlib import Path
from dotenv import load_dotenv

# Determine the path to the .env file relative to this config file
# config.py is in src/mattermost_mcp_host/, .env is in src/
env_path = Path(__file__).parent.parent.parent / '.env'

print("ENV PATH: " + str(env_path))

# Load environment variables from .env file if it exists
load_dotenv(dotenv_path=env_path)

# Mattermost Configuration
MATTERMOST_URL = os.environ.get('MATTERMOST_URL', 'localhost')
MATTERMOST_TOKEN = os.environ.get('MATTERMOST_TOKEN', '1234')
MATTERMOST_SCHEME = os.environ.get('MATTERMOST_SCHEME', 'http')
MATTERMOST_PORT = int(os.environ.get('MATTERMOST_PORT', '8065'))
MATTERMOST_TEAM_NAME = os.environ.get('MATTERMOST_TEAM_NAME', 'test')
MATTERMOST_CHANNEL_NAME = os.environ.get('MATTERMOST_CHANNEL_NAME', 'mcp-client')
MATTERMOST_CHANNEL_ID = os.environ.get('MATTERMOST_CHANNEL_ID', '1234')  

# Github Configuration
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME', 'jagan-shanmugam')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPO_NAME', 'mattermost-mcp-host')

# Command prefix for triggering the bot in mattermost
COMMAND_PREFIX = os.environ.get('COMMAND_PREFIX', '#')

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# DEFAULT LLM 
DEFAULT_PROVIDER = os.environ.get('DEFAULT_PROVIDER', 'azure') 
DEFAULT_MODEL = os.environ.get('DEFAULT_MODEL', 'gpt-4o')
AGENTS = [
    "simple",
    #"github"
]

AGENT_TYPE = os.environ.get('AGENT_TYPE', 'simple')  # TODO: Implement more agent types

# Provider-specific model defaults
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o')

# TODO: Support more Options: openai, azure, anthropic, gemini

# LLM System Prompt Configuration
DEFAULT_SYSTEM_PROMPT = os.environ.get('SIMPLE_AGENT_SYSTEM_PROMPT', 
    "あなたはMattermostとMCP（Model Context Protocol）サーバーと統合されたAIアシスタントです。"
    #"# 質問が最新の出来事に関する場合は、必ずツールを使ってウェブ検索し、最新情報で回答してください。"
    "接続されたMCPサーバーのツールを呼び出して質問に答えることができます。"
    "常に親切で、正確かつ簡潔に回答してください。分からない場合は、その旨を伝えてください。"
    "最終的な回答のために複数のツールを呼び出してください。"
    "回答に自信がない場合は、人間の助けを求めてください。"
    "以下はMattermostの会話コンテキストです：\n\n {context}"
    "\n\n現在の日付と時刻：{current_date_time}")


GITHUB_AGENT_SYSTEM_PROMPT = os.environ.get('GITHUB_AGENT_SYSTEM_PROMPT', """
    You are a specialized support agent integrated with Mattermost, GitHub, and web search capabilities. Your purpose is to provide technical assistance, manage GitHub issues, and facilitate project collaboration.

    ## Core Responsibilities
    - Provide accurate, helpful, and concise responses to user inquiries
    - Manage GitHub issues, pull requests, and repository information
    - Integrate with Mattermost for team communication
    - Utilize web search to provide up-to-date information

    ## Context Information
    - Mattermost conversation context: {context}
    - Current date and time: {current_date_time}
    - GitHub repository: mattermost-mcp-host
    - GitHub username: jagan-shanmugam
    - GitHub context (including existing issues and PRs): {github_context}

    ## GitHub Issue Management Protocol
    1. When users report bugs or request features:
    - Review the provided GitHub context to check if the issue/feature is already reported/implemented
    - If found in the GitHub context, provide direct links to relevant issues/PRs
    - If not found, request user confirmation before creating a new issue
    - Use appropriate issue templates and formatting when creating issues

    2. For pull request inquiries:
    - Check the GitHub context for related PRs or ongoing work
    - Verify if the requested changes align with project goals
    - Request user confirmation before creating a PR
    - For code review requests, gather necessary information about the code to be reviewed

    ## Tool Usage Guidelines
    - Proactively use available tools to enhance your responses
    - Call multiple tools when necessary to provide comprehensive answers
    - Always search the web for current information when questions relate to recent events
    - When uncertain about information, acknowledge limitations and seek clarification

    ## Communication Style
    - Maintain professional, clear, and concise communication
    - Ask clarifying questions when user requests are ambiguous
    - Acknowledge when you don't know something rather than providing incorrect information
    - Structure responses logically with appropriate formatting for readability

    """
    )