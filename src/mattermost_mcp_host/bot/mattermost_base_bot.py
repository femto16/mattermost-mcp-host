from mattermost_mcp_host.mattermost_client import MattermostClient
import mattermost_mcp_host.config as config

import json
import asyncio
import logging
import traceback

import nest_asyncio
nest_asyncio.apply()

# ロギングの設定
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MattermostBaseBot:
    """Mattermost Botベースクラス"""
    def __init__(self):
        self.mattermost_client = None
        self.channel_id = config.MATTERMOST_CHANNEL_ID

    async def initialize(self):
        # Mattermostクライアントを初期化する
        try:
            self.mattermost_client = MattermostClient(
                url=config.MATTERMOST_URL,
                token=config.MATTERMOST_TOKEN,
                scheme=config.MATTERMOST_SCHEME,
                port=config.MATTERMOST_PORT
            )
            self.mattermost_client.connect()
            logger.info("Connected to Mattermost server")
        except Exception as e:
            logger.error(f"Failed to connect to Mattermost server: {str(e)}")
            raise
        
        # チャンネルが存在することを確認するために、常にチャンネルIDを取得しようとする
        try:
            teams = self.mattermost_client.get_teams()
            logger.info(f"Available teams: {teams}")
            if teams:  # チームが存在する場合にのみチャンネルを取得しようとする
                team_id = next(team['id'] for team in teams if team['name'] == config.MATTERMOST_TEAM_NAME)
                channel = self.mattermost_client.get_channel_by_name(config.MATTERMOST_TEAM_NAME, config.MATTERMOST_CHANNEL_NAME)
                if not self.channel_id:
                    self.channel_id = channel['id']
                logger.info(f"Using channel ID: {self.channel_id}")
        except Exception as e:
            logger.warning(f"Channel verification failed: {str(e)}. Using configured channel ID: {self.channel_id}")
            # 例外を発生させず、設定されたチャンネルIDで続行する
        
        if not self.channel_id:
            raise ValueError("No channel ID available. Please configure MATTERMOST_CHANNEL_ID or ensure team/channel exist")
        
        # メッセージハンドラを設定
        self.mattermost_client.add_message_handler(self.handle_message)

    async def start_websocket(self):
        """MattermostのWebSocket接続を開始"""
        logger.info(f"Listening for commands in channel {self.channel_id}")
        if self.mattermost_client:
            await self.mattermost_client.start_websocket()
        else:
            raise RuntimeError("Mattermost client is not initialized")

    async def handle_message(self, post):
        """Mattermostからの受信メッセージを処理"""
        try:
            logger.info(f"Received post: {json.dumps(post, indent=2)}")
            
            # ボット自身からのメッセージはスキップ
            if post.get('user_id') == self.mattermost_client.driver.client.userid:
                return
            
            # メッセージデータを抽出
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
            
            # オウム返しで応答
            user = self.mattermost_client.driver.users.get_user(user_id)
            response = f"Hello, @{user['username']}!\nYour message: {message}"
            await self.send_response(channel_id, response, root_id)
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            logger.error(traceback.format_exc())
        

    async def handle_command(self, channel_id, message_text, user_id, post_id=None, root_id=None):
        """Mattermostからのコマンドメッセージを処理"""
        logger.info(f"Handling command: {message_text=}, {user_id=}, {channel_id=}, {post_id=} {root_id=}")

    async def send_response(self, channel_id, message, root_id=None):
        """Mattermostチャンネルに応答を送信"""
        if channel_id is None:
            logger.warning(f"Channel id is not sent, using default channel - {self.channel_id}")
            channel_id = self.channel_id
        self.mattermost_client.post_message(channel_id, message, root_id)

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

async def start():
    integration = MattermostBaseBot()
    await integration.run()

def main():
    asyncio.run(start())
    

if __name__ == "__main__":
    main()

