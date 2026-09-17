import copy
import importlib.util
from pathlib import Path
import shutil
import subprocess
import json
import pytest
from fastapi.testclient import TestClient
from cyberarm.calibration import validate_mapping, angle_pulse, CalibrationStore
from cyberarm import server
from cyberarm.hardware import HardwareBridge
from test_hardware import FakeSerial

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('wiring',ROOT/'tools/generate_wiring.py')
wiring=importlib.util.module_from_spec(spec);spec.loader.exec_module(wiring)
M={'points':[{'deg':-10,'us':1400},{'deg':0,'us':1500},{'deg':10,'us':1620}], 'low_deg':-5,'high_deg':5}


def test_mapping_and_independent_limits():
    assert angle_pulse(M,5)==1560
    expanded={**M,'low_deg':-10,'high_deg':10}
    assert angle_pulse(expanded,5)==angle_pulse(M,5)
    with pytest.raises(ValueError):angle_pulse(M,6)
    for change in ({'low_deg':-11},{'points':[{'deg':-1,'us':1400},{'deg':0,'us':1600},{'deg':1,'us':1500}]}, {'high_deg':float('nan')}):
        with pytest.raises(ValueError):validate_mapping({**M,**change})


def test_wiring_validation_generation_and_host_firmware(tmp_path):
    data=json.loads((ROOT/'config/wiring.json').read_text())
    bad=copy.deepcopy(data);bad['axes'][1]['channel']=bad['axes'][0]['channel']
    with pytest.raises(ValueError):wiring.validate(bad)
    bad=copy.deepcopy(data);bad['i2c']['sda_gpio']=19
    with pytest.raises(ValueError):wiring.validate(bad)
    data['axes'][2]['channel']=12
    src=tmp_path/'wiring.json';src.write_text(json.dumps(data))
    digest=wiring.generate(src,tmp_path/'WiringConfig.h')
    assert digest in (tmp_path/'WiringConfig.h').read_text()
    compiler=shutil.which('g++')
    assert compiler,'g++ is required to execute firmware tests'
    exe=tmp_path/'firmware_test.exe'
    subprocess.run([compiler,'-std=c++17','-I'+str(ROOT/'.pio/libdeps/esp32-s3-devkitc-1/ArduinoJson/src'),'-I'+str(ROOT/'tools/firmware_test/host_stubs'),'-I'+str(tmp_path),'-I'+str(ROOT/'lib/CyberArmFirmware/src'),
                    str(ROOT/'tools/firmware_test/firmware_host_test.cpp'),str(ROOT/'lib/CyberArmFirmware/src/ServoSubsystem.cpp'),
                    str(ROOT/'lib/CyberArmFirmware/src/CommandProtocol.cpp'),
                    str(ROOT/'lib/CyberArmFirmware/src/MotionController.cpp'),'-o',str(exe)],check=True,capture_output=True)
    subprocess.run([str(exe)],check=True,capture_output=True)


class CalibrationSerial(FakeSerial):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.state.update(capabilities={'axis_calibration':1},device_id='test-device',wiring_hash='test-wiring',
            test={'active':False},mappings=[{'confirmed':False,'revision':0,'points':[]} for _ in range(6)])
    def write(self,encoded):
        cmd=json.loads(encoded);name=cmd['command']
        if name=='test_begin':self.state.update(mode='SERVICE',outputs_enabled=True,test={'active':True,'axis':cmd['axis']+1})
        if name in ('test_end','disarm'):self.state.update(mode='DISARMED',outputs_enabled=False,test={'active':False})
        if name=='save_mapping':
            i=cmd['axis'];self.state['mappings'][i]={'confirmed':True,'revision':self.state['mappings'][i]['revision']+1,
              'points':cmd['points'],'low_deg':cmd['low_deg'],'high_deg':cmd['high_deg'],
              'work_low_deg':cmd['low_deg'],'work_high_deg':cmd['high_deg']}
        return super().write(encoded)


def test_workbench_ownership_save_readback_drafts_and_limits(tmp_path,monkeypatch):
    monkeypatch.setenv('CYBERARM_USER_DATA_DIR',str(tmp_path))
    with TestClient(server.app) as client:
        device=CalibrationSerial()
        bridge=HardwareBridge('revc-sim-1',[[-30,30]]*5+[[-8,8]],serial_factory=lambda **kw:device)
        monkeypatch.setattr(server,'hardware',bridge)
        boot=client.get('/api/bootstrap').json();headers={'x-session':boot['session'],'x-client':'page-a'}
        assert client.post('/api/hardware/connect',headers=headers,json={'port':'FAKE'}).status_code==200
        base='/api/hardware/calibration-workbench/'
        def post(path,body,h=headers):return client.post(base+path,headers=h,json=body)
        assert post('test',{'action':'begin'}).status_code==409
        assert post('test',{'action':'begin','confirmation':'SUPPORTED'}).status_code==200
        assert post('test',{'action':'renew'},{**headers,'x-client':'page-b'}).status_code==409
        saved={**M,'axis':1,'confirmed':True,'device_id':'test-device','wiring_hash':'test-wiring','expected_revision':0}
        assert post('save',saved).status_code==422
        assert post('test',{'action':'end'}).status_code==200
        assert post('draft',{'axis':1,'data':{'points':M['points'],'readings':[]}}).status_code==200
        response=post('save',saved);assert response.status_code==200,response.text
        assert bridge.effective_limits()[0]==[-5,5]
        assert post('save',saved).status_code==422
        records=client.get(base+'records').json()
        assert records['backup_matches'] and records['axes']['1']['points']==M['points']
        assert len(list((tmp_path/'calibration').glob('*.json')))==1
        from cyberarm.planner import plan_job, Rejected
        with pytest.raises(Rejected):plan_job({'start':[0]*6,'limits_deg':bridge.effective_limits(),'obstacles':[],
            'speed':.7,'steps':[{'kind':'joint','q_deg':[8,0,0,0,0,0]}]})
