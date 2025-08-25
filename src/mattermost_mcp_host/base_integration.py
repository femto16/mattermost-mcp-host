from abc import ABC, abstractmethod

class BaseIntegration(ABC):
    """Base class for Mattermost MCP integrations."""

    @abstractmethod
    async def handle_message(self, post):
        """Handle incoming messages from Mattermost."""
        raise NotImplementedError

    @abstractmethod
    async def handle_command(self, channel_id, message_text, user_id, post_id=None, root_id=None):
        """Handle command messages from Mattermost."""
        raise NotImplementedError
