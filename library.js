'use strict';
(() => {
 const apiBase=(window.HOUSING_API_URL||'').replace(/\/$/,'');
 let session=null, online=false, rows=[], trashMode=false, editing=null, busy=false;
 const panel=document.createElement('section');panel.id='library';panel.className='card database';
 panel.innerHTML=`<div class="section-title"><span class="number">04</span><h2>共享零件库</h2><span id="cloud-state" class="muted" role="status"></span></div>
 <p class="help">公开查询与匹配。授权账号登录后可保存产品、下载原始 3D 和维护资料；管理员负责授权账号。尺寸单位 mm。</p>
 <div id="cloud-unconfigured" class="note" hidden>共享库尚未连接云端，当前仍可使用内置库进行匹配。部署后台后即可启用账号和永久保存。</div>
 <form id="cloud-login" class="toolbar"><label>用户名<input id="login-user" autocomplete="username" required maxlength="40"></label><label>密码<input id="login-pass" type="password" autocomplete="current-password" required maxlength="128"></label><button type="submit">登录</button></form>
 <div id="cloud-session" class="toolbar" hidden><strong id="session-name"></strong><button id="cloud-logout">退出登录</button><button id="cloud-new">保存当前零件</button><button id="cloud-trash">查看回收站</button><button id="cloud-backup" hidden>导出完整备份 ZIP</button></div>
 <p id="cloud-message" class="help" role="status" aria-live="polite"></p>
 <div class="toolbar"><input id="cloud-search" type="search" placeholder="搜索编号、名称、机种、版本、备注" aria-label="搜索共享零件库"><button id="cloud-refresh">刷新共享库</button><span id="cloud-count"></span></div>
 <div class="table-wrap"><table><thead><tr><th>编号 / 名称</th><th>机种 / 版本</th><th>长 × 宽</th><th>台阶高 / 长</th><th>原始文件</th><th>操作</th></tr></thead><tbody id="cloud-rows"></tbody></table></div>
 <section id="account-panel" hidden><h3>账号授权</h3><p class="help">仅管理员可创建账号。停用或重置密码后，该账号原来的登录立即失效。</p><form id="account-form" class="toolbar"><label>新用户名<input id="account-user" required pattern="[a-zA-Z0-9_.-]{3,40}" maxlength="40" autocomplete="off"></label><label>初始密码<input id="account-pass" type="password" minlength="12" maxlength="128" required autocomplete="new-password"></label><button>创建授权账号</button></form><div id="account-list"></div></section>
 <dialog id="part-dialog"><form id="part-form"><h2 id="part-title">保存零件</h2><div class="fields">
 <label>零件编号<input id="part-part" maxlength="160" required></label><label>产品名称<input id="part-name" maxlength="200" required></label><label>机种<input id="part-model" maxlength="200"></label><label>版本<input id="part-version" maxlength="80" required placeholder="例如 V02"></label>
 <label>长度<input id="part-length" type="number" step="any" min="0.000001" required></label><label>宽度<input id="part-width" type="number" step="any" min="0.000001" required></label><label>台阶高度<input id="part-stepHeight" type="number" step="any"></label><label>台阶长度<input id="part-stepLength" type="number" step="any" min="0"></label></div>
 <label>备注<textarea id="part-notes" maxlength="4000" rows="3"></textarea></label><label>原始 3D 文件<input id="part-file" type="file" accept=".step,.stp,.stl,.sldprt"></label><p id="part-file-note" class="help"></p><p class="help">保存前请核对四项尺寸；未知台阶尺寸留空。相同编号可以通过不同版本保存。</p><p id="part-error" role="alert"></p><div class="toolbar"><button id="part-save" class="primary" type="submit">确认并保存到共享库</button><button id="part-close" type="button">取消</button></div></form></dialog>
 <dialog id="password-dialog"><form id="reset-form"><h3>重置授权账号密码</h3><label>新密码<input id="reset-pass" type="password" minlength="12" maxlength="128" required autocomplete="new-password"></label><p id="reset-error" role="alert"></p><div class="toolbar"><button>保存新密码</button><button type="button" id="reset-close">取消</button></div></form></dialog>`;
 document.querySelector('footer').before(panel);
 const nav=document.createElement('a');nav.href='#library';nav.textContent='共享零件库';document.querySelector('nav').append(nav);
 const save=document.createElement('button');save.type='button';save.textContent='保存当前零件到共享库';save.className='text-button';save.onclick=()=>{$('library').scrollIntoView({behavior:'smooth'});if(session&&online)openEditor();else message('请先连接云端并使用授权账号登录');};$('match-form').append(save);
 function message(t){$('cloud-message').textContent=t;}
 function access(){
  $('cloud-login').hidden=!!session||!apiBase;$('cloud-session').hidden=!session;
  $('session-name').textContent=session?session.username+' · '+(session.role==='admin'?'管理员':'授权编辑'):'';
  $('account-panel').hidden=session?.role!=='admin';$('cloud-backup').hidden=session?.role!=='admin';
  $('cloud-new').disabled=!online;$('cloud-trash').disabled=!online;
 }
 async function requestAPI(path,options={}){
  if(!apiBase)throw Error('尚未配置共享库后台地址');
  const headers={...options.headers};if(session)headers.Authorization='Bearer '+session.token;
  const res=await fetch(apiBase+'/api'+path,{...options,headers,signal:AbortSignal.timeout(path==='/backup'?180000:90000)});
  if(!res.ok){let error;try{error=(await res.json()).error;}catch{error='后台请求失败（'+res.status+'）';}if(res.status===401){session=null;access();render();}throw Error(error);}
  return res;
 }
 const jsonOptions=(method,data)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 function combined(records){$('database-source').textContent='当前使用共享零件库：包含原表导入记录与新增产品。删除的记录不参与匹配。详细产品资料与维护操作见下方共享零件库。';db.splice(0,db.length,...records);$('total').textContent=db.length;renderDB();invalidate();}
 async function refresh(){
  try{
   const data=await (await requestAPI('/parts')).json();combined(data.records);online=true;
   rows=trashMode?(await (await requestAPI('/trash')).json()).records:data.records;
   $('cloud-state').textContent='已连接 · '+new Date().toLocaleTimeString();render();access();
  }catch(e){online=false;$('cloud-state').textContent='未连接 / 数据可能不是最新';access();throw e;}
 }
 function render(){
  const q=$('cloud-search').value.trim().toLowerCase();const visible=rows.filter(r=>[r.part,r.name,r.model,r.version,r.notes].join(' ').toLowerCase().includes(q));
  $('cloud-count').textContent=(trashMode?'回收站 ':'')+visible.length+' 条';$('cloud-trash').textContent=trashMode?'返回零件库':'查看回收站';
  $('cloud-rows').innerHTML=visible.map(r=>`<tr><td><strong>${esc(r.part)}</strong><div>${esc(r.name)}</div><details><summary>查看详情</summary><p>${esc(r.notes||'无备注')}</p><p>更新：${esc(new Date(r.updated*1000).toLocaleString())}</p></details></td><td>${esc(r.model)}<div>${esc(r.version)}</div></td><td>${fmt(r.length)} × ${fmt(r.width)}</td><td>${fmt(r.stepHeight)} / ${fmt(r.stepLength)}</td><td>${esc(r.filename||'未附文件')}${r.filename&&session?`<button data-action="download" data-id="${esc(r.id)}">下载 3D</button>`:''}</td><td>${!trashMode?`<button data-action="measure" data-id="${esc(r.id)}">用此尺寸匹配</button>`:''}${session?(trashMode?`<button data-action="restore" data-id="${esc(r.id)}">恢复</button>`:`<button data-action="edit" data-id="${esc(r.id)}">编辑</button><button data-action="delete" data-id="${esc(r.id)}">移入回收站</button>`):'<span class="muted">登录后可维护</span>'}</td></tr>`).join('')||'<tr><td colspan="6">'+(online?'没有符合条件的记录':'连接后台后显示共享资料')+'</td></tr>';
 }
 function openEditor(r=null){
  if(!session||!online){message('请先连接后台并登录');return;}
  editing=r;$('part-form').reset();$('part-error').textContent='';$('part-title').textContent=r?'编辑产品资料':'确认尺寸并保存零件';
  for(const k of ['part','name','model','version','notes',...keys])$('part-'+k).value=r?.[k]??(keys.includes(k)?$(k).value:'');
  $('part-file-note').textContent=r?'现有文件：'+(r.filename||'无')+'。不选新文件则保留原文件。':lastFile?'将保存当前文件：'+lastFile.name:'请选择原始 3D 文件（最大 30 MB）。';
  $('part-dialog').showModal();
 }
 $('part-close').onclick=()=>{if(!busy)$('part-dialog').close();};$('part-dialog').addEventListener('cancel',e=>{if(busy)e.preventDefault();});
 $('cloud-new').onclick=()=>openEditor();
 $('part-form').onsubmit=async e=>{
  e.preventDefault();if(busy)return;
  const metadata={};for(const k of ['part','name','model','version','notes'])metadata[k]=$('part-'+k).value;
  for(const k of keys)metadata[k]=$('part-'+k).value===''?null:Number($('part-'+k).value);
  if(editing)metadata.revision=editing.revision;
  const file=$('part-file').files[0]||(!editing?lastFile:null);
  if(!editing&&!file){$('part-error').textContent='请选择需要保存的原始 3D 文件';return;}
  if(file&&(!file.size||file.size>30*1024*1024)){$('part-error').textContent='文件须非空且不超过 30 MB';return;}
  const form=new FormData();form.append('metadata',JSON.stringify(metadata));if(file)form.append('file',file);
  busy=true;$('part-save').disabled=true;$('part-close').disabled=true;$('part-error').textContent='正在上传并保存，请稍候…';
  try{await requestAPI('/parts'+(editing?'/'+encodeURIComponent(editing.id):''),{method:editing?'PUT':'POST',body:form});$('part-dialog').close();message('已保存。此零件已加入共享库并参与匹配。');try{await refresh();}catch{message('保存成功，但刷新失败，请点击刷新共享库。');}}
  catch(err){$('part-error').textContent=err.message+'；如网络中断，请先刷新共享库确认是否已保存，再重试。';}
  finally{busy=false;$('part-save').disabled=false;$('part-close').disabled=false;}
 };
 async function download(path,name){const blob=await(await requestAPI(path)).blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),60000);}
 $('cloud-rows').onclick=async e=>{
  const b=e.target.closest('button[data-action]');if(!b)return;const r=rows.find(r=>r.id===b.dataset.id);if(!r)return;b.disabled=true;
  try{switch(b.dataset.action){
   case 'measure':stop();clearModel();lastFile=null;$('file').value='';keys.forEach(k=>$(k).value=r[k]??'');$('file-status').textContent='已填入共享库记录：'+r.part;invalidate();$('match-form').requestSubmit();$('workspace').scrollIntoView();break;
   case 'edit':openEditor(r);break;
   case 'download':await download('/parts/'+encodeURIComponent(r.id)+'/file',r.filename);break;
   case 'delete':case 'restore':if(!confirm((b.dataset.action==='delete'?'将此零件移入回收站？可随后恢复。':'恢复此零件到共享库？')+'\n'+r.part+' / '+r.version))break;await requestAPI('/parts/'+encodeURIComponent(r.id)+'/'+b.dataset.action,jsonOptions('POST',{revision:r.revision}));await refresh();message('操作成功');break;
  }}catch(err){message(err.message);}finally{b.disabled=false;}
 };
 $('cloud-search').oninput=render;$('cloud-refresh').onclick=()=>refresh().catch(e=>message(e.message));
 $('cloud-trash').onclick=()=>{trashMode=!trashMode;refresh().catch(e=>message(e.message));};
 $('cloud-login').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{session=await(await requestAPI('/login',jsonOptions('POST',{username:$('login-user').value,password:$('login-pass').value}))).json();$('login-pass').value='';access();render();message('登录成功。关闭或刷新网页后需重新登录。');await refresh();if(session.role==='admin')await accounts();}catch(err){message(err.message);}finally{b.disabled=false;}};
 $('cloud-logout').onclick=async()=>{try{await requestAPI('/logout',{method:'POST'});}catch(err){message('退出请求未确认，请关闭网页；会话最迟 8 小时失效。');}finally{session=null;trashMode=false;access();rows=rows.filter(r=>!r.deleted);render();$('part-dialog').close();$('password-dialog').close();}};
 $('cloud-backup').onclick=async()=>{const b=$('cloud-backup');b.disabled=true;message('正在生成包含原始文件的备份…');try{await download('/backup','Housing备份-'+new Date().toISOString().slice(0,10)+'.zip');message('备份已下载，请妥善保存。');}catch(err){message(err.message);}finally{b.disabled=false;}};
 let users=[],resetUser=null;
 async function accounts(){users=(await(await requestAPI('/users')).json()).users;$('account-list').innerHTML=users.map(u=>`<p><strong>${esc(u.username)}</strong> · ${u.role==='admin'?'管理员':u.active?'已授权':'已停用'} ${u.role==='editor'?`<button data-user="${esc(u.id)}" data-action="toggle">${u.active?'停用':'启用'}</button><button data-user="${esc(u.id)}" data-action="reset">重置密码</button>`:''}</p>`).join('');}
 $('account-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await requestAPI('/users',jsonOptions('POST',{username:$('account-user').value,password:$('account-pass').value}));$('account-form').reset();await accounts();message('授权账号已创建');}catch(err){message(err.message);}finally{b.disabled=false;}};
 $('account-list').onclick=async e=>{const b=e.target.closest('button[data-user]');if(!b)return;const u=users.find(x=>x.id===b.dataset.user);if(b.dataset.action==='reset'){resetUser=u;$('reset-form').reset();$('reset-error').textContent='';$('password-dialog').showModal();return;}if(!confirm((u.active?'停用':'启用')+'账号 '+u.username+'？'))return;try{await requestAPI('/users/'+u.id,jsonOptions('PUT',{active:!u.active}));await accounts();}catch(err){message(err.message);}};
 $('reset-close').onclick=()=>$('password-dialog').close();$('reset-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{await requestAPI('/users/'+resetUser.id,jsonOptions('PUT',{password:$('reset-pass').value}));$('reset-pass').value='';$('password-dialog').close();message('密码已重置，旧登录已失效。');}catch(err){$('reset-error').textContent=err.message;}finally{e.submitter.disabled=false;}};
 $('cloud-unconfigured').hidden=!!apiBase;$('cloud-refresh').disabled=!apiBase;$('cloud-state').textContent=apiBase?'正在连接…':'等待云端配置';access();render();
 if(apiBase)refresh().catch(e=>message(e.message+'。当前可继续使用内置库。'));
})();
