# VS Code GitHub Copilot Chat Recovery Tool

Recover lost GitHub Copilot Chat sessions from VS Code's internal storage and import them back.

## Why this exists

VS Code stores GitHub Copilot Chat sessions as `.jsonl` files in `workspaceStorage`. These sessions can become orphaned or inaccessible for various reasons, some of which are still under investigation. While such issues get fixed, you may use this tool to find "lost" chats and converts them to importable JSON.

## Requirements

- Python 3.8+ (stdlib only, no dependencies)

## Usage

```bash
python3 main.py
```

This will:
1. Scan all VS Code and VS Code Insiders workspaceStorage directories for chat sessions
2. Display them sorted by most recent, showing session ID, title, workspace, date, and turn count

### Recovering a session

Copy the session ID from the list and pass it as an argument:

```bash
python3 main.py <session-id>
python3 main.py <session-id> -o ./recovered   # Save to a specific directory
```

### Importing into VS Code

After recovering a session:

1. **Cmd+Shift+P** (or Ctrl+Shift+P)
2. Type **"Chat: Import Chat…"**
3. Select the exported `.json` file

## How it works

VS Code stores chat sessions as `.jsonl` files under:

| OS      | Path                                                                         |
|---------|------------------------------------------------------------------------------|
| macOS   | `~/Library/Application Support/Code/User/workspaceStorage/`                  |
| macOS   | `~/Library/Application Support/Code - Insiders/User/workspaceStorage/`       |
| Windows | `%APPDATA%/Code/User/workspaceStorage/`                                      |
| Windows | `%APPDATA%/Code - Insiders/User/workspaceStorage/`                           |
| Linux   | `~/.config/Code/User/workspaceStorage/`                                      |
| Linux   | `~/.config/Code - Insiders/User/workspaceStorage/`                           |

The `.jsonl` format uses incremental patches:

- **kind=0** — Initial full state snapshot
- **kind=1** — Set a field at a nested path
- **kind=2** — Extend an array or delete at index

The tool replays these patches to reconstruct the final session state, then extracts the fields needed by VS Code's import command.
