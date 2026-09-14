from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from cyberarm_sdk import CyberArm

with CyberArm() as arm:
    start=arm.state()['q_deg']
    target=start.copy();target[0]=min(20,target[0]+5)
    plan=arm.preview([{'kind':'joint','q_deg':target}])
    print(f"预览通过：{plan['duration']:.2f} 秒，{plan['checks']} 个检查区间")
    # Explicitly call arm.execute(plan) to run, and keep this client alive until
    # completion. Closing the controlling client causes an automatic pause.
