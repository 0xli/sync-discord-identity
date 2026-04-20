#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional


def sanitize_filename(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    s = s.strip("-.")
    return s or "discord-bot"


def build_static_avatar_url(bot_id: str, avatar_hash: str) -> str:
    return f"https://cdn.discordapp.com/avatars/{bot_id}/{avatar_hash}.png"


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def load_discord_json(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_discord_block_lines(data: Dict) -> List[str]:
    fields = []
    for key in ("username", "locale", "email", "bio"):
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        fields.append(f"  - {key}: {value}")
    if not fields:
        return []
    return ["- **Discord:**"] + fields


def find_field_line(lines: List[str], field_name: str) -> Optional[int]:
    pat = re.compile(rf"^\s*[-*]\s*\*\*{re.escape(field_name)}:\*\*")
    for i, line in enumerate(lines):
        if pat.search(line):
            return i
    return None


def find_discord_block(lines: List[str]) -> Optional[tuple[int, int]]:
    start = find_field_line(lines, "Discord")
    if start is None:
        return None
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if re.match(r"^\s*[-*]\s*\*\*[^*]+:\*\*", line):
            break
        end += 1
    return start, end


def upsert_avatar(lines: List[str], avatar_url: str, force_avatar: bool) -> List[str]:
    idx = find_field_line(lines, "Avatar")
    new_line = f"- **Avatar:** {avatar_url}"
    if idx is None:
        insert_at = 1 if lines and lines[0].startswith("#") else 0
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        lines.insert(insert_at, new_line)
        return lines

    existing = lines[idx].strip()
    if existing == new_line:
        return lines
    if not force_avatar:
        raise RuntimeError(
            f"IDENTITY.md already has a different Avatar field:\n  existing: {existing}\n  desired:  {new_line}\nUse --force-avatar to replace it."
        )
    lines[idx] = new_line
    return lines


def upsert_discord_block(lines: List[str], discord_lines: List[str]) -> List[str]:
    if not discord_lines:
        return lines
    block = find_discord_block(lines)
    if block is None:
        # append near end, preserving a blank line before if needed
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(discord_lines)
        return lines

    start, end = block
    lines[start:end] = discord_lines
    return lines


def ensure_identity_file(path: Path) -> List[str]:
    if path.exists():
        return path.read_text(encoding="utf-8").splitlines()
    return ["# IDENTITY", ""]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Discord bot metadata into OpenClaw IDENTITY.md")
    parser.add_argument("--workspace", required=True, help="OpenClaw workspace directory")
    parser.add_argument("--discord-json", required=True, help="Path to Discord bot JSON from /users/@me")
    parser.add_argument("--identity", help="Path to IDENTITY.md (defaults to <workspace>/IDENTITY.md)")
    parser.add_argument("--force-avatar", action="store_true", help="Replace an existing different Avatar field")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    identity = Path(args.identity).expanduser().resolve() if args.identity else workspace / "IDENTITY.md"
    data = load_discord_json(Path(args.discord_json).expanduser().resolve())

    bot_id = str(data.get("id") or "").strip()
    avatar_hash = str(data.get("avatar") or "").strip()
    username = str(data.get("username") or bot_id or "discord-bot").strip()

    if not bot_id:
        print("Missing Discord bot id in JSON.", file=sys.stderr)
        return 2
    if not avatar_hash:
        print("Discord bot JSON does not contain an avatar hash.", file=sys.stderr)
        return 2

    avatar_url = build_static_avatar_url(bot_id, avatar_hash)
    avatar_filename = sanitize_filename(username) + ".png"
    avatar_dest = workspace / "avatars" / avatar_filename

    download_file(avatar_url, avatar_dest)

    lines = ensure_identity_file(identity)
    backup = identity.with_suffix(identity.suffix + ".bak") if identity.exists() else None
    if backup:
        shutil.copy2(identity, backup)

    lines = upsert_avatar(lines, avatar_url, force_avatar=args.force_avatar)
    lines = upsert_discord_block(lines, ensure_discord_block_lines(data))

    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Updated:")
    print(f"  IDENTITY.md: {identity}")
    print(f"  local avatar: {avatar_dest}")
    print(f"  avatar url:   {avatar_url}")
    if backup:
        print(f"  backup:       {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
