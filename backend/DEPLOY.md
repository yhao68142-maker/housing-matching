# 共享零件库部署

当前交付的是可部署版本，尚未开通云服务器。GitHub Pages 继续承担网页；后台需部署到具有持久磁盘的单台 Linux 服务器并配置 HTTPS。不要使用会在休眠或重启后清空磁盘的临时容器。

## 本机验证（Windows）

从项目目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd backend
../.venv/Scripts/python.exe app.py admin --username admin
../.venv/Scripts/python.exe app.py serve
```

管理员密码通过隐藏输入设置，不放进源码、聊天或 GitHub。密码至少 12 位。后台默认地址 `http://127.0.0.1:8787`，仅监听本机。另一个终端在项目目录构建网页并启动：

```powershell
npm ci --ignore-scripts
npm run build
python -m http.server 8765 --bind 127.0.0.1 --directory dist
```

本机测试时将 `dist/cloud-config.js` 中地址设置为 `http://127.0.0.1:8787`，打开 `http://127.0.0.1:8765`。源码中的 `cloud-config.js` 保持空值，直到云端可用。不要将本机地址发布到线上。

## Linux / Docker

```sh
cd backend
docker compose up -d --build
docker compose exec api python app.py admin --username admin
```

容器以非 root 身份运行；命名卷 `housing-data` 保存数据库、产品、原始文件、账号及操作记录。部署升级不要执行 `docker compose down -v`，否则会删除数据卷。

在服务器的 HTTPS 反向代理中将 API 域名转发到 `127.0.0.1:8787`。示例 Nginx 配置片段（放入已有 HTTPS server，证书由部署平台配置）：

```nginx
location /api/ {
    client_max_body_size 31m;
    proxy_read_timeout 180s;
    proxy_pass http://127.0.0.1:8787;
    proxy_set_header Host $host;
}
```

`ALLOWED_ORIGINS` 必须包含网页来源 `https://yhao68142-maker.github.io`（不带仓库路径）。新增域名时同步修改。后台并不信任转发 IP 请求头；代理后的登录限流会共享代理 IP。生产代理应额外按真实客户端 IP 对 `/api/login` 限流。

后台 `/api/health` 正常后，设置源码 `cloud-config.js` 中 `HOUSING_API_URL` 为真实 HTTPS API 地址，并更新 index.html 中 cloud-config.js 的版本参数，再提交到 GitHub。页面会自动加载云端库取代内置匹配库。新后台首次启动导入原有 141 条记录；不会在重启时重复导入，也不会恢复已删除记录。

## 用户与使用

- 访客：公开读取产品尺寸、名称、机种、版本、备注，以及参与匹配；不能下载 3D，也不能写入。
- 编辑账号：由管理员创建；允许保存、编辑、回收、恢复产品及下载原始文件。没有公开注册入口。
- 管理员：另可创建账号、停用、重置密码、导出备份。重置密码或停用会撤销账号所有会话。管理员自己的密码通过上述服务器 `admin` 命令重置。
- 登录有效期 8 小时。令牌只在页面内存中，刷新网页后重新登录；服务器仅保存令牌摘要。
- 新增必须附原始文件，修改可保留原文件或上传替换。SLDPRT 可以保存，但自动测量仍需 STEP/STL，SLDPRT 尺寸手动输入。
- 相同编号与版本不可重复；编辑带修订号，发生冲突需刷新重新编辑。移入回收站后退出公开匹配，授权账号可恢复。
- 原表记录版本以 `原表-行号` 标记，避免历史同编号数据被合并；可由编辑账号逐条补全。

## 备份与恢复

页面管理员“导出完整备份 ZIP”：导出 `records.json`、`audit.json` 与全部原始文件（含回收站）。不包含用户账号及密码摘要，适合资料归档与迁移。此版本不提供网页批量导入 ZIP。

用于灾难恢复的完整备份请执行（支持服务运行时一致性快照）：

```sh
docker compose exec api python maintenance.py backup /data/backups/2026-10-15.sqlite3
docker compose cp api:/data/backups/2026-10-15.sqlite3 ./2026-10-15.sqlite3
```

完整 SQLite 备份包含账号、密码摘要、操作记录、回收站及 3D 文件，必须保存在私有位置。每次使用不同文件名，再复制到独立磁盘/私有存储。当前未自动安排定时备份，开通服务器后应配置定时任务和容量告警。

恢复：停止后台；先保留现有数据库及 `-wal`、`-shm` 文件，将它们一起移到安全位置。然后在相同 DATA_DIR 环境下运行：

```sh
python maintenance.py restore /path/to/backup.sqlite3
```

只有目标数据库不存在时才允许恢复；校验完整性后恢复，并清空登录会话。启动服务，核对记录数、下载文件及账号登录。

## 验证与容量

```sh
python -m unittest -v test_api.py
```

项目根目录运行 `npm test` 验证尺寸算法，`npm run build` 构建前端。集成测试验证未登录/普通编辑越权、账号撤权、增删改查、并发修订冲突、原文件下载、备份和历史数据导入。

本版使用单节点 SQLite，将文件与记录一起事务提交，避免孤立上传文件。每文件最多 30 MB。完整 ZIP 导出在内存中构建，适用于初期小规模库；大库应使用服务器 SQLite 备份，并在容量增长后迁移对象存储、分页检索和后台导出队列。不要在多个服务器间共享 SQLite 文件或使用无持久磁盘的部署。

密码使用 PBKDF2-SHA256 600,000 次迭代、随机盐；参考 [OWASP 密码存储指导](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。数据库一致性备份使用 [Python SQLite backup API](https://docs.python.org/3/library/sqlite3.html)。
