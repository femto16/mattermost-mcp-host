from mattermost_mcp_host.mattermost_client import MattermostClient
import mattermost_mcp_host.config as config

import json
import asyncio
import logging
import traceback

import nest_asyncio
nest_asyncio.apply()

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MattermostBaseBot:
    """Base class for Mattermost MCP integrations."""
    def __init__(self):
        self.mattermost_client = None
        self.channel_id = config.MATTERMOST_CHANNEL_ID

    async def initialize(self):
        # Initialize Mattermost client
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
        
        # Always try to get channel ID to verify it exists
        try:
            teams = self.mattermost_client.get_teams()
            logger.info(f"Available teams: {teams}")
            if teams:  # Only try to get channel if teams exist
                team_id = next(team['id'] for team in teams if team['name'] == config.MATTERMOST_TEAM_NAME)
                #channel = self.mattermost_client.get_channel_by_name(team_id, config.MATTERMOST_CHANNEL_NAME)
                channel = self.mattermost_client.get_channel_by_name(config.MATTERMOST_TEAM_NAME, config.MATTERMOST_CHANNEL_NAME)
                if not self.channel_id:
                    self.channel_id = channel['id']
                logger.info(f"Using channel ID: {self.channel_id}")
        except Exception as e:
            logger.warning(f"Channel verification failed: {str(e)}. Using configured channel ID: {self.channel_id}")
            # Don't raise the exception, continue with the configured channel ID
        
        if not self.channel_id:
            raise ValueError("No channel ID available. Please configure MATTERMOST_CHANNEL_ID or ensure team/channel exist")
        
        
        # Set up message handler
        self.mattermost_client.add_message_handler(self.handle_message)
        logger.info(f"Listening for commands in channel {self.channel_id}")
        await self.mattermost_client.start_websocket()

    async def handle_message(self, post):
        """Handle incoming messages from Mattermost"""
        try:
            logger.info(f"Received post: {json.dumps(post, indent=2)}")  # Better logging
            
            # Skip messages from the bot itself
            if post.get('user_id') == self.mattermost_client.driver.client.userid:
                return
            
            # Extract message data
            channel_id = post.get('channel_id')
            message = post.get('message', '')
            user_id = post.get('user_id')
            post_id = post.get('id') 
            root_id = post.get('root_id')
            if root_id == '':
                root_id = post_id
            
            # Skip messages from other channels if a specific channel is configured
            if self.channel_id and channel_id != self.channel_id:
                logger.info(f'Received message from a different channel - {channel_id} than configured - {self.channel_id}')
                # Only process direct messages to the bot and messages in the configured channel
                # if not any(team_member.get('mention_keys', []) in message for team_member in self.mattermost_client.driver.users.get_user_teams(user_id)):
                #     return
            
            user = self.mattermost_client.driver.users.get_user(user_id)
            response = f"Hello, @{user['username']}!\nYour message: {message}"
            await self.send_response(channel_id, response, root_id)
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            logger.error(traceback.format_exc())
        

    async def handle_command(self, channel_id, message_text, user_id, post_id=None, root_id=None):
        """Handle command messages from Mattermost."""
        logger.info(f"Handling command: {message_text=}, {user_id=}, {channel_id=}, {post_id=} {root_id=}")

    async def send_response(self, channel_id, message, root_id=None):
        """Send a response to the Mattermost channel"""
        if channel_id is None:
            logger.warning(f"Channel id is not sent, using default channel - {self.channel_id}")
            channel_id = self.channel_id
        self.mattermost_client.post_message(channel_id, message, root_id)

    async def run(self):
        """Run the integration"""
        try:
            await self.initialize()
            
            # Keep the application running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        finally:
            # Close clients in reverse order of initialization
            if self.mattermost_client:
                self.mattermost_client.close()

async def start():
    integration = MattermostBaseBot()
    await integration.run()

def main():
    asyncio.run(start())
    

if __name__ == "__main__":
    main()
