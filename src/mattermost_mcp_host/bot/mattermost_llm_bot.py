import mattermost_mcp_host.config as config
from mattermost_mcp_host.bot.mattermost_base_bot import MattermostBaseBot
from mattermost_mcp_host.agent.utils import get_final_response, get_thread_history, add_reaction
from mattermost_mcp_host.agent.model import get_llm
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

import asyncio
import logging
import json
from datetime import datetime

# 以下のインポートを追加
import traceback

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

PROCESSING_MESSAGE = "Processing your request..."

# ロギング設定
logger = logging.getLogger(__name__)

class MattermostLLMBot(MattermostBaseBot):
    """Mattermost LLMボット"""
    def __init__(self, llm, tools=[]):
        super().__init__()
        self.command_prefix = config.COMMAND_PREFIX
        self.llm = llm
        self.tools = tools
        self.system_prompt = config.DEFAULT_SYSTEM_PROMPT
        
    async def initialize(self):
        """初期化"""
        await super().initialize()
        # エージェント作成
        self.agent = create_react_agent(self.llm, self.tools)
        
    
    async def handle_llm_request(self, channel_id: str, message: str, user_id: str, post_id: str = None, root_id: str = None):
        """
        LLMへのリクエストを処理
        
        Args:
            channel_id: チャンネルID
            message: ユーザーのメッセージテキスト
            user_id: 会話履歴を追跡するためのユーザーID
            post_id: スレッド化のための投稿ID
        """
        try:
            # リアクションの送信
            await asyncio.sleep(1)
            add_reaction(self.mattermost_client.driver, post_id, "robot")
            
            # スレッド履歴の取得
            # root_idが空の場合、自身が新しいスレッドのルート
            root_id = post_id if root_id is None or root_id == "" else root_id
            logger.info(f"Fetching thread history for root_id: {root_id}")
            
            # スレッド履歴の取得（新しい会話の場合は空）
            thread_history = await get_thread_history(self.mattermost_client.driver, root_id, channel_id)
            
            # エージェント用のメッセージをフォーマット
            logger.info(f"Running agent with message: {message}")
            metadata={
                "channel_id": channel_id,
                "team_name": config.MATTERMOST_TEAM_NAME.lower().replace(" ", "-"),
                "channel_name": config.MATTERMOST_CHANNEL_NAME.lower().replace(" ", "-"),
            }
            # システムプロンプトを追加
            messages = [SystemMessage(content=self.system_prompt.format(context=metadata, 
                                                                    current_date_time=datetime.now().isoformat()))]
            # スレッド履歴を追加
            for msg in thread_history:
                if msg["content"] == message:
                    continue
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    if msg["content"] != PROCESSING_MESSAGE:
                        messages.append(AIMessage(content=msg["content"]))
            
            # ユーザークエリを追加
            messages.append(HumanMessage(content=message))
            
            
            # エージェント実行
            state = {"messages": messages}
            result = await self.agent.ainvoke(state)

            # エージェントのメッセージから最終応答を抽出
            responses = get_final_response(result["messages"], message)
            logger.info(f"Agent response: {responses}")
            #previous_agent_responses = [msg["content"] for msg in thread_history if msg["role"] == "assistant"]
            
            for response in responses:
                #if response not in previous_agent_responses: # 重複を避けるために以前のエージェントの応答を除外
                await self.send_response(channel_id, response or "No response generated", root_id)
                
        except Exception as e:
            logger.error(f"Error handling LLM request: {str(e)}")
            logger.error(traceback.format_exc())
            await self.send_response(channel_id, f"Error processing your request: {str(e)}", root_id)

    async def handle_message(self, post):
        """Mattermostからの受信メッセージを処理"""
        try:
            logger.info(f"Received post: {json.dumps(post, indent=2)}")  # より良いロギング
            
            # ボット自身からのメッセージはスキップ
            if post.get('user_id') == self.mattermost_client.driver.client.userid:
                return
            
            # メッセージデータの抽出
            channel_id = post.get('channel_id')
            message = post.get('message', '')
            user_id = post.get('user_id')
            post_id = post.get('id') 
            root_id = post.get('root_id')
            if root_id == '':
                root_id = post_id
            
            # 特定のチャンネルが設定されている場合、他のチャンネルからのメッセージはスキップ
            if self.channel_id and channel_id != self.channel_id:
                logger.info(f'Received message from a different channel - {channel_id} than configured - {self.channel_id}')
                # ボットへのダイレクトメッセージと設定されたチャンネルのメッセージのみを処理
                # if not any(team_member.get('mention_keys', []) in message for team_member in self.mattermost_client.driver.users.get_user_teams(user_id)):
                #     return
            
            # メッセージがコマンドプレフィックスで始まるかチェック
            if message.startswith(self.command_prefix):
                # MCPコマンドの処理
                # 処理前にコマンドプレフィックスを削除
                message = message[len(self.command_prefix):].strip()
                await self.handle_command(channel_id, message, user_id, post_id, root_id)
            else:
                # LLMへのダイレクトメッセージ
                await self.handle_llm_request(channel_id, message, user_id, post_id, root_id)
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            logger.error(traceback.format_exc())

    async def handle_command(self, channel_id, message_text, user_id, post_id=None, root_id=None):
        """Mattermostからのコマンドメッセージを処理"""
        try:
            root_id = post_id if root_id is None or root_id == "" else root_id

            # コマンドテキストの分割
            command_parts = message_text.split()
            
            if len(command_parts) < 1:
                await self.send_help_message(channel_id, root_id)
                return
            
            command = command_parts[0]
            
            if command == 'help':
                await self.send_help_message(channel_id, root_id)
                return
            
            if command == 'servers':
                response = "Available MCP servers:\n"
                for name in self.mcp_clients.keys():
                    response += f"- {name}\n"
                await self.send_response(channel_id, response, root_id)
                return
            
            # 最初の引数がサーバー名かチェック
            server_name = command
            if server_name not in self.mcp_clients:
                await self.send_response(
                    channel_id,
                    f"Unknown server '{server_name}'. Available servers: {', '.join(self.mcp_clients.keys())}",
                    root_id
                )
                return
            
            if len(command_parts) < 2:
                await self.send_response(
                    channel_id,
                    f"Invalid command. Use {self.command_prefix}{server_name} <command> [arguments]",
                    root_id
                )
                return
            
            client = self.mcp_clients[server_name]
            subcommand = command_parts[1]
            
            # サブコマンドの処理
            if subcommand == 'tools':
                tools = await client.list_tools()
                response = f"Available tools for {server_name}:\n"
                for name, tool in tools.items():
                    response += f"- {name}: {tool.description}\n"
                await self.send_response(channel_id, response, root_id)
            else:
                # フォールバックとしてLLMの使用を試行
                await self.handle_llm_request(channel_id, message_text, user_id, root_id)
                
        except Exception as e:
            logger.error(f"Error processing command: {str(e)}")
            await self.send_response(channel_id, f"Error processing command: {str(e)}", root_id)

    async def send_help_message(self, channel_id, post_id=None):
        """利用可能なすべてのコマンドを説明する詳細なヘルプメッセージを送信"""
        help_text = f"""
                **MCPクライアント ヘルプ**
                `{self.command_prefix}<command>` を使用してMCPサーバーと対話します。

                **利用可能なコマンド:**
                1. `{self.command_prefix}help` - このヘルプメッセージを表示
                2. `{self.command_prefix}servers` - 利用可能なすべてのMCPサーバーを一覧表示

                **サーバー固有のコマンド:**
                `{self.command_prefix}<server_name> <command>` を使用して特定のサーバーと対話します。

                **各サーバーのコマンド:**
                1. `{self.command_prefix}<server_name> tools` - サーバーで利用可能なすべてのツールを一覧表示

                **例:**
                • サーバーの一覧表示:
                `{self.command_prefix}servers`
                • サーバーのツール一覧表示:
                `{self.command_prefix}simple-mcp-server tools`
                • ツールの呼び出し:
                `{self.command_prefix}simple-mcp-server call echo message "Hello World"`

                **注:**
                - ツールパラメータは名前と値のペアで指定する必要があります。
                - 複数のパラメータを持つツールには、JSON形式を使用してください:
                `{self.command_prefix}<server_name> call <tool_name> parameters '{{"param1": "value1", "param2": "value2"}}'`
                
                **直接対話:**
                必要に応じてツールを使用するAIアシスタントと直接チャットすることも可能です。
                """
        await self.send_response(channel_id, help_text, post_id)
    
    async def send_tool_help(self, channel_id, server_name, tool_name, tool, post_id=None):
        """特定のツールのヘルプメッセージを送信"""
        help_text = f"""
                    **ツールヘルプ: {tool_name}**
                    説明: {tool.description}

                    **パラメータ:**
                    """
        if hasattr(tool, 'inputSchema') and tool.inputSchema:
            required = tool.inputSchema.get('required', [])
            properties = tool.inputSchema.get('properties', {})
            for param_name, param_info in properties.items():
                req_mark = "*" if param_name in required else ""
                param_type = param_info.get('type', 'any')
                param_desc = param_info.get('description', '')
                help_text += f"- {param_name}{req_mark}: {param_type}"
                if param_desc:
                    help_text += f" - {param_desc}"
                help_text += "\n"
            help_text += "\n* = 必須パラメータ"
        else:
            help_text += "パラメータは不要です"

        help_text += f"\n\n**例:**\n`{self.command_prefix}{server_name} call {tool_name} "
        if hasattr(tool, 'inputSchema') and tool.inputSchema.get('required'):
            first_required = tool.inputSchema['required'][0]
            help_text += f"{first_required} <value>`"
        else:
            help_text += "<parameter_name> <value>`"

        await self.send_response(channel_id, help_text, post_id)
        
    async def run(self):
        """実行"""
        try:
            await self.initialize()
            await self.start_websocket()
            
            # websocketが終了した
            
            # アプリケーションを実行し続ける
            #while True:
            #    await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        finally:
            if self.mattermost_client:
                self.mattermost_client.close()
        
async def start():
    params = {
        "calculator": {
            "command": "uv",
            "args": [
                "run",
                "--directory",
                "E:\\repository\\langchain-prebuilt-agent",
                "mcp_math.py"
            ],
            "transport": "stdio",
        },
    }
    client = MultiServerMCPClient(params)
    tools = await client.get_tools()
    llm = get_llm(config.DEFAULT_PROVIDER)
    bot = MattermostLLMBot(llm, tools)
    await bot.run()

def main():
    asyncio.run(start())

if __name__ == "__main__":
    main()
