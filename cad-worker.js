importScripts('matcher.js');
importScripts('step-features.js');
self.onmessage=async({data})=>{try{
 let meshes;
 if(data.ext==='stl'){postMessage({stage:'正在解析 STL 网格…'});const a=HousingMatcher.parseSTL(data.buffer).map(x=>x*data.scale);meshes=[{attributes:{position:{array:a}},index:null}];}
 else{postMessage({stage:'正在加载 STEP 解析器…'});importScripts('vendor/occt-import-js.js');const occt=await occtimportjs({locateFile:p=>'vendor/'+p});postMessage({stage:'正在解析 STEP 几何体，复杂零件可能需要较长时间…'});const r=occt.ReadStepFile(new Uint8Array(data.buffer),{linearUnit:'millimeter',linearDeflectionType:'absolute_value',linearDeflection:0.01,angularDeflection:0.2});if(!r.success||!r.meshes?.length)throw Error('无法解析 STEP，请检查文件或重新导出');meshes=r.meshes;}
 postMessage({stage:'正在测量尺寸并识别台阶…'});
 const box=HousingMatcher.bounds(meshes.map(m=>m.attributes.position.array));const edges=[];
 let budget=4500;
 for(const m of meshes){const a=m.attributes.position.array,idx=m.index?.array;const n=idx?idx.length/3:a.length/9;const stride=Math.max(1,Math.ceil(n/Math.max(1,budget)));for(let t=0;t<n&&budget>0;t+=stride,budget--){for(const v of [0,1,1,2,2,0]){let i=(idx?idx[t*3+v]:t*3+v)*3;edges.push(a[i],a[i+1],a[i+2]);}}}
 const planes=data.ext==='stl'?[]:StepFeatures.extractPlanes(meshes);
 postMessage({box,edges,meshes:meshes.length,planes,format:data.ext});
}catch(e){postMessage({error:e.message||'解析失败'});}};
