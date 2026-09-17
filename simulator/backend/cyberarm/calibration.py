"""Calibration validation and device-bound user records (no actuator I/O)."""
import hashlib
import json
import math
import os
from pathlib import Path
import uuid


def validate_mapping(data):
    points = data['points']
    low, high = data['low_deg'], data['high_deg']
    def finite(v):
        return type(v) in (int, float) and math.isfinite(v)
    if not finite(low) or not finite(high) or not low < 0 < high or not 3 <= len(points) <= 7:
        raise ValueError('需要 3–7 个标定点，工作范围必须包含零位')
    if any(not finite(p['deg']) or not finite(p['us']) or not -180 <= p['deg'] <= 180 or not 500 <= p['us'] <= 2500 for p in points):
        raise ValueError('标定点必须是有限角度和 500–2500 μs 脉宽')
    if not any(p['deg'] == 0 for p in points):
        raise ValueError('必须包含实测零位点')
    diffs = [b['us']-a['us'] for a,b in zip(points, points[1:])]
    if any(a['deg'] >= b['deg'] for a,b in zip(points, points[1:])) or not (all(d>0 for d in diffs) or all(d<0 for d in diffs)):
        raise ValueError('按角度从小到大排列，脉宽必须严格单调；不能有重复点')
    if low < points[0]['deg'] or high > points[-1]['deg']:
        raise ValueError('工作范围不能超过标定覆盖范围')
    return {'points':[{'deg':p['deg'],'us':p['us']} for p in points], 'low_deg':low, 'high_deg':high}


def angle_pulse(data, angle):
    m = validate_mapping(data)
    if not math.isfinite(angle) or not m['low_deg'] <= angle <= m['high_deg']:
        raise ValueError('目标角超出已验证工作范围')
    for a,b in zip(m['points'],m['points'][1:]):
        if angle <= b['deg']:
            return a['us']+(angle-a['deg'])*(b['us']-a['us'])/(b['deg']-a['deg'])
    raise ValueError('目标角未被标定覆盖')


class CalibrationStore:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get('CYBERARM_USER_DATA_DIR') or
                         Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'CyberArm')/'calibration'

    def path(self, state):
        if not state.get('device_id') or not state.get('wiring_hash'):
            raise ValueError('固件未提供设备身份/接线摘要')
        key = hashlib.sha256(json.dumps([state['device_id'],state['model_id'],state['wiring_hash']]).encode()).hexdigest()[:24]
        return self.root/(key+'.json')

    def read(self, state):
        path = self.path(state)
        if not path.exists():
            return {'schema_version':1,'device_id':state['device_id'],'model_id':state['model_id'],
                    'wiring_hash':state['wiring_hash'],'axes':{},'saved_mappings':[]}
        return json.loads(path.read_text(encoding='utf-8'))

    def write(self, state, data):
        path=self.path(state);path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('w',encoding='utf-8') as file:
                json.dump(data,file,ensure_ascii=False,indent=2,allow_nan=False)
                file.flush();os.fsync(file.fileno())
            os.replace(temporary,path)
        finally:
            temporary.unlink(missing_ok=True)
