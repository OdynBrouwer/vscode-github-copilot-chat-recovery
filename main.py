#!/usr/bin/env python3
"""
VS Code Copilot Chat Recovery Tool

Scans VS Code's internal workspaceStorage (stable + Insiders) for
Copilot Chat sessions and lists them sorted by most recent.

Usage:
    python3 main.py                         # List all sessions
    python3 main.py <session-id>            # Recover a session by ID
    python3 main.py <session-id> -o ./out   # Recover to a specific directory

No external dependencies — Python 3.8+ stdlib only.
"""
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ─── Storage location ───────────────────────────────────────────────────────────

def get_workspace_storage_roots():
    """Return the VS Code workspaceStorage roots for the current OS (stable + Insiders)."""
    app_names = ["Code", "Code - Insiders"]
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", ""))
    else:
        base = Path.home() / ".config"
    return [base / name / "User" / "workspaceStorage" for name in app_names]


# ─── JSONL replay engine ────────────────────────────────────────────────────────

def set_nested(obj, path, value):
    """Set a nested value in obj following the key path."""
    for key in path[:-1]:
        if isinstance(obj, list):
            key = int(key)
            while len(obj) <= key:
                obj.append({})
            obj = obj[key]
        else:
            if key not in obj:
                obj[key] = {}
            obj = obj[key]
    last = path[-1]
    if isinstance(obj, list):
        last = int(last)
        while len(obj) <= last:
            obj.append({})
        obj[last] = value
    else:
        obj[last] = value


def extend_nested(obj, path, items):
    """Append items to the array at the nested path."""
    for key in path[:-1]:
        if isinstance(obj, list):
            key = int(key)
            while len(obj) <= key:
                obj.append({})
            obj = obj[key]
        else:
            if key not in obj:
                obj[key] = []
            obj = obj[key]
    last = path[-1]
    if isinstance(obj, list):
        last = int(last)
        while len(obj) <= last:
            obj.append([])
        obj[last].extend(items)
    else:
        if last not in obj:
            obj[last] = []
        obj[last].extend(items)


def delete_at_index(obj, path, index):
    """Delete an element at the given index from the array at the nested path."""
    for key in path:
        if isinstance(obj, list):
            obj = obj[int(key)]
        else:
            obj = obj[key]
    if isinstance(obj, list) and index < len(obj):
        obj.pop(index)


def replay_jsonl(filepath):
    """Replay all incremental patches in a .jsonl file and return the final state."""
    state = None
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            kind = entry.get("kind")
            if kind == 0:
                state = entry["v"]
            elif kind == 1:
                set_nested(state, entry["k"], entry["v"])
            elif kind == 2:
                if "v" in entry:
                    extend_nested(state, entry["k"], entry["v"])
                elif "i" in entry:
                    delete_at_index(state, entry["k"], entry["i"])
    return state


# ─── Scanning ────────────────────────────────────────────────────────────────────

def read_workspace_info(ws_dir):
    """Read workspace.json to get the folder path."""
    ws_json = ws_dir / "workspace.json"
    if ws_json.exists():
        try:
            with open(ws_json) as f:
                data = json.load(f)
            folder = data.get("folder", data.get("workspace", ""))
            # Strip file:// prefix for readability
            if folder.startswith("file:///"):
                folder = folder[7:]
            elif folder.startswith("file://"):
                folder = folder[7:]
            return folder or "unknown"
        except (json.JSONDecodeError, OSError):
            pass
    return "unknown"


def peek_session(jsonl_path):
    """Extract session metadata by scanning the JSONL without full replay."""
    try:
        with open(jsonl_path) as f:
            first_line = f.readline().strip()
            if not first_line:
                return None
            entry = json.loads(first_line)
            if entry.get("kind") != 0:
                return None
            v = entry["v"]

            title = v.get("customTitle", "Untitled")
            request_count = len(v.get("requests", []))

            # Scan for title patches and request appends
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                k = e.get("k", [])
                if e.get("kind") == 1 and k == ["customTitle"]:
                    title = e.get("v", title)
                if e.get("kind") == 2 and k == ["requests"] and "v" in e:
                    request_count += len(e["v"])

            return {
                "title": title,
                "session_id": v.get("sessionId", ""),
                "created": v.get("creationDate"),
                "turns": request_count,
                "file": str(jsonl_path),
            }
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def scan_all_sessions(storage_root):
    """Scan workspaceStorage for all chat sessions, returning metadata list."""
    results = []
    if not storage_root.exists():
        return results

    for ws_dir in sorted(storage_root.iterdir()):
        if not ws_dir.is_dir():
            continue

        workspace = read_workspace_info(ws_dir)
        chat_dir = ws_dir / "chatSessions"
        if not chat_dir.exists():
            continue

        for session_file in sorted(chat_dir.glob("*.jsonl")):
            info = peek_session(session_file)
            if info:
                info["workspace"] = workspace
                results.append(info)

    results.sort(key=lambda s: s.get("created") or 0, reverse=True)
    return results


# ─── Formatting ──────────────────────────────────────────────────────────────────

def fmt_time(ts):
    """Format a millisecond timestamp."""
    if ts is None:
        return "unknown"
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError):
        return str(ts)


def fmt_workspace(ws):
    """Shorten workspace path for display."""
    home = str(Path.home())
    if ws.startswith(home):
        return "~" + ws[len(home):]
    return ws


def print_session_list(sessions):
    """Print a list of sessions with ID, title, date, turns, and workspace."""
    max_title = max((len(s["title"]) for s in sessions), default=20)
    max_title = min(max_title, 55)
    id_width = 36

    print(f"\n  {'ID':<{id_width}}  {'Title':<{max_title}}  {'Created':<17} {'Turns':>5}  Workspace")
    print(f"  {'─'*id_width}  {'─'*max_title}  {'─'*17} {'─'*5}  {'─'*30}")

    for s in sessions:
        title = s["title"][:max_title]
        ws = fmt_workspace(s["workspace"])
        print(f"  {s['session_id']:<{id_width}}  {title:<{max_title}}  {fmt_time(s['created']):<17} {s['turns']:>5}  {ws}")

    print()


# ─── Conversion ──────────────────────────────────────────────────────────────────

def convert_session(jsonl_path, output_path):
    """Replay a JSONL session and write it as importable JSON."""
    state = replay_jsonl(jsonl_path)
    if state is None:
        return None

    export = {
        "responderUsername": state.get("responderUsername", "GitHub Copilot"),
        "initialLocation": state.get("initialLocation", "panel"),
        "requests": copy.deepcopy(state.get("requests", [])),
    }

    with open(output_path, "w") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    return {
        "title": state.get("customTitle", "Untitled"),
        "turns": len(export["requests"]),
        "output": output_path,
    }


def sanitize_filename(title):
    """Convert a title to a safe filename."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    return safe.strip().replace(" ", "-")[:80] or "untitled"


# ─── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Recover VS Code Copilot Chat sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python3 main.py                          List all sessions
  python3 main.py <session-id>             Recover a session by ID
  python3 main.py <session-id> -o ./out    Recover to a specific directory
        """,
    )
    parser.add_argument("session_id", nargs="?", default=None, help="Session ID to recover")
    parser.add_argument("-o", "--output-dir", default=".", help="Output directory (default: current dir)")
    args = parser.parse_args()

    storage_roots = [r for r in get_workspace_storage_roots() if r.exists()]
    if not storage_roots:
        print("Error: no workspaceStorage directories found", file=sys.stderr)
        sys.exit(1)

    # ── Scan sessions ──
    sessions = []
    for storage_root in storage_roots:
        sessions.extend(scan_all_sessions(storage_root))
    sessions.sort(key=lambda s: s.get("created") or 0, reverse=True)

    if not sessions:
        print("No sessions found.")
        sys.exit(0)

    # ── List mode (no session ID given) ──
    if args.session_id is None:
        print_session_list(sessions)
        return

    # ── Recover a specific session ──
    match = [s for s in sessions if s["session_id"] == args.session_id]
    if not match:
        print(f"Error: no session found with ID '{args.session_id}'", file=sys.stderr)
        sys.exit(1)

    session = match[0]
    os.makedirs(args.output_dir, exist_ok=True)
    filename = sanitize_filename(session["title"]) + ".json"
    output_path = os.path.join(args.output_dir, filename)

    result = convert_session(session["file"], output_path)
    if result:
        print(f"✓ {result['title']}")
        print(f"  {result['turns']} turns → {result['output']}")
        print(f"\nImport in VS Code: Cmd+Shift+P → 'Chat: Import Chat…' → select the .json file.")
    else:
        print(f"✗ Failed to recover: {session['title']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
