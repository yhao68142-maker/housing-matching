'use strict';
(() => {
 const offline=window.HOUSING_OFFLINE===true;
 const button=document.createElement('button');button.type='button';button.textContent=offline?'离线版 · 使用说明':'切换离线版';
 document.querySelector('header').append(button);
 const dialog=document.createElement('dialog');dialog.innerHTML=`<h2>${offline?'正在使用离线版':'切换到离线工作台'}</h2><p>离线版包含尺寸数据库、STEP/STL 解析器、红绿对比和加载进度，无需联网。</p><ol><li>首次联网时下载 Windows 离线包，也可由同事拷贝给你。</li><li>完整解压，双击 Housing-Offline.exe，保持启动器窗口打开。</li><li>点击“本地选择零件”，在电脑文件窗口中选择 STEP/STL。</li></ol><p class="note">离线版使用随包提供的数据库快照，不连接或同步共享库。文件只在本机内存中处理，关闭启动器后清除。公司如禁止运行本地程序或读取零件，请联系 IT 授权。</p>${offline?'':'<a class="primary offline-download" href="offline/Housing-Offline-Windows.zip" download>下载 Windows 离线包</a>'}<button type="button">关闭</button>`;
 document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();button.onclick=()=>dialog.showModal();
 if(!offline)return;
 document.querySelector('header>.pill').textContent='● 离线本机';
 const library=$('library');if(library)library.hidden=true;
 document.querySelectorAll('a[href="#library"]').forEach(a=>a.hidden=true);
 // Shared library has no offline backend. Hide saving instead of implying a backup was made.
 for(const b of $('match-form').querySelectorAll('button'))if(b.textContent.includes('保存当前零件'))b.hidden=true;
 $('drop').hidden=true;
 const choose=document.createElement('button');choose.type='button';choose.className='primary';choose.textContent='本地选择零件（无需网页上传）';$('file-status').before(choose);
 $('file-status').textContent='点击本地选择零件，或在离线启动器窗口中选择文件。';
 const info=document.createElement('p');info.className='note';info.textContent='离线模式：数据库为随包快照，文件不上传；保持离线启动器打开。';$('workspace').before(info);
 const localToken=location.pathname.split('/')[1];let lastId='',disconnected=false;
 choose.onclick=async()=>{choose.disabled=true;try{const response=await fetch('native/pick',{method:'POST',headers:{'X-Housing-Local':localToken}});if(!response.ok)throw Error();$('file-status').textContent='请在本地文件选择窗口中选择零件；如果未看到窗口，请切换到离线启动器。';}catch{$('file-status').textContent='无法连接离线启动器，请重新打开 Housing-Offline.exe。';}finally{choose.disabled=false;}};
 async function poll(){
  try{const res=await fetch('native/status',{signal:AbortSignal.timeout(5000)});if(!res.ok)throw Error();const item=await res.json();if(disconnected){disconnected=false;choose.disabled=false;}
   if(item.id&&item.id!==lastId){const response=await fetch('native/model/'+encodeURIComponent(item.id),{signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error();const bytes=await response.arrayBuffer();lastId=item.id;loadFile(new File([bytes],item.name));}
  }catch{if(!disconnected){disconnected=true;choose.disabled=true;$('file-status').textContent='离线启动器已关闭或连接中断，请重新打开启动器及网页。';}}
  setTimeout(poll,1500);
 }
 poll();
})();
