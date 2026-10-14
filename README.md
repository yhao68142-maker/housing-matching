# Housing 智能匹配

内置真实 Excel Housing 数据的静态网页。默认 141 条记录，无需反复上传 Excel。所有零件在浏览器本机处理，原始 CAD 文件不会上传。

## 使用

1. 选择 STEP/STP 或 STL（不超过 30 MB），或直接手动输入长度、宽度。
2. STL 无单位信息，选择导出时使用的单位。STEP 输出统一为毫米。
3. 自动测量模型坐标轴包围盒，默认最长轴为长、次长轴为宽，可以手动调整轴映射。斜放模型必须在 CAD 中对齐后导出；旋转预览不会改变测量。
4. 按原表定义补充台阶高度、台阶长度。不知道就留空。零值与未知不同，负台阶高度保留其符号。整体高度不能代替台阶高度。
5. 开始匹配，查看 TOP 10、各维差值、覆盖率和待核对提示；可导出 CSV。

SLDPRT 不在此静态版本的解析范围，请从 SolidWorks 另存为 STEP。没有浏览器端 SLDPRT 转换功能。STEP 使用 occt-import-js 0.0.23 的 OpenCascade WebAssembly，网格化参数为 0.01 mm 弦偏差，包围盒为网格近似值，不是工程公差认证结果。当前没有自动台阶、孔、槽或整体形状识别。

## 数据与评分

来源：Housing和连板&COC-尺寸统计.xlsx，Housing 第 3–143 行；源文件 SHA256 记录在 housing-data.js。填充仅发生在原有合并单元格范围，行号用作唯一标识，原序号的重复不造成覆盖。

保留原文和负值，未知尺寸为 null。11 条记录存在缺失台阶或异常数值提示，未擅自交换疑似填反的字段。Panel/COC 不属于本次 Housing 匹配库。原 Excel 中图片未内嵌，可按原行号回查图纸。

权重：长度 40、宽度 30、台阶高 20、台阶长 10。仅使用用户已填维度，误差 = min(abs(输入 − 库值) / 容差, 1)，库值缺失时误差为 1。得分 = 100 × (1 − 加权平均误差)。覆盖率为有库值维度的权重占比；分数不是概率。严格模式要求全部已填维度有库值且在容差内。同分按覆盖率、原表行排序，并不宣称唯一识别。

## 开发与发布

Node.js 22：`npm ci --ignore-scripts`、`npm test`、`npm run build`。将 dist 作为静态目录通过 HTTP 服务访问。运行时不依赖第三方 CDN，CAD 引擎随网站发布。

GitHub Pages 的 Source 选择 GitHub Actions。推送 main 后工作流测试、构建并发布 dist。首次需在 Settings → Pages 启用 GitHub Actions。网页与内置数据库是公开可访问的静态内容。

更新数据库：安装 Python openpyxl 后执行 `python scripts/convert.py path/to/source.xlsx .`，核对原文和异常标记，再提交 housing-data.js。当前转换器要求此版表格的 141 行，表格结构变化时需要同步调整校验。

第三方解析器：[occt-import-js](https://github.com/kovacsv/occt-import-js)，LGPL-2.1；其许可证随构建复制至 vendor/LICENSE.md。解析器保留为可替换的独立 JS/WASM 文件，未修改其源码。
