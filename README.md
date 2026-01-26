# Google Chat MCP Server (Lightweight)

A lightweight MCP (Model Context Protocol) server for Google Chat integration. This is a stripped-down version focused on core messaging functionality without heavy ML dependencies.

## Features

- **Send messages** to Google Chat spaces
- **Reply to threads** in existing conversations
- **List messages** from spaces with filtering
- **Search messages** using exact match or regex patterns
- **Manage spaces** - list, create, and configure
- **User management** - get user info and member lists

## Installation

```bash
# Clone the repository
git clone https://github.com/azgooon/google-chat-mcp-server.git
cd google-chat-mcp-server

# Install dependencies
pip install -r requirements.txt
```

## Requirements

Minimal dependencies:
- `google-auth` - Google authentication
- `google-auth-oauthlib` - OAuth 2.0 support
- `google-api-python-client` - Google API client
- `fastmcp` - MCP server framework
- `pyyaml` - Configuration parsing

**No CUDA, PyTorch, or ML libraries required!**

## Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the **Google Chat API**

### 2. Configure OAuth Credentials

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. Select **Desktop app** as application type
4. Download the credentials JSON file
5. Save it as `src/providers/google_chat/credentials.json`

### 3. Required OAuth Scopes

When setting up OAuth, ensure these scopes are enabled:
- `https://www.googleapis.com/auth/chat.messages` - Read and send messages
- `https://www.googleapis.com/auth/chat.spaces` - Access spaces

### 4. Authenticate

```bash
# Run the auth server to complete OAuth flow
python src/server.py --provider google_chat -local-auth
```

This will open a browser for Google authentication. Once complete, a token file will be saved locally.

## Usage

### As MCP Server

Add to your Claude Code MCP configuration (`.mcp.json`):

```json
{
    "mcpServers": {
        "google-chat": {
            "command": "python",
            "args": ["src/server.py", "--provider", "google_chat"],
            "cwd": "/path/to/google-chat-mcp-server"
        }
    }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `send_message_tool` | Send a message to a space |
| `reply_to_message_thread_tool` | Reply to an existing thread |
| `get_space_messages_tool` | List messages in a space |
| `get_chat_message_tool` | Get a specific message |
| `delete_chat_message_tool` | Delete a message |
| `get_chat_spaces_tool` | List available spaces |
| `search_chat_messages_tool` | Search messages (exact/regex) |

### Example

```python
# Send a message
send_message_tool(
    space_name="spaces/AAQAtjsc9v4",
    text="Hello from Claude!"
)

# Search messages
search_chat_messages_tool(
    space_name="spaces/AAQAtjsc9v4",
    query="deployment",
    mode="exact"
)
```

## Search Modes

This lightweight version supports:

| Mode | Description |
|------|-------------|
| `exact` | Case-insensitive substring matching with contraction expansion |
| `regex` | Regular expression pattern matching |
| `hybrid` | Combines exact and regex results |

**Note:** Semantic search (ML-based) is not available in this version. If you request semantic mode, it will gracefully fall back to exact search.

## Configuration

Edit `src/providers/google_chat/search_config.yaml` to customize search behavior:

```yaml
search:
  default_mode: exact
  hybrid_weights:
    exact: 1.0
    regex: 1.2

search_modes:
  - name: exact
    enabled: true
    weight: 1.0
  - name: regex
    enabled: true
    weight: 1.2
```

## Development

```bash
# Run tests
pytest

# Run with debug logging
python src/server.py --provider google_chat --debug
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Credits

Forked from [siva010928/multi-chat-mcp-server](https://github.com/siva010928/multi-chat-mcp-server) and stripped down for lightweight deployment.
