const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const desktop = path.resolve(__dirname,'..');
const root = path.resolve(desktop,'..');
const simulator = path.join(root,'simulator');
const stage = path.join(desktop,'stage');
function run(command,args,cwd=root) {
  const result = spawnSync(command,args,{cwd,stdio:'inherit',shell:process.platform==='win32' && command==='npm',env:{...process.env,PYTHONPATH:path.join(simulator,'backend')}});
  if(result.error)throw result.error;
  if(result.status!==0)throw new Error(`${command} 失败，退出码 ${result.status}`);
}
const python = path.join(simulator,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
if(!fs.existsSync(python))throw new Error('请先建立 simulator/.venv');
run('npm',['ci'],path.join(simulator,'frontend'));
run('npm',['run','build'],path.join(simulator,'frontend'));
run('cmake',['--build',path.join(simulator,'core/build'),'--config','Release']);
run('ctest',['--test-dir',path.join(simulator,'core/build'),'-C','Release','--output-on-failure']);
run(python,['-m','PyInstaller','--version']);
// Only generated directories under this desktop project may be removed.
for(const folder of [stage,path.join(desktop,'build')]) {
  if(!folder.startsWith(desktop+path.sep))throw new Error('构建清理路径越界');
  fs.rmSync(folder,{recursive:true,force:true});
}
fs.mkdirSync(path.join(desktop,'build'),{recursive:true});
run(python,['-m','PyInstaller','--noconfirm','--clean','--onedir','--name','cyberarm-backend',
  // The planner imports scipy.optimize inside a function so a session's first
  // joint preview does not pay six tenths of a second for it. Naming it here
  // keeps that import in the archive even if the bytecode scan misses it.
  '--hidden-import','scipy.optimize',
  '--distpath',path.join(desktop,'build/frozen'),'--workpath',path.join(desktop,'build/work'),
  '--specpath',path.join(desktop,'build'),'--paths',path.join(simulator,'backend'),
  path.join(desktop,'backend_entry.py')]);
fs.mkdirSync(stage,{recursive:true});
fs.cpSync(path.join(desktop,'build/frozen/cyberarm-backend'),path.join(stage,'backend'),{recursive:true});
const resources=path.join(stage,'simulator');
fs.cpSync(path.join(simulator,'frontend/dist'),path.join(resources,'frontend/dist'),{recursive:true});
fs.cpSync(path.join(simulator,'assets/revc'),path.join(resources,'assets/revc'),{recursive:true});
const names=process.platform==='win32'?['libcyberarm_core.dll','cyberarm_core.dll']:process.platform==='darwin'?['libcyberarm_core.dylib']:['libcyberarm_core.so'];
const candidates=names.flatMap(name=>[path.join(simulator,'core/build',name),path.join(simulator,'core/build/Release',name)]);
const library=candidates.find(p=>fs.existsSync(p));
if(!library)throw new Error('核心库缺失');
fs.mkdirSync(path.join(resources,'core'),{recursive:true});
fs.copyFileSync(library,path.join(resources,'core',path.basename(library)));
for(const file of ['frontend/dist/index.html','assets/revc/robot.glb','assets/revc/robot.json','assets/revc/collision.npz']) {
  if(!fs.existsSync(path.join(resources,file)))throw new Error(`资源缺失：${file}`);
}
console.log('完整后端、前端和模型已准备完成。');
