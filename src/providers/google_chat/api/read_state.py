"""API functions for Google Chat read state management.

This module provides functions to interact with the Google Chat API's read state
endpoints, allowing retrieval and management of message read states for spaces
and threads.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from googleapiclient.discovery import build

from src.providers.google_chat.api.auth import get_credentials

logger = logging.getLogger("read_state")


def _normalize_space_name(space_name: str) -> str:
    """Normalize space name to ensure it has the 'spaces/' prefix.

    Args:
        space_name: The space name, with or without 'spaces/' prefix

    Returns:
        Normalized space name with 'spaces/' prefix
    """
    if not space_name.startswith('spaces/'):
        return f"spaces/{space_name}"
    return space_name


def _get_user_id_from_credentials() -> str:
    """Extract the user ID from the current credentials.

    Returns:
        The user ID in the format 'users/me' for API calls

    Raises:
        Exception: If no valid credentials are found
    """
    creds = get_credentials()
    if not creds:
        raise Exception("No valid credentials found. Please authenticate first.")
    return "users/me"


async def get_space_read_state(space_name: str) -> Dict:
    """Get the read state of a space for the authenticated user.

    Retrieves the last read time for a specific space, indicating the timestamp
    of the most recent message the user has read in that space.

    Args:
        space_name: The resource name of the space. Can be either a full resource
                   name (e.g., 'spaces/AAQAXL5fJxI') or just the ID portion
                   ('AAQAXL5fJxI'). If only the ID is provided, it will be
                   automatically prefixed with 'spaces/'.

    Returns:
        Dictionary containing the read state with properties:
        - name: The resource name of the read state
               (format: "users/{user}/spaces/{space}/spaceReadState")
        - lastReadTime: ISO 8601 timestamp of when the space was last read

    Raises:
        Exception: If authentication fails or the API call fails

    API Reference:
        https://developers.google.com/workspace/chat/api/reference/rest/v1/users.spaces/getSpaceReadState
    """
    try:
        creds = get_credentials()
        if not creds:
            raise Exception("No valid credentials found. Please authenticate first.")

        service = build('chat', 'v1', credentials=creds)

        # Normalize space name
        space_name = _normalize_space_name(space_name)

        # Build the resource name for the read state
        user_id = _get_user_id_from_credentials()
        resource_name = f"{user_id}/{space_name}/spaceReadState"

        logger.info(f"Getting read state for: {resource_name}")

        # Make API request
        result = service.users().spaces().getSpaceReadState(
            name=resource_name
        ).execute()

        logger.info(f"Retrieved read state for space {space_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to get space read state: {str(e)}")
        raise Exception(f"Failed to get space read state: {str(e)}")


async def get_thread_read_state(space_name: str, thread_name: str) -> Dict:
    """Get the read state of a thread for the authenticated user.

    Retrieves the last read time for a specific thread within a space,
    indicating the timestamp of the most recent message the user has read
    in that thread.

    Args:
        space_name: The resource name of the space containing the thread.
                   Can be either a full resource name or just the ID portion.
        thread_name: The resource name of the thread. Can be either a full
                    resource name (e.g., 'spaces/{space}/threads/{thread}')
                    or just the thread ID.

    Returns:
        Dictionary containing the thread read state with properties:
        - name: The resource name of the thread read state
               (format: "users/{user}/spaces/{space}/threads/{thread}/threadReadState")
        - lastReadTime: ISO 8601 timestamp of when the thread was last read

    Raises:
        Exception: If authentication fails or the API call fails

    API Reference:
        https://developers.google.com/workspace/chat/api/reference/rest/v1/users.spaces.threads/getThreadReadState
    """
    try:
        creds = get_credentials()
        if not creds:
            raise Exception("No valid credentials found. Please authenticate first.")

        service = build('chat', 'v1', credentials=creds)

        # Normalize space name
        space_name = _normalize_space_name(space_name)

        # Normalize thread name
        if not thread_name.startswith('spaces/'):
            if thread_name.startswith('threads/'):
                thread_name = f"{space_name}/{thread_name}"
            else:
                thread_name = f"{space_name}/threads/{thread_name}"

        # Build the resource name for the thread read state
        user_id = _get_user_id_from_credentials()
        resource_name = f"{user_id}/{space_name}/threads/{thread_name.split('/')[-1]}/threadReadState"

        logger.info(f"Getting thread read state for: {resource_name}")

        # Make API request
        result = service.users().spaces().threads().getThreadReadState(
            name=resource_name
        ).execute()

        logger.info(f"Retrieved read state for thread {thread_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to get thread read state: {str(e)}")
        raise Exception(f"Failed to get thread read state: {str(e)}")


async def update_space_read_state(space_name: str, last_read_time: Optional[str] = None) -> Dict:
    """Update the read state of a space (mark as read).

    Updates the last read time for a specific space. If no timestamp is provided,
    marks the space as fully read up to the current time.

    Args:
        space_name: The resource name of the space. Can be either a full resource
                   name (e.g., 'spaces/AAQAXL5fJxI') or just the ID portion
                   ('AAQAXL5fJxI'). If only the ID is provided, it will be
                   automatically prefixed with 'spaces/'.
        last_read_time: Optional ISO 8601 timestamp to set as the last read time.
                       If not provided, the current time is used.

    Returns:
        Dictionary containing the updated read state with properties:
        - name: The resource name of the read state
        - lastReadTime: The updated ISO 8601 timestamp

    Raises:
        Exception: If authentication fails or the API call fails

    API Reference:
        https://developers.google.com/workspace/chat/api/reference/rest/v1/users.spaces/updateSpaceReadState
    """
    try:
        creds = get_credentials()
        if not creds:
            raise Exception("No valid credentials found. Please authenticate first.")

        service = build('chat', 'v1', credentials=creds)

        # Normalize space name
        space_name = _normalize_space_name(space_name)

        # Build the resource name for the read state
        user_id = _get_user_id_from_credentials()
        resource_name = f"{user_id}/{space_name}/spaceReadState"

        # Use current time if not provided
        if last_read_time is None:
            last_read_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        # Build update body
        update_body = {
            "lastReadTime": last_read_time
        }

        logger.info(f"Updating read state for space {space_name} to {last_read_time}")

        # Make API request
        result = service.users().spaces().updateSpaceReadState(
            name=resource_name,
            updateMask="lastReadTime",
            body=update_body
        ).execute()

        logger.info(f"Updated read state for space {space_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to update space read state: {str(e)}")
        raise Exception(f"Failed to update space read state: {str(e)}")


async def find_direct_message_space(user_email: str) -> Dict:
    """Find the direct message (DM) space with a specific user.

    Uses the spaces.findDirectMessage endpoint to locate a 1:1 direct message
    space between the authenticated user and the specified user.

    Args:
        user_email: The email address of the user to find the DM with
                   (e.g., 'user@example.com')

    Returns:
        Dictionary containing the space information for the DM:
        - name: The resource name of the space (e.g., 'spaces/AAQAXL5fJxI')
        - type: The type of space (always "DIRECT_MESSAGE" for DMs)
        - displayName: The display name of the space
        - Other space properties as applicable

    Raises:
        Exception: If authentication fails, the DM doesn't exist, or the API call fails

    API Reference:
        https://developers.google.com/workspace/chat/api/reference/rest/v1/spaces/findDirectMessage
    """
    try:
        creds = get_credentials()
        if not creds:
            raise Exception("No valid credentials found. Please authenticate first.")

        service = build('chat', 'v1', credentials=creds)

        # Build user reference
        user_reference = f"users/{user_email}"

        logger.info(f"Finding DM space with user: {user_email}")

        # Make API request
        result = service.spaces().findDirectMessage(
            name=user_reference
        ).execute()

        logger.info(f"Found DM space: {result.get('name', 'unknown')}")
        return result

    except Exception as e:
        logger.error(f"Failed to find DM space: {str(e)}")
        raise Exception(f"Failed to find DM space with user {user_email}: {str(e)}")
