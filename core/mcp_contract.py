"""Shared self-MCP schema and pipe identity, without importing UI or credentials."""
import getpass
import hashlib
from pathlib import Path


def pipe_name():
    source = str(Path(__file__).resolve().parents[1]).lower() + getpass.getuser()
    return 'guga-self-' + hashlib.sha256(source.encode('utf-8')).hexdigest()[:20]


def self_tools():
    from core.self_agent import TOOLS
    return [dict(name=t['function']['name'], description=t['function']['description'],
                 inputSchema=t['function']['parameters'])
            for t in TOOLS if t['function']['name'] in ('app_state', 'pet_control', 'workspace', 'applications')]
