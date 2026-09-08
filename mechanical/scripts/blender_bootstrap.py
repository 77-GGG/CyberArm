import bpy
from pathlib import Path

addon_path = Path('E:/CyberArm/tools/blender-mcp/addon.py')
bpy.ops.preferences.addon_install(filepath=str(addon_path))
bpy.ops.preferences.addon_enable(module='addon')
bpy.context.preferences.addons['addon'].preferences.telemetry_consent = False
bpy.ops.wm.save_userpref()
bpy.context.scene.blendermcp_auto_start_server = True
if not getattr(bpy.types, 'blendermcp_server', None):
    bpy.ops.blendermcp.start_server()
print('CYBERARM_BLENDER_MCP_READY', flush=True)
