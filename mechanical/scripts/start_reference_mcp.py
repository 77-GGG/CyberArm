import bpy
import addon_utils

addon_utils.enable('addon', default_set=False)
bpy.context.preferences.addons['addon'].preferences.telemetry_consent = False
if not getattr(bpy.types, 'blendermcp_server', None):
    bpy.ops.blendermcp.start_server()
print('ARDUINO_REFERENCE_MCP_READY', flush=True)
