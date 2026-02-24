"""MCP tools for Google Chat read state and unread messages management.

This module provides MCP tools for managing message read states in Google Chat,
including getting unread messages, listing conversations with unread messages,
finding DMs with users, and marking spaces as read.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.providers.google_chat.api.read_state import (
    get_space_read_state,
    get_thread_read_state,
    update_space_read_state,
    find_direct_message_space,
)
from src.providers.google_chat.api.spaces import list_chat_spaces
from src.providers.google_chat.api.messages import list_space_messages
from src.providers.google_chat.mcp_instance import mcp, tool

logger = logging.getLogger("read_state_tools")


def _parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string to a datetime object.

    Args:
        timestamp_str: ISO 8601 timestamp string

    Returns:
        datetime object or None if parsing fails
    """
    if not timestamp_str:
        return None

    try:
        # Handle various ISO 8601 formats
        timestamp_str = timestamp_str.replace('Z', '+00:00')
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, AttributeError):
        logger.warning(f"Failed to parse timestamp: {timestamp_str}")
        return None


@tool()
async def get_unread_messages_tool(
    space_name: str,
    include_sender_info: bool = True,
    max_results: int = 50
) -> dict:
    """Get unread messages from a specific Google Chat space.

    Retrieves messages that have been posted to a space since the user last
    read it. This tool compares message timestamps against the space's
    lastReadTime to identify which messages are unread.

    This tool requires OAuth authentication with the chat.users.readstate.readonly
    or chat.users.readstate scope.

    COMMON USE CASES:
    - Check for new messages in a specific space without manually comparing timestamps
    - Get a summary of what you've missed since last reading a conversation
    - Monitor high-priority spaces for new activity

    Args:
        space_name: The resource name of the space to check for unread messages.
                   Format: 'spaces/{space_id}' (e.g., 'spaces/AAQAXL5fJxI')

                   IMPORTANT: You can get space IDs using the get_chat_spaces_tool.

        include_sender_info: Whether to include detailed sender information for
                            each message. When true, each message will include
                            sender details like email and display name.
                            (default: True)

        max_results: Maximum number of unread messages to return (default: 50).
                    Higher values may impact performance. Limit: 1000.

                    USAGE STRATEGY:
                    - 10-25: Quick check for recent unread messages
                    - 50-100: Comprehensive view of unread activity
                    - 100+: Full catch-up for spaces with lots of activity

    Returns:
        Dictionary containing:
        - space_name: The resource name of the space
        - space_display_name: The display name of the space (if available)
        - last_read_time: ISO 8601 timestamp of when the space was last read
        - unread_count: Number of unread messages found
        - messages: List of unread message objects, each with:
          - name: Resource name of the message
          - text: Message content
          - sender: Information about who sent the message
          - createTime: When the message was created
          - thread: Thread information if applicable
          - sender_info: Additional sender details if include_sender_info=True
        - has_more: Boolean indicating if there are more unread messages beyond max_results

    Raises:
        Exception: If authentication fails or API calls fail

    Examples:

    1. Get unread messages from a space:
       ```python
       unread = get_unread_messages_tool(
           space_name="spaces/AAQAXL5fJxI"
       )
       print(f"You have {unread['unread_count']} unread messages")
       ```

    2. Get unread messages with sender details:
       ```python
       unread = get_unread_messages_tool(
           space_name="spaces/AAQAXL5fJxI",
           include_sender_info=True,
           max_results=25
       )
       for msg in unread['messages']:
           sender = msg.get('sender_info', {}).get('display_name', 'Unknown')
           print(f"{sender}: {msg['text'][:50]}...")
       ```

    3. Check for unread messages across multiple spaces:
       ```python
       spaces = get_chat_spaces_tool()
       for space in spaces:
           unread = get_unread_messages_tool(
               space_name=space['name'],
               max_results=10
           )
           if unread['unread_count'] > 0:
               print(f"{space['displayName']}: {unread['unread_count']} unread")
       ```

    API References:
        - https://developers.google.com/workspace/chat/api/reference/rest/v1/users.spaces/getSpaceReadState
        - https://developers.google.com/workspace/chat/api/reference/rest/v1/spaces.messages/list
    """
    # Normalize space name
    if not space_name.startswith('spaces/'):
        space_name = f"spaces/{space_name}"

    # Get the read state for this space
    read_state = await get_space_read_state(space_name)
    last_read_time = read_state.get('lastReadTime')

    if not last_read_time:
        logger.warning(f"No lastReadTime found for space {space_name}")
        last_read_time = "1970-01-01T00:00:00.000Z"

    last_read_dt = _parse_timestamp(last_read_time)

    # List messages from the space
    messages_result = await list_space_messages(
        space_name=space_name,
        include_sender_info=include_sender_info,
        page_size=max_results,
        order_by="createTime desc"  # Newest first
    )

    all_messages = messages_result.get('messages', [])

    # Filter messages that are unread (createTime > lastReadTime)
    unread_messages = []
    for message in all_messages:
        create_time = message.get('createTime')
        if create_time:
            create_dt = _parse_timestamp(create_time)
            if create_dt and last_read_dt:
                if create_dt > last_read_dt:
                    unread_messages.append(message)

    # Check if there might be more unread messages
    has_more = len(all_messages) >= max_results and len(unread_messages) == max_results

    # Get space display name from first message if available
    space_display_name = None
    if all_messages:
        space_info = all_messages[0].get('space', {})
        space_display_name = space_info.get('displayName')

    return {
        "space_name": space_name,
        "space_display_name": space_display_name,
        "last_read_time": last_read_time,
        "unread_count": len(unread_messages),
        "messages": unread_messages,
        "has_more": has_more
    }


@tool()
async def get_unread_conversations_tool(
    include_dms: bool = True,
    include_spaces: bool = True,
    max_results: int = 20
) -> dict:
    """List all conversations (spaces and DMs) with unread messages.

    Scans all accessible spaces and identifies those with unread messages.
    This is useful for getting an overview of all conversations that need
    your attention without checking each one individually.

    This tool requires OAuth authentication with the chat.users.readstate.readonly
    or chat.users.readstate scope.

    COMMON USE CASES:
    - Get a daily digest of all conversations needing attention
    - Identify which spaces have new activity since you last checked
    - Prioritize which conversations to read first based on unread count

    PERFORMANCE NOTE: This tool makes multiple API calls (one per space to get
    read state and check for messages), so it may take several seconds for
    accounts with many spaces.

    Args:
        include_dms: Whether to include direct message conversations in the
                    results (default: True)
        include_spaces: Whether to include regular spaces (rooms) in the
                       results (default: True)
        max_results: Maximum number of conversations with unread messages to
                    return (default: 20). This limits the result set, not the
                    number of spaces scanned.

    Returns:
        Dictionary containing:
        - total_spaces_scanned: Total number of spaces checked
        - conversations_with_unread: Number of spaces with unread messages
        - conversations: List of conversation summaries, each with:
          - space_name: Resource name of the space
          - display_name: Display name of the space
          - space_type: Type of space ("DIRECT_MESSAGE", "GROUP_CHAT", or "SPACE")
          - last_read_time: When the user last read this space
          - unread_count: Estimated number of unread messages
          - latest_message_time: Timestamp of the most recent message
          - preview: Snippet of the latest unread message (if available)

    Raises:
        Exception: If authentication fails or API calls fail

    Examples:

    1. Get all conversations with unread messages:
       ```python
       result = get_unread_conversations_tool()
       for conv in result['conversations']:
           print(f"{conv['display_name']}: {conv['unread_count']} unread")
       ```

    2. Get only spaces (excluding DMs) with unread messages:
       ```python
       result = get_unread_conversations_tool(
           include_dms=False,
           include_spaces=True
       )
       ```

    3. Get a quick overview of top priority conversations:
       ```python
       result = get_unread_conversations_tool(max_results=5)
       if result['conversations_with_unread'] > 0:
           print(f"You have unread messages in {result['conversations_with_unread']} conversations")
       ```

    API References:
        - https://developers.google.com/workspace/chat/api/reference/rest/v1/spaces/list
        - https://developers.google.com/workspace/chat/api/reference/rest/v1/users.spaces/getSpaceReadState
        - https://developers.google.com/workspace/chat/api/reference/rest/v1/spaces.messages/list
    """
    # List all spaces
    all_spaces = await list_chat_spaces()
    logger.info(f"Scanning {len(all_spaces)} spaces for unread messages")

    conversations_with_unread = []
    total_scanned = 0

    for space in all_spaces:
        space_name = space.get('name', '')
        space_type = space.get('spaceType', 'SPACE')
        display_name = space.get('displayName', 'Unnamed Space')

        # Skip based on filter settings
        if space_type == 'DIRECT_MESSAGE' and not include_dms:
            continue
        if space_type != 'DIRECT_MESSAGE' and not include_spaces:
            continue

        total_scanned += 1

        try:
            # Get read state for this space
            read_state = await get_space_read_state(space_name)
            last_read_time = read_state.get('lastReadTime')

            if not last_read_time:
                # If no read state, treat all messages as unread
                last_read_time = "1970-01-01T00:00:00.000Z"

            last_read_dt = _parse_timestamp(last_read_time)

            # Get recent messages (limit to 20 for performance)
            messages_result = await list_space_messages(
                space_name=space_name,
                include_sender_info=False,
                page_size=20,
                order_by="createTime desc"
            )

            messages = messages_result.get('messages', [])

            # Count unread messages
            unread_count = 0
            latest_message_time = None
            latest_message_preview = None

            for message in messages:
                create_time = message.get('createTime')
                if create_time:
                    create_dt = _parse_timestamp(create_time)
                    if create_dt and last_read_dt:
                        if create_dt > last_read_dt:
                            unread_count += 1
                            if latest_message_time is None:
                                latest_message_time = create_time
                                text = message.get('text', '')
                                if text:
                                    latest_message_preview = text[:100] + ('...' if len(text) > 100 else '')

            # Only include if there are unread messages
            if unread_count > 0:
                conversations_with_unread.append({
                    "space_name": space_name,
                    "display_name": display_name,
                    "space_type": space_type,
                    "last_read_time": last_read_time,
                    "unread_count": unread_count,
                    "latest_message_time": latest_message_time,
                    "preview": latest_message_preview
                })

        except Exception as e:
            logger.warning(f"Failed to check read state for {space_name}: {str(e)}")
            continue

    # Sort by unread count (descending) and limit results
    conversations_with_unread.sort(key=lambda x: x['unread_count'], reverse=True)
    conversations_with_unread = conversations_with_unread[:max_results]

    return {
        "total_spaces_scanned": total_scanned,
        "conversations_with_unread": len(conversations_with_unread),
        "conversations": conversations_with_unread
    }


@tool()
async def find_dm_with_user_tool(user_email: str) -> dict:
    """Find the direct message (DM) space with a specific user.

    Locates the 1:1 direct message space between you and the specified user.
    This is useful when you want to send a DM to someone but don't know the
    space ID.

    This tool requires OAuth authentication with the chat.spaces.readonly or
    chat.spaces scope.

    COMMON USE CASES:
    - Find the DM space with a colleague before sending a message
    - Check for unread messages in a specific 1:1 conversation
    - Get the space ID needed for other DM operations

    Args:
        user_email: The email address of the user to find the DM with.
                   Format: 'user@example.com'

                   IMPORTANT: The user must be in your organization's
                   Google Workspace directory or have previously interacted
                   with you in Chat.

    Returns:
        Dictionary containing the DM space information:
        - name: Resource name of the space (e.g., 'spaces/AAQAXL5fJxI')
        - type: Always "DIRECT_MESSAGE" for DMs
        - display_name: Display name (usually the other user's name)
        - space_type: Type classification ("DIRECT_MESSAGE")
        - single_user_bot_dm: Whether this is a DM with a bot (boolean)
        - Other space properties as available

    Raises:
        Exception: If authentication fails, the DM doesn't exist yet,
                  or the API call fails

    Examples:

    1. Find DM space with a colleague:
       ```python
       dm = find_dm_with_user_tool(
           user_email="colleague@company.com"
       )
       print(f"DM space ID: {dm['name']}")
       ```

    2. Find DM and check for unread messages:
       ```python
       dm = find_dm_with_user_tool(user_email="boss@company.com")
       unread = get_unread_messages_tool(
           space_name=dm['name'],
           max_results=10
       )
       print(f"Unread messages: {unread['unread_count']}")
       ```

    3. Find DM and send a message:
       ```python
       dm = find_dm_with_user_tool(user_email="teammate@company.com")
       send_message_tool(
           space_name=dm['name'],
           text="Hey, quick question..."
       )
       ```

    API Reference:
        https://developers.google.com/workspace/chat/api/reference/rest/v1/spaces/findDirectMessage
    """
    result = await find_direct_message_space(user_email)

    # Add a friendly space_type field for consistency
    result['space_type'] = result.get('spaceType', 'DIRECT_MESSAGE')

    return result


@tool()
async def mark_space_as_read_tool(space_name: str) -> dict:
    """Mark all messages in a space as read.

    Updates the space read state to the current time, effectively marking
    all messages up to now as read. This is useful for clearing notifications
    or acknowledging that you've caught up on a conversation.

    This tool requires OAuth authentication with the chat.users.readstate scope.
    The readonly scope is not sufficient for this operation.

    COMMON USE CASES:
    - Clear notifications after catching up on a long conversation
    - Mark a space as read after reviewing messages via other tools
    - Reset the unread counter for a space you don't need to respond to

    Args:
        space_name: The resource name of the space to mark as read.
                   Format: 'spaces/{space_id}' (e.g., 'spaces/AAQAXL5fJxI')

                   Can also be just the ID portion ('AAQAXL5fJxI'),
                   which will be automatically prefixed with 'spaces/'.

                   IMPORTANT: You can get space IDs using the get_chat_spaces_tool.

    Returns:
        Dictionary containing the updated read state:
        - space_name: The resource name of the space
        - last_read_time: The new ISO 8601 timestamp marking the read position
        - success: Boolean indicating the operation succeeded

    Raises:
        Exception: If authentication fails, insufficient permissions,
                  or the API call fails

    Examples:

    1. Mark a space as read:
       ```python
       result = mark_space_as_read_tool(
           space_name="spaces/AAQAXL5fJxI"
       )
       print(f"Marked as read at: {result['last_read_time']}")
       ```

    2. Get unread count, review messages, then mark as read:
       ```python
       # Check for unread messages
       unread = get_unread_messages_tool(
           space_name="spaces/AAQAXL5fJxI"
       )

       if unread['unread_count'] > 0:
           # Review the messages...
           for msg in unread['messages']:
               print(f"{msg['text']}")

           # Mark as read
           mark_space_as_read_tool(
               space_name="spaces/AAQAXL5fJxI"
           )
       ```

    3. Mark all spaces with many unread messages as read:
       ```python
       result = get_unread_conversations_tool()
       for conv in result['conversations']:
           if conv['unread_count'] > 50:
               mark_space_as_read_tool(
                   space_name=conv['space_name']
               )
       ```

    API Reference:
        https://developers.google.com/workspace/chat/api/reference/rest/v1/users.spaces/updateSpaceReadState
    """
    # Normalize space name
    if not space_name.startswith('spaces/'):
        space_name = f"spaces/{space_name}"

    # Update the read state to current time
    result = await update_space_read_state(space_name)

    return {
        "space_name": space_name,
        "last_read_time": result.get('lastReadTime'),
        "success": True
    }


@tool()
async def get_space_read_state_tool(space_name: str) -> dict:
    """Get the read state of a space.

    Retrieves the last read time for a specific space, showing when you
    last read messages in that space. This can be used to check your
    "read position" in a conversation without retrieving messages.

    This tool requires OAuth authentication with the chat.users.readstate.readonly
    or chat.users.readstate scope.

    COMMON USE CASES:
    - Check when you last read a specific space
    - Compare read states between different spaces
    - Determine if you might have missed messages based on last read time

    Args:
        space_name: The resource name of the space to get read state for.
                   Format: 'spaces/{space_id}' (e.g., 'spaces/AAQAXL5fJxI')

                   Can also be just the ID portion ('AAQAXL5fJxI'),
                   which will be automatically prefixed with 'spaces/'.

    Returns:
        Dictionary containing the read state:
        - name: Full resource name of the read state
        - space_name: The space resource name
        - last_read_time: ISO 8601 timestamp of last read position
        - formatted_last_read: Human-readable last read time

    Raises:
        Exception: If authentication fails or the API call fails

    Examples:

    1. Get read state for a space:
       ```python
       state = get_space_read_state_tool(
           space_name="spaces/AAQAXL5fJxI"
       )
       print(f"Last read: {state['formatted_last_read']}")
       ```

    2. Check read states across all spaces:
       ```python
       spaces = get_chat_spaces_tool()
       for space in spaces:
           try:
               state = get_space_read_state_tool(space['name'])
               print(f"{space['displayName']}: {state['formatted_last_read']}")
           except:
               print(f"{space['displayName']}: Never read")
       ```

    API Reference:
        https://developers.google.com/workspace/chat/api/reference/rest/v1/users.spaces/getSpaceReadState
    """
    # Normalize space name
    if not space_name.startswith('spaces/'):
        space_name = f"spaces/{space_name}"

    # Get the read state
    result = await get_space_read_state(space_name)

    last_read_time = result.get('lastReadTime', '')

    # Format the timestamp for human readability
    formatted_last_read = "Never read"
    if last_read_time:
        try:
            dt = _parse_timestamp(last_read_time)
            if dt:
                now = datetime.now(timezone.utc)
                diff = now - dt

                if diff.days == 0:
                    hours = diff.seconds // 3600
                    if hours == 0:
                        minutes = diff.seconds // 60
                        formatted_last_read = f"{minutes} minutes ago"
                    else:
                        formatted_last_read = f"{hours} hours ago"
                elif diff.days == 1:
                    formatted_last_read = "Yesterday"
                else:
                    formatted_last_read = f"{diff.days} days ago"
        except Exception:
            formatted_last_read = last_read_time

    return {
        "name": result.get('name'),
        "space_name": space_name,
        "last_read_time": last_read_time,
        "formatted_last_read": formatted_last_read
    }
