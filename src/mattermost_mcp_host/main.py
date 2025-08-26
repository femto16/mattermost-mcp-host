from mattermost_mcp_host.bot.mattermost_mcp_bot_original import MattermostMCPBotOriginal
import asyncio

async def start():
    integration = MattermostMCPBotOriginal()
    await integration.run()

def main():
    asyncio.run(start())

if __name__ == "__main__":
    main()
