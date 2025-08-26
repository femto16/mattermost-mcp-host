from typing import Dict, List, Any
import logging
import traceback
from langchain.schema import BaseMessage, AIMessage

logger = logging.getLogger(__name__)


def get_final_response(messages: List[BaseMessage]) -> str:
    """Extract the final response from the messages.
    
    Args:
        messages: The messages from the agent run
        
    Returns:
        The final response as a string
    """
    
    messages_to_send = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            if hasattr(msg, 'additional_kwargs') and msg.additional_kwargs != {} and msg.content == "":
                tool_calls = msg.additional_kwargs.get('tool_calls', [])
                for tool_call in tool_calls:
                    if tool_call.get('type') == 'function':
                        tool_call_message = f"Called tool: {tool_call.get('function', {}).get('name')} with arguments: {tool_call.get('function', {}).get('arguments')}"
                    messages_to_send.append(tool_call_message)
            else:
                messages_to_send.append(msg.content)
            
    return messages_to_send
    # ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
    
    # # Return the content of the last AI message
    # if ai_messages:
    #     return ai_messages[-1].content
    
    # return "No response generated."
    
async def get_thread_history(driver, root_id=None, channel_id=None) -> List[Dict[str, Any]]:
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
        posts_response = driver.posts.get_thread(root_id)
        if not posts_response or 'posts' not in posts_response:
            return []
            
        # create_atで投稿をソートし、時系列順を維持
        posts = posts_response['posts']
        ordered_posts = sorted(posts.values(), key=lambda x: x['create_at'])
        
        # LLMメッセージ形式に変換
        messages = []
        bot_user_id = driver.client.userid
        
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