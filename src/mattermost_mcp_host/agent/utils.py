from typing import Dict, List, Any
import json
import logging
import traceback
from langchain.schema import BaseMessage, AIMessage, HumanMessage
from langchain_core.messages import ToolMessage
from mattermostdriver import Driver

logger = logging.getLogger(__name__)


def get_final_response(messages: List[BaseMessage], last_user_message: str = None) -> str:
    """Extract the final response from the messages.
    
    Args:
        messages: The messages from the agent run
        
    Returns:
        The final response as a string
    """
    
    messages_to_send = []
    tool_call_messages = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            # ツール呼び出しのnameとargsを抽出。resultはToolMessageで処理するため、一度tool_call_messageへ格納
            if hasattr(msg, 'lc_attributes') and msg.lc_attributes != {} and msg.content == "":
                tool_calls = msg.lc_attributes.get('tool_calls', [])
                for tool_call in tool_calls:
                    if tool_call.get('type') == 'tool_call':
                        tool_call_message = f"Called tool: **{tool_call.get('name')}**"
                        if tool_call.get('args') != {}:
                            tool_call_message +=  f"\n~~~{{.json linenums=false}}\n{json.dumps(tool_call.get('args'), indent=2, ensure_ascii=False)}\n~~~" 
                    tool_call_messages.append(tool_call_message)
            else:
                # 通常のメッセージ
                messages_to_send.append(msg.content)
        if isinstance(msg, ToolMessage):
            # ツールの結果を直前のツール呼び出しと組み合わせて追加
            tool_result_message = tool_call_messages[0] + f"\nResult: **{msg.content}** ({msg.status})"
            messages_to_send.append(tool_result_message)
            tool_call_messages = tool_call_messages[1:]  # 先頭のtool_callメッセージを削除
        elif isinstance(msg, HumanMessage) and msg.content == last_user_message:
            # ユーザーメッセージだったらそれ以降のメッセージのみ抽出させるため、リセット
            messages_to_send = []
            
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
    
def add_reaction(driver: Driver, post_id, emoji_name="thumbsup") -> List[Dict[str, Any]]:
    driver.reactions.create_reaction({
        "user_id": driver.client.userid,
        "post_id": post_id,
        "emoji_name": emoji_name
    })
    return True