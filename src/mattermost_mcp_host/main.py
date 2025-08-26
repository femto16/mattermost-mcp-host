from mattermost_mcp_host.bot.mattermost_mcp_bot import MattermostMCPBot
import asyncio

async def start():
    integration = MattermostMCPBot()
    await integration.run()

def main():
    asyncio.run(start())

if __name__ == "__main__":
    main()
