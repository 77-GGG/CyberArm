import bpy
bpy.context.scene.cycles.samples=16
bpy.ops.render.render(write_still=True)
