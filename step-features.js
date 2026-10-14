/* Geometric candidates only: never use database dimensions to infer a feature. */
(function(root){
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
function extractPlanes(meshes){const faces=[];
 meshes.forEach((mesh,mi)=>{const p=mesh.attributes.position.array,idx=mesh.index?.array;if(!idx||!mesh.brep_faces)return;
 mesh.brep_faces.forEach((f,fi)=>{let normal=null,area=0,level=0,axis=-1,valid=true;const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity],tris=[];
 for(let t=f.first;t<=f.last;t++){const v=[0,1,2].map(j=>p.slice(idx[t*3+j]*3,idx[t*3+j]*3+3));if(v.some(a=>a.length!==3||a.some(x=>!Number.isFinite(x)))){valid=false;break;}
 const u=v[1].map((x,j)=>x-v[0][j]),w=v[2].map((x,j)=>x-v[0][j]),c=[u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0]],norm=Math.hypot(...c);if(norm<1e-10)continue;const n=c.map(x=>x/norm);
 if(!normal){normal=n;axis=n.map(Math.abs).indexOf(Math.max(...n.map(Math.abs)));if(Math.abs(n[axis])<.99999){valid=false;break;}}
 if(dot(normal,n)<.99999){valid=false;break;}area+=norm/2;level+=v[0][axis]*norm/2;
 for(const a of v)for(let j=0;j<3;j++){min[j]=Math.min(min[j],a[j]);max[j]=Math.max(max[j],a[j]);}tris.push(v);
 }
 if(!valid||area<1||max[axis]-min[axis]>.01)return;
 // Keep a bounded sample for highlighting, independently from measurement.
 const edges=[];const stride=Math.max(1,Math.ceil(tris.length/180));for(let t=0;t<tris.length;t+=stride)for(const j of [0,1,1,2,2,0])edges.push(...tris[t][j]);
 faces.push({id:mi+':'+fi,mesh:mi,face:fi,axis,sign:Math.sign(normal[axis]),normal,level:level/area,min,max,area,edges});
 });});return faces;
}
function findCandidates(faces,box,l,w){if(l===w||![l,w].every(x=>[0,1,2].includes(x)))return[];const h=3-l-w,L=box.size[l],W=box.size[w],H=box.size[h],out=[];if(!(L>0&&W>0&&H>0))return[];
 const planes=faces.filter(f=>f.axis===h&&f.max[w]-f.min[w]>=W*.3&&f.area>W*L*.015).sort((a,b)=>b.area-a.area).slice(0,100);
 for(const base of planes)for(const tail of planes){if(base===tail||base.mesh!==tail.mesh||base.sign!==tail.sign)continue;
 const bl=base.max[l]-base.min[l],tl=tail.max[l]-tail.min[l],bw=base.max[w]-base.min[w],tw=tail.max[w]-tail.min[w];
 if(bl<L*.35||tl<L*.06||tl>L*.6||bl<tl*1.05)continue;
 const height=(tail.level-base.level)*base.sign;if(Math.abs(height)<.05||Math.abs(height)>H*.85)continue;
 const overlapW=Math.min(base.max[w],tail.max[w])-Math.max(base.min[w],tail.min[w]);if(overlapW<W*.3)continue;
 const tailAtStart=tail.min[l]<base.min[l];const gap=tailAtStart?base.min[l]-tail.max[l]:tail.min[l]-base.max[l];
 if(gap<-.15||gap>Math.max(8,L*.08))continue;
 const endDistance=tailAtStart?tail.min[l]-box.min[l]:box.max[l]-tail.max[l];if(endDistance>Math.max(2,L*.035))continue;
 const coverage=Math.min(1,(bl+tl)/L),widthCoverage=Math.min(1,Math.min(bw,tw)/W),fill=Math.min(1,(base.area+tail.area)/(bl*bw+tl*tw));
 const quality=coverage*.4+widthCoverage*.25+fill*.2+.15*(1-Math.min(1,gap/Math.max(8,L*.08)));
 // A tail's flat patch stops before a ramp/fillet. The requested length runs
 // from the part end to the shoulder's transverse edge, including the ramp.
 const shoulderPlanes=faces.filter(f=>f.mesh===base.mesh&&f.axis===h&&f.sign===base.sign&&f.id!==base.id&&f.id!==tail.id&&
 Math.abs(f.level-base.level)<=Math.min(.3,Math.abs(height)*.1)&&
 Math.min(f.max[w],base.max[w])-Math.max(f.min[w],base.min[w])>=overlapW*.8&&
 f.max[l]-f.min[l]<L*.1&&
 (tailAtStart?f.min[l]>=tail.max[l]-.02&&f.max[l]<=base.min[l]+.02:f.max[l]<=tail.min[l]+.02&&f.min[l]>=base.max[l]-.02));
 const shoulderChoices=shoulderPlanes.length?shoulderPlanes:[base];
 for(const shoulder of shoulderChoices){const transition=tailAtStart?shoulder.min[l]:shoulder.max[l],end=tailAtStart?box.min[l]:box.max[l];
 out.push({base,tail,shoulder,stepHeight:height,stepLength:Math.abs(transition-end),end,transition,gap,quality,tailAtStart,l,w,h});}
 }
 // Retain alternatives from distinct planes: a similar dimension is not evidence of identical intent.
 return out.sort((a,b)=>b.quality-a.quality||b.base.area-a.base.area).slice(0,20);
}
root.StepFeatures={extractPlanes,findCandidates};if(typeof module!=='undefined')module.exports=root.StepFeatures;
})(globalThis);
