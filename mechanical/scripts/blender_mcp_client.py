"""Local MCP client for this session; Codex loads configured tools next session."""
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    env = dict(os.environ, DISABLE_TELEMETRY='1', BLENDER_HOST='127.0.0.1')
    params = StdioServerParameters(command='E:/CyberArm/tools/blender-mcp/.venv/Scripts/blender-mcp.exe', env=env)
    async with stdio_client(params) as (rd, wr):
        async with ClientSession(rd, wr) as session:
            await session.initialize()
            if len(sys.argv) == 1:
                res = await session.call_tool('get_scene_info', {'user_prompt': 'Inspect local CyberArm modeling scene'})
            else:
                code = Path(sys.argv[1]).read_text(encoding='utf-8')
                res = await session.call_tool('execute_blender_code', {'code': code, 'user_prompt': 'Build and verify the user-requested printable mechanical arm locally'})
            print(res.model_dump_json(indent=2))
asyncio.run(main())
