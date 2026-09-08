import bpy,json
ns={}
exec(compile(open('E:/CyberArm/mechanical/scripts/revC_connections.py',encoding='utf8').read(),'RevC','exec'),ns,ns)
for name in ['print_interfaces','machined_horns','clear_fixed_supports','hardware','centre_screws','save']:
    print('START',name,flush=True)
    print(json.dumps(ns[name](),ensure_ascii=False,default=str),flush=True)
print('REV_C_BUILD_COMPLETE',flush=True)
