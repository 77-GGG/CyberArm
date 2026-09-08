from pathlib import Path
p=Path('E:/CyberArm/mechanical')
code=(p/'scripts/interference_blender_arm.py').read_text().replace('blender_arm_v2','blender_arm_v3')
exec(compile(code,'B3_interference','exec'),globals())
