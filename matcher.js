(function(root){
const FIELDS=['length','width','stepHeight','stepLength'];
const WEIGHTS={length:40,width:30,stepHeight:20,stepLength:10};
function rank(records,query,tolerances,strict=false){
 for(const k of ['length','width']) if(!Number.isFinite(query[k])||query[k]<=0) throw Error('长度和宽度必须大于零');
 const active=FIELDS.filter(k=>query[k]!==null&&query[k]!==undefined);
 for(const k of active){if(!Number.isFinite(query[k]))throw Error('尺寸必须为有限数字');if(!Number.isFinite(tolerances[k])||tolerances[k]<=0)throw Error('容差必须大于零');}
 if(query.stepLength!=null&&query.stepLength<0)throw Error('台阶长度不能小于零');
 const total=active.reduce((s,k)=>s+WEIGHTS[k],0);
 return records.map(record=>{let error=0,covered=0,within=true;const deltas={};
 for(const k of active){if(!Number.isFinite(record[k])){error+=WEIGHTS[k];within=false;deltas[k]=null;continue;}let d=query[k]-record[k];deltas[k]=d;covered+=WEIGHTS[k];error+=WEIGHTS[k]*Math.min(Math.abs(d)/tolerances[k],1);if(Math.abs(d)>tolerances[k]+1e-9)within=false;}
 return{record,score:Math.max(0,100*(1-error/total)),coverage:covered/total*100,deltas,within};
 }).filter(r=>!strict||r.within).sort((a,b)=>b.score-a.score||b.coverage-a.coverage||a.record.sourceRow-b.record.sourceRow);
}
function bounds(arrays){const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];let count=0;
 for(const array of arrays){if(array.length%3)throw Error('无效顶点坐标');for(let i=0;i<array.length;i+=3){for(let j=0;j<3;j++){const n=array[i+j];if(!Number.isFinite(n))throw Error('模型含无效坐标');min[j]=Math.min(min[j],n);max[j]=Math.max(max[j],n);}count++;}}
 if(count<3)throw Error('模型中没有有效几何体');const size=max.map((n,i)=>n-min[i]);if(size.filter(n=>n>0).length<2)throw Error('模型尺寸退化');return{min,max,size,count};
}
function parseSTL(buffer){const view=new DataView(buffer);let vertices=[];
 if(buffer.byteLength>=84&&84+view.getUint32(80,true)*50===buffer.byteLength){const n=view.getUint32(80,true);for(let i=0;i<n;i++)for(let j=0;j<9;j++)vertices.push(view.getFloat32(84+i*50+12+j*4,true));}
 else{const text=new TextDecoder().decode(buffer);if(!/^\s*solid\b/i.test(text)||!/(?:^|\n)\s*endsolid\b/i.test(text))throw Error('STL 格式无效');const re=/\bvertex\s+([+-]?[\d.eE+-]+)\s+([+-]?[\d.eE+-]+)\s+([+-]?[\d.eE+-]+)/g;for(const m of text.matchAll(re))vertices.push(Number(m[1]),Number(m[2]),Number(m[3]));}
 if(vertices.length%9||!vertices.length)throw Error('STL 三角面数据不完整');bounds([vertices]);return vertices;
}
root.HousingMatcher={rank,bounds,parseSTL,FIELDS};if(typeof module!=='undefined')module.exports=root.HousingMatcher;
})(globalThis);
