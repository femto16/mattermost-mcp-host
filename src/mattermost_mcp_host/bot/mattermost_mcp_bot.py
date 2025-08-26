from mattermost_mcp_host.mcp_client import MCPClient
from mattermost_mcp_host.mattermost_client import MattermostClient
import mattermost_mcp_host.config as config
from mattermost_mcp_host.agent import LangGraphAgent
from mattermost_mcp_host.bot.mattermost_base_bot import MattermostBaseBot

import sys
import asyncio
import logging
import json
from pathlib import Path

# 以下のインポートを追加
from typing import Dict, List, Any
import traceback

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

# ロギング設定
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_server_configs():
    """mcp-servers.jsonからMCPサーバー設定を読み込み"""
    try:
        config_path = Path(__file__).parent / "mcp-servers.json"
        with open(config_path) as f:
            config = json.load(f)
            return config.get("mcpServers", {})
    except Exception as e:
        logger.error(f"Error loading server configurations: {str(e)}")
        return {}

class MattermostMCPBot(MattermostBaseBot):
    """Mattermost MCPボット(オリジナル)"""
    def __init__(self):
        super().__init__()
        self.mcp_clients = {}  # 複数のMCPクライアントを格納するdict
        self.command_prefix = config.COMMAND_PREFIX
        
    async def initialize(self):
        """Mattermostクライアントを初期化し、Websocket経由で接続"""
        
        try:
            # MCPサーバー設定のロード
            server_configs = load_server_configs()
            logger.info(f"Found {len(server_configs)} MCP servers in config")
            
            all_langchain_tools = []
            # 各MCPクライアントの初期化
            for server_name, server_config in server_configs.items():
                try:
                    client = MCPClient(server_config=server_config)

                    await client.connect()
                    self.mcp_clients[server_name] = client
                    lanchain_tools = await client.convert_mcp_tools_to_langchain()
                    all_langchain_tools.extend(lanchain_tools)
                    logger.info(f"Connected to MCP server '{server_name}' via stdio")
                except Exception as e:
                    logger.error(f"Failed to connect to MCP server '{server_name}': {str(e)}")
                    # 1つが失敗しても他のサーバーで続行
                    continue
            
            if not self.mcp_clients:
                raise ValueError("No MCP servers could be connected")

        except Exception as e:
            logger.error(f"Failed to initialize MCP servers: {str(e)}")
            raise
        
        # エージェントツールのセットアップ
        logger.info(f"Setting up agent with {all_langchain_tools} tools")
        logger.info(f"Number of tools : {len(all_langchain_tools)}")

        # 設定に基づいたエージェントの初期化
        if config.AGENT_TYPE.lower() == 'simple':
            system_prompt = config.DEFAULT_SYSTEM_PROMPT
            name = 'simple'
            
        elif config.AGENT_TYPE.lower() == 'github':
            name = 'github'
            system_prompt = config.GITHUB_AGENT_SYSTEM_PROMPT

        self.agent = LangGraphAgent(name=name, 
                                    provider=config.DEFAULT_PROVIDER, 
                                    model=config.DEFAULT_MODEL, 
                                    tools=all_langchain_tools, 
                                    system_prompt=system_prompt)

        await super().initialize()
        
    async def get_thread_history(self, root_id=None, channel_id=None) -> List[Dict[str, Any]]:
        """
        Mattermostスレッドから会話履歴を取得
        
        Args:
            root_id: スレッドのルート投稿のID
            channel_id: スレッドが存在するチャンネルID
            
        Returns:
            LLM用にフォーマットされたメッセージのリスト
        """
        if not root_id or not channel_id:
            # スレッドがない場合は空の履歴を返す
            return []
            
        try:
            # スレッド内の投稿を取得
            posts_response = self.mattermost_client.driver.posts.get_thread(root_id)
            if not posts_response or 'posts' not in posts_response:
                return []
                
            # create_atで投稿をソートし、時系列順を維持
            posts = posts_response['posts']
            ordered_posts = sorted(posts.values(), key=lambda x: x['create_at'])
            
            # LLMメッセージ形式に変換
            messages = []
            bot_user_id = self.mattermost_client.driver.client.userid
            
            for post in ordered_posts:
                # システムメッセージはスキップ
                if post.get('type') == 'system_join_channel':
                    continue
                    
                content = post.get('message', '')
                user_id = post.get('user_id')
                
                # 空のメッセージはスキップ
                if not content:
                    continue
                    
                # 送信者に基づいてロールを決定
                role = "assistant" if user_id == bot_user_id else "user"
                
                # LLM形式でメッセージに追加
                messages.append({
                    "role": role,
                    "content": content
                })
                
            return messages
            
        except Exception as e:
            logger.error(f"Error fetching thread history: {str(e)}")
            logger.error(traceback.format_exc())
            return []

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
            # スレッド履歴の取得 - post_idが存在する場合、それが新しいスレッドのルート
            root_id = post_id if root_id is None or root_id == "" else root_id
            logger.info(f"Fetching thread history for root_id: {root_id}")
            
            # タイピングインジケーターの送信
            # await self.send_response(channel_id, "Processing your request...", root_id)
            
            # 接続されているすべてのMCPサーバーから利用可能なツールを収集
            all_tools = {}
            for server_name, client in self.mcp_clients.items():
                try:
                    server_tools = await client.list_tools()
                    # 競合を避けるためにツール名にサーバー名のプレフィックスを追加
                    prefixed_tools = {
                        f"{server_name}.{name}": tool 
                        for name, tool in server_tools.items()
                    }
                    all_tools.update(prefixed_tools)
                except Exception as e:
                    logger.error(f"Error getting tools from {server_name}: {str(e)}")
            
            # スレッド履歴の取得（新しい会話の場合は空）
            thread_history = await self.get_thread_history(root_id, channel_id)
            
            # エージェント用のメッセージをフォーマット
            # エージェントはクエリ、履歴、user_idを期待
            logger.info(f"Running agent with message: {message}")
            
            # ユーザーのメッセージ、スレッド履歴、ユーザーIDでエージェントを実行
            # 適切なメモリ管理のためにスレッド履歴とユーザーIDをエージェントに渡す
            result = await self.agent.run(
                query=message,
                history=thread_history,
                user_id=user_id,
                metadata={
                    "channel_id": channel_id,
                    "team_name": config.MATTERMOST_TEAM_NAME.lower().replace(" ", "-"),
                    "channel_name": config.MATTERMOST_CHANNEL_NAME.lower().replace(" ", "-"),
                    #"github_username": config.GITHUB_USERNAME,
                    "github_repo": config.GITHUB_REPO_NAME,
                }
            )
            
            # エージェントのメッセージから最終応答を抽出
            responses = self.agent.extract_response(result["messages"])
            logger.info(f"Agent response: {responses}")
            previous_agent_responses = [msg["content"] for msg in thread_history if msg["role"] == "assistant"]
            
            # 重複を避けるために以前のエージェントの応答を除外
            for response in responses:
                if response not in previous_agent_responses:
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
                
            elif subcommand == 'call':
                if len(command_parts) < 4:
                    await self.send_response(
                        channel_id,
                        f"Invalid call command. Use {self.command_prefix}{server_name} call <tool_name> [parameter_name] [value]",
                        root_id
                    )
                    return
                    
                tool_name = command_parts[2]
                # パラメータのないツールの処理
                if len(command_parts) == 4:
                    tool_args = {}
                    logger.info(f"Calling tool {tool_name} with no parameters")
                else:
                    # JSONが提供されている場合はそれをパース
                    try:
                        # 残りの部分を結合してJSONとしてパース
                        params_str = " ".join(command_parts[3:]).replace("'", '')
                        
                        tool_args = json.loads(params_str)
                        logger.info(f"Calling tool {tool_name} with JSON inputs: {tool_args}")
                    except json.JSONDecodeError:
                        # 古いparameter_name value形式へのフォールバック
                        parameter_name = command_parts[3]
                        parameter_value = " ".join(command_parts[4:]) if len(command_parts) > 4 else ""
                        tool_args = {parameter_name: parameter_value}
                        logger.info(f"Calling tool {tool_name} with key-value inputs: {tool_args}")
                
                try:
                    result = await client.call_tool(tool_name, tool_args)
                    await self.send_response(channel_id, f"Tool result from {server_name}: {result}", root_id)
                    # result.textをマークダウンとして送信
                    if hasattr(result, 'content') and result.content:
                        if hasattr(result.content[0], 'text'):
                            await self.send_response(channel_id, result.content[0].text, root_id)
                except Exception as e:
                    logger.error(f"Error calling tool {tool_name} on {server_name}: {str(e)}")
                    await self.send_response(channel_id, f"Error calling tool {tool_name} on {server_name}: {str(e)}", root_id)
                    
            elif subcommand == 'resources':
                # 正しいクライアントインスタンスを使用
                resources = await client.list_resources()
                response = "Available MCP resources:\n"
                for resource in resources:
                    response += f"- {resource}\n"
                await self.send_response(channel_id, response, root_id)
                
            elif subcommand == 'prompts':
                # 正しいクライアントインスタンスを使用
                prompts = await client.list_prompts()
                response = "Available MCP prompts:\n"
                for prompt in prompts:
                    response += f"- {prompt}\n"
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
                2. `{self.command_prefix}<server_name> call <tool_name> <parameter_name> <value>` - 特定のツールを呼び出し
                3. `{self.command_prefix}<server_name> resources` - 利用可能なすべてのリソースを一覧表示
                4. `{self.command_prefix}<server_name> prompts` - 利用可能なすべてのプロンプトを一覧表示

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
            # 初期化の逆の順序でクライアントを閉じる
            if self.mattermost_client:
                self.mattermost_client.close()
            for client in self.mcp_clients.values():
                await client.close()
        
async def start():
    integration = MattermostMCPBot()
    await integration.run()

def main():
    asyncio.run(start())

if __name__ == "__main__":
    main()
