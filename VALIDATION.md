# Validation

## 2026-09-17 — KF6 V2 真实日志诊断与 GUI

本轮只修改 FLP。开始时 FLP/FCCG/GSHC 的 `git status --short` 均为空。
FLP 起始 HEAD `07835302709c9dcdebfbb6641a76b469c5d18e2e`；没有 commit/push。
FCCG HEAD `34e16ef282402e3800c20492b32255143c0da67b`、GSHC HEAD
`62656da1fa035bff344165c8857a932e644ddbae` 与状态均保持不变。
没有修改日志、decoder、工程 schema、固件、生产参数/门限、P0/Q/INS/姿态/部署/着陆。

### 修改文件与行为

- `plugins/algorithms/kf6/diagnostics.py`（位于 src/silverstar_flp，下同）：新增独立临时诊断选项、
  请求包装、5组量测权重审计和专用JSON导出，未向参数/schema增加字段。
- `plugins/algorithms/kf6/plugin.py`：复用正常resolver之后施加精确Baro R覆盖、速度时移及冻结初始化；
  diagnostics/provenance明确Analysis-only。无覆盖的原路径保持不变。
- `plugins/algorithms/kf6/filter.py`：分析开关真正跳过GNSS pU，E/N仍执行原更新。
- `plugins/algorithms/kf6/field_analysis.py`：复用扫描，补充zero/best/improvement/采样谷宽和结果元数据，
  子回放共享取消事件，避免嵌套进度倒退。
- `ui/offline_diagnostics.py`：KF6子页、双语模式/结果摘要、量测表、后台操作入口、Reset Charts和JSON导出。
- `ui/pages/replay.py`：仅增KF6子tab、请求分发、模式标签和忙状态；同一数据集完成复算后保留参数草稿。
- `ui/main_window.py`：沿用FunctionWorker/QThreadPool、进度/取消/错误处理；工程保存不持久化分析结果配置。
- `core/analysis_source.py`、`ui/pages/charts.py`：传递临时Analysis-only来源标签。
- `export/service.py`：普通导出保留诊断元数据、来源及Full-P标签。
- `i18n/en_US.json`、`i18n/zh_CN.json`：诊断文字、单位、时移方向和原点项/覆盖边界。
- `tests/test_offline_diagnostics.py`：数值行为、隔离、合成时延、后台线程和四种语言主题组合回归。
- `docs/KF6_FIELD_ANALYSIS.md`、`docs/GUI_STYLE_GUIDE.md`、本文件：行为契约及验收。

GUI入口：复算→选择KF6→高级离线诊断；不增加第六个主页面。
默认Firmware-faithful。自动扫描仅展示结果，Apply Best才应用到当前analysis并回放。
手动shift=0保留完整原调度；自动扫描0档与其他shift共享内部窗口，二者评分窗口不同。
Baro覆盖为精确sigma²，不叠加原点项；禁用pU不使用巨大R。
Restore清除临时值/开关/scan，已经完成的Analysis-only结果继续保持原标签。
正常项目参数草稿可保存，临时shift/Baro覆盖/pU禁用均不进入.ssflp或decoder。

### 测试覆盖与限制

新增测试含7个pytest case（其中4个为中英文×深浅色组合），覆盖提示词18项：

| 要求 | 验证 |
| --- | --- |
| 默认模式/覆盖关闭/shift0（1–3） | GUI真实控件初始值 |
| 手动真实平移/恢复（4–5） | KF6状态确实变化；去掉覆盖后与基线逐位相同 |
| 合成已知latency（6） | +80ms信号恢复到−80ms±5ms；进度单调并完成 |
| Apply Best隔离（7） | Scan不改选项；显式Apply后才发replay请求 |
| Baro有效R/恢复（8–9） | native R25→分析R4；KF6实际通道R4；恢复原输出 |
| pU跳过/E-N不变（10–11） | pU更新数和NIS样本数0；E/N状态逐位相同 |
| 工程/decoder/Recorded隔离（12–14） | 真实_Project_Write、decoder SHA256、原日志SHA256、记录参数和原生variance未变 |
| 导出标签（15） | JSON analysis_only字段及AlgorithmResult.provenance；拒绝覆盖已存在导出文件 |
| GUI后台计算（16） | 线程ID与主线程不同、QTimer继续tick、禁重复、成功/异常/取消后恢复 |
| 中英文/主题/布局（17–18） | Qt offscreen四组合，1000×700尺寸、无页面横向溢出，截图人工复核 |

Windows offscreen QPA未自动发现字体，截图测试显式只读加载系统微软雅黑，并验证“中”字有字形；
未改产品字体或系统字体配置。Qt offscreen不支持QOpenGLWidget，未宣称实体CF-33触摸或OpenGL硬件验收。
初次compileall递归进入历史pytest产物，遇到清理测试故意写入的无效`preserve-or-clean`代码；
未修改/删除这些产物，最终源码检查排除隐藏测试输出目录。

完成检查：

- `.venv/Scripts/python.exe -m pytest -q --basetemp=tests/.pytest-v2-final -o cache_dir=tests/.pytest-cache-v2`：
  **287 passed, 8 skipped，110.54s**。8项分别为历史SS0000、SS0007、SS0014及SS_TEST_0手动数据gate，
  未设置各自精确匹配环境变量，不能拿本轮同名SS0007或合成数据替代。
- `.venv/Scripts/python.exe -m ruff check src tests tools`：通过。
- `PYTHONPYCACHEPREFIX=tests/.compile-v2-cache`，
  `.venv/Scripts/python.exe -m compileall -q -x '[\\/]\.' src tests tools`：通过。
- `git diff --check`：通过。去掉无关格式变化时逐块验证AST完全一致，未整文件回退。

### 真实日志V2证据

输出仅在用户指定的新目录：
`D:/stm32_project/SS_0_5_TEST_0/LOG/KF6_PARAMETER_OPTIMIZATION_V2/`。
主报告`KF6_PARAMETER_OPTIMIZATION_V2.md`，交互报告`VU_LATENCY_INTERACTION.md`，
冲击报告`SS0008_IMPACT_RECOVERY.md`，全部要求的CSV、逐日志JSON/NPZ/Markdown及8张PNG已生成。
V1及输入共1994文件SHA256前后一致。未改原固件参考工程。

- 四条真实日志SS0005–8，exact decoder 1.2配对，APPROXIMATE复算，不宣称旧固件bit-exact或Host Golden已验证。
- 54位置配置×4日志=216回放；12组latency共684回放；3时序×7速度倍率×4日志=84回放。
  另有4基线、24次气压floor等效性验证和同shift参照回放；主计数不冒充全部运行总次数。
- native Baro variance25导致配置sigma1.5/2/2.5/3/4/5均等效，24次状态逐位相同。
- 位置稳定区域选择GNSS pU2.5 / Baro有效sigma2.5；vU scale1、shift0下聚合分0.935264。
- B位置候选最优shift分别−255/−375/−290/−220 ms；median−272.5、IQR65、MAD35、range155 ms，同号100%。
  timing mismatch证据YES；固定固件补偿依据NO。common诊断shift−270ms。
- 三时序最低分scale均2.0；唯一外场验证候选采用邻近稳定点1.75、GNSS pU2.5、Baro有效2.5、shift0、outage300。
  完整候选**NOT CURRENTLY IMPLEMENTABLE**，因当前native floor5；不把离线覆盖包装成可下发字段。
- SS0008候选末段vU RMS0.2997，相对基线0.2663增加12.6%，同时回高残差绝对值2.6797降至1.3167m。
  最低总分不代表所有指标改善。单例报告不被普通日志平均掩盖。
- GNSS最大epoch间隔46.975/46.203/47.240/47.986ms，无>300ms outage；基线/位置/速度扫描均无误inflation。
  保持outage300不重新优化。
- 一份当前默认固件足够用于下一轮采集/离线候选比较；不表示这个完整候选已可部署。机上六项默认不变。

## 2026-09-17 — 外场前工程默认根目录一致性收尾

本节是本轮路径修改的验收；下方较早的 KF6 修改记录属于历史基线，不是本轮改动。
初始 HEAD：`98cc422`；初始 `git status --short` 为空。
只改 FLP 工程文件对话框路径；没有 commit/push，没有删除、覆盖用户未提交内容。
GSHC 无改动。与 FCCG 独立实现，不增加跨仓库依赖。

### 文件与原因

- `src/silverstar_flp/core/path_preferences.py`：给已有 PathPreferences 添加
  `DefaultProjectRoot_EffectiveGet`，共享有效配置 → Documents → Home → cwd 的现存目录 fallback。
  不增加设置系统、字段或 schema；读取不创建目录、不回写偏好。
- `src/silverstar_flp/ui/main_window.py`：New/Open/Save As 与默认根目录选择入口复用 helper。
  Open 不再固定 Home；Save As 不再沿用旧工程所在目录或 cwd，而是新 root + 原文件名。
  首次 Save 补用已有 _Overwrite_Confirm，拒绝覆盖时不写文件；已有项目的普通 Save 不变。
- `tests/test_path_preferences.py`：拦截 QFileDialog/NewProjectDialog，验证实际入口的建议路径、
  Unicode、取消无副作用、缺失/损坏/空/相对/已删除/文件/缺失磁盘偏好。
  比较工程序列化前后、偏好原始字节和既有工程内容，保持普通 Save、导入、导出规则。
- `docs/GUI_STYLE_GUIDE.md`：补充工程路径规则。
- `VALIDATION.md`：本轮验收记录。

### 最终规则

假设默认目录为 D:/SilverStarFlightLogs：
New 保持 <root>/<name>/<name>.ssflp；Open 从 root 开始；
旧路径 D:/Other/Flight_001.ssflp 的 Save As 建议为
D:/SilverStarFlightLogs/Flight_001.ssflp，未保存工程建议 flight.ssflp。
Unicode 文件名原样保留，用户仍可选择其他目标；普通 Save 写当前文件。
Open/Save As 不静默修改默认目录。无效偏好只选择现存 fallback，不创建任何目录。
新建工程在用户接受目标后创建目录的原有流程不变。

日志导入仍优先当前/待建工程目录；结果仍按 ExportDirectory_Default 放在工程或日志旁的
Result_<logstem>，不会集中到默认根目录顶层。既有覆盖确认、项目兼容校验、单日志引用均保留。

### 检查结果

- 定向：
  `.venv/Scripts/python.exe -m pytest tests/test_path_preferences.py tests/test_project_export.py tests/test_gui_smoke.py -q --basetemp=tests/.pytest-root-focus-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **36 passed, 42.13 s**。
- 全量：
  `.venv/Scripts/python.exe -m pytest tests -q --ignore-glob='tests/.pytest-*' --basetemp=tests/.pytest-root-full-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **280 passed, 8 skipped, 75.27 s**，日志 `tests/.pytest-root-full-20260917.log`。
  跳过：SS0000 一项、SS0007 三项、SS0014 一项、SS_TEST_0 三项，
  均因指定的真实日志未提供；本轮未伪造实测验证。
- 将无效盘符 fixture 加强为机器上实际缺失盘符后：
  `.venv/Scripts/python.exe -m pytest tests/test_path_preferences.py -q --basetemp=tests/.pytest-root-drive-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **12 passed, 2.86 s**。随后为首次 Save 补充覆盖确认，最终重跑见下。
- `.venv/Scripts/python.exe -m ruff check --no-cache src tests tools --exclude '.pytest-*' --output-format concise`：
  **All checks passed**。仅修复新增测试的导入顺序与长行，没有批量格式化源代码。
- `.venv/Scripts/python.exe -m compileall -q src`：通过；
  PYTHONPYCACHEPREFIX 限 tests/.pytest-root-compile-20260917。
- 最终完整运行（含首次 Save 覆盖确认）：
  `.venv/Scripts/python.exe -m pytest tests -q --ignore-glob='tests/.pytest*' --basetemp=tests/.pytest-root-final-20260917 -o cache_dir=tests/.pytest-root-cache-20260917`：
  **280 passed, 8 skipped, 68.91 s**；日志 `tests/.pytest-root-final-20260917.log`。
  跳过原因同上。覆盖确认定向检查 **12 passed, 2.87 s**；最终 Ruff 通过。
- `git diff --check`：通过。没有为本轮新增 mypy 等强制工具。
- 所有对话框测试拦截 exec/静态选择方法，没有弹出真实文件选择框；不声明实体 GUI/硬件验收。

### 未修改的问题与边界

未修改 KF6/GNSS/INS、reacquisition、NIS、任何算法默认参数、
.ssflp v3/schema、FCCG project/schema、protocol、日志格式或 decoder。
GNSS CONFIG READ/SHOW 的既有差异没有在本轮诊断或修复，按提示词留待新固件外场复核。
没有发现需要在本轮顺手修改的其他产品问题。最终工作区保留上述文件的未提交修改，不 push。


## 2026-09-17 — KF6 outage、独立 U 速度权重、离线扫描与工程工作流

初始 HEAD：`2a301d8c6c0c7f37568998acc675a0c5d68b9d3c`；初始 `git status --short` 为空。
本轮按附件分别本地中文提交，不 push；未 reset/checkout/clean。FLP 0.0.2、.ssflp v3、
decoder/project-semantics 1.2、算法参数 schema 1.0 均未升级，无 FCCG/GSHC 运行时依赖。
详细行为与 CLI 见 [KF6 分析与工程路径](docs/KF6_FIELD_ANALYSIS.md)。

### 改动与兼容结论

- Python KF6 同步 C：position EN/U、velocity EN/U 各自跟踪有效时间戳和恢复状态；
  连续有效 GNSS 即使 hard reject 仍刷新可用性，不触发 inflation。
  仅严格超过 outage 阈值才允许恢复；正常融合返回直接解除，无需膨胀。
  真掉线后五次 hard reject + 三个一致间隔可启动 DPD'，factor=2、间隔五次 reject、
  上限八次与三次融合退出保持。重复掉线/非法数据/重复和回退时间戳有回归覆盖。
- 新增 `gnss_reacquire_outage_ms`（整数，默认 300）和
  `gnss_velocity_vertical_scale`（默认 1）；保留既有 `gnss_velocity_std`。
  EN sigma=max(receiver sigma*1.25, floor)，U 再乘独立 scale，R 平方；
  receiver uncertainty 不被固定 R 代替。P0、Q、NIS 阈值、gravity、INS/姿态保持。
- Barometer 直接更新 pU，通过交叉协方差间接修正 vU；GNSS pU、vU 分别量测更新。
  正式默认仍为 GNSS pU floor 2.5 m、Barometer 5 m、velocity floor 0.15 m/s、U scale 1。
  这些是兼容的保守候选，不是本轮新证明的飞行最佳参数。
- 旧工程只接受精确的旧 KF6 参数身份，只有两个新字段允许缺失 fallback；
  原有必需参数缺失仍报错。Recorded Configuration 不可变，What-if 使用独立实际值，
  int 参数保持整数。旧 GNSS 日志使用新恢复策略明确标为 approximate；
  不能把新策略宣称为旧固件 exact replay。新实际参数继续走原 exact matching 和哈希校验。
- 保留 GNSS NIS max(EN 2D,U 1D) 展示、稀疏 PRE-FLIGHT、时间戳匹配、Pure INS、full P、
  replay cadence、导出。未改 AIR/GSP、SSLOG、FCCG project 12、部署或着陆逻辑。

### 离线能力与证据边界

`tools/kf6_field_analysis.py --pair LOG DECODER [--pair ...] --output NEW_DIRECTORY`
对每个日志独立 exact-pair 打开与复算，前后核对源 SHA256，输出逐日志 JSON 和 comparison.json。
无多日志 .ssflp schema 或跨仓库运行时依赖。扫描使用实际 KF6：

| 扫描 | 候选 |
| --- | --- |
| 恢复门禁 | 旧 reject-only comparator / 新 outage-required |
| outage | 160 / 200 / 250 / 300 / 500 ms |
| GNSS pU floor | 2.5 / 3 / 4 / 5 / 6 m |
| Barometer floor | 1.5 / 2 / 3 / 5 m |
| velocity U scale | 1 / 1.25 / 1.5 / 2 |
| velocity latency | -500…+500 ms，20 ms coarse，最优附近 5 ms refinement |

延迟扫描在原 GNSS epoch 网格上重采样 velocity 和 receiver variance，正值表示延后，
所有候选使用共同内部时间窗，不越过大 source gap、不外推。position/Baro/IMU 时间不变；
每个候选重跑 KF6。这是 approximate 离线试验，不是 OOSM，也不是简单移动结果曲线。
评分为实际 EN/U hard 阈值归一化 p95 NIS 与 hard-reject 比例。
INITIAL_STATE/P0 冻结仅限显式 analysis；正常 What-if 仍保留初始化证据门禁。
缺少匹配 native uncertainty 时 R sweep 明确 unavailable，不虚构固定方差。

统计含逐组 accept/soft/hard/invalid/numeric、NIS max/p50/p90/p95/p99、inflation 次数、
最终 p/v、P 对角峰值、同时间戳 Recorded residual 与 Pure INS。
Recorded residual 不是 ground truth；静止 RMSE 只在显式已知区间计算，
reference RMSE 只在有参考序列时计算，否则 null。

合成验证：

- 已知 +80 ms velocity 延迟，57 次实际重跑找回 **-80 ms**，score=0。
- 连续 fresh GNSS 拒绝对照：新策略四组 inflation=[0,0,0,0]；
  旧 comparator=[0,0,5,0]。这说明旧策略会把动态不一致当作恢复，不表示旧输出更准确。
- 显式 native uncertainty 合成 fixture 覆盖全部权重候选；U scale=1.5 时对应 R×2.25，
  EN 不变；缺 native 的 fixture 如实拒绝权重重建。
- 输出在 `tests/.pytest-closeout-0917/` 下相应 test 目录：
  `latency_synthetic.json`、`continuous_rejection_comparison.json`、
  `native_weight_sweeps.json` 和 `c_python_equivalence.json`。

三仓库、D:/python_software 与用户 Desktop 搜索未找到真实 SS0005–SS0008 BIN/SSLOG；
少数历史测试缓存 ACL 不可读。**未执行真实 SS0005–8 baseline/A/B**。
四组真实日志的最佳 shift、手持最优参数均未知；无稳定物理延迟证据，
不支持 firmware compensation，本轮没有加入固定补偿。地面候选不能自动推广为火箭飞行参数。

### 工程工作流示例

默认根目录 JSON 位于应用 AppLocalDataLocation 下 `path_preferences.json`，UTF-8、原子 replace、
schema_version=1。独立于 .ssflp 和 compatibility hash。坏 JSON、缺失文件/根目录安全 fallback；
设置偏好不创建未确认的大目录。名称自动跟随，实际手改或 Browse 后使用所选目录本身。

例如默认 root=`D:/SilverStarFlightProjects`、name=`FieldTest_0917`：

```text
D:/SilverStarFlightProjects/FieldTest_0917/
├─ FieldTest_0917.ssflp
├─ SS0005.BIN
├─ SS0006.BIN
├─ Flight.ssdecoder
├─ Result_SS0005/
└─ Result_SS0006/
```

这表示同一目录可依次处理不同日志；.ssflp 仍只保存一个当前日志。
Import 默认 folder_search，当前或待建工程目录优先，打开另一工程时刷新；
无工程按 default root → 最近成功导入目录 → 安全现存目录。
Browse 从当前搜索目录开始，manual pair 仍可用且语言切换不丢模式。
默认 Result_<logstem> 正确处理 BIN/SSLOG 大小写、中文/空格/括号；Windows 非法字符替换。
碰撞自动 _2/_3，手工目的地保持；非空导出目录拒绝，不覆盖旧结果。
新工程接受路径时创建子目录，取消后续导入不留下 .ssflp；Save/Open 原路径语义保留。

### 数值等价与测试

C 真实生成 fixture 十场景×64帧=640帧，FLP 使用独立仓库本地固定数据。
最大 position deviation=**7.499018093992671e-09 m**；
velocity=**4.881515330845687e-11 m/s**；
P=**3.7143001591077862e-09**。
所有恢复状态/计数逐帧相同；C 文本序列化精度带来这些差异，符合 float32 等价。

- `.venv/Scripts/python.exe -m pytest tests -q --basetemp=tests/.pytest-closeout-0917 --ignore-glob='tests/.pytest-*' -o cache_dir=tests/.pytest-cache/0917`：
  **272 passed, 8 skipped, 62.42 s**，日志 `tests/.pytest-cache/0917-closeout.log`。
  覆盖 KF、replay、参数、NIS、sparse preflight、比较、export、GUI、路径/导入/结果目录。
- 跳过八项：SS0000 一项、SS0007 三项、SS0014 一项、SS_TEST_0 三项；
  缺少各自 hash-locked 实测日志与 decoder，不能伪造通过。
- `.venv/Scripts/python.exe -m ruff check --no-cache src tests tools --exclude '.pytest-*' --output-format concise`：通过。
  排除一次性测试输出中故意非法的 fixture，不排除正式源/测试。
- `git diff --check`、`git diff --cached --check`：通过。
- Qt offscreen Light/Dark × zh_CN/en_US 新工程对话框渲染，测试进程加载 Windows 字体；
  检视英文 Dark、中文 Light 无裁切，图在 `tests/.pytest-visual-0917/`。
  未完成实体触屏、真实飞行或新安装包验证；无对应支持声明。

### 提交前 Git 快照（不含本报告）

初始 HEAD 复核：2a301d8c6c0c7f37568998acc675a0c5d68b9d3c

```text
M	README.md
M	docs/CXYL_Python_GUI_STYLE_GUIDE.md
M	docs/GUI_STYLE_GUIDE.md
A	docs/KF6_FIELD_ANALYSIS.md
A	src/silverstar_flp/core/path_preferences.py
M	src/silverstar_flp/core/project.py
M	src/silverstar_flp/export/service.py
M	src/silverstar_flp/i18n/en_US.json
M	src/silverstar_flp/i18n/zh_CN.json
A	src/silverstar_flp/plugins/algorithms/kf6/field_analysis.py
M	src/silverstar_flp/plugins/algorithms/kf6/filter.py
M	src/silverstar_flp/plugins/algorithms/kf6/plugin.py
M	src/silverstar_flp/plugins/api/algorithm.py
M	src/silverstar_flp/ui/main_window.py
M	src/silverstar_flp/ui/new_project.py
M	src/silverstar_flp/ui/pages/export_settings.py
M	src/silverstar_flp/ui/pages/replay.py
A	tests/fixtures/kf6_outage_vectors.json
M	tests/fixtures/parameter_contracts/kf6_fccg_1_2.json
M	tests/parameter_fixtures.py
M	tests/test_gui_smoke.py
A	tests/test_kf6_field_analysis.py
A	tests/test_kf6_outage.py
A	tests/test_path_preferences.py
M	tests/test_replay_page.py
A	tools/kf6_field_analysis.py

 README.md                                          |   3 +
 docs/CXYL_Python_GUI_STYLE_GUIDE.md                |   4 +-
 docs/GUI_STYLE_GUIDE.md                            |   4 +-
 docs/KF6_FIELD_ANALYSIS.md                         |  86 ++++++++
 src/silverstar_flp/core/path_preferences.py        |  82 +++++++
 src/silverstar_flp/core/project.py                 |  23 +-
 src/silverstar_flp/export/service.py               |   2 +
 src/silverstar_flp/i18n/en_US.json                 |   9 +-
 src/silverstar_flp/i18n/zh_CN.json                 |   9 +-
 .../plugins/algorithms/kf6/field_analysis.py       | 244 +++++++++++++++++++++
 .../plugins/algorithms/kf6/filter.py               |  77 ++++++-
 .../plugins/algorithms/kf6/plugin.py               | 149 ++++++++++---
 src/silverstar_flp/plugins/api/algorithm.py        |  13 +-
 src/silverstar_flp/ui/main_window.py               |  59 ++++-
 src/silverstar_flp/ui/new_project.py               |  26 ++-
 src/silverstar_flp/ui/pages/export_settings.py     |  66 +++---
 src/silverstar_flp/ui/pages/replay.py              |  82 +++----
 tests/fixtures/kf6_outage_vectors.json             |   1 +
 .../fixtures/parameter_contracts/kf6_fccg_1_2.json |  47 +++-
 tests/parameter_fixtures.py                        |   5 +-
 tests/test_gui_smoke.py                            |  14 +-
 tests/test_kf6_field_analysis.py                   | 168 ++++++++++++++
 tests/test_kf6_outage.py                           | 184 ++++++++++++++++
 tests/test_path_preferences.py                     | 106 +++++++++
 tests/test_replay_page.py                          |   4 +-
 tools/kf6_field_analysis.py                        |  61 ++++++
 26 files changed, 1353 insertions(+), 175 deletions(-)
```

最终提交后的工作区状态另在交付消息核验。


## 2026-09-16 — GNSS NIS semantics and sparse PRE-FLIGHT closeout

Clean initial source worktree at `f4b10f8`; user attachment explicitly authorized independent
FLP changes. No reset, checkout, commit or push. Version 0.0.2, .ssdecoder/project-semantics
1.2, SSLOG 0.0 and existing project formats remain unchanged.

### Root cause, fix and scope

KF6's recorded/recomputed position and velocity NIS are max(horizontal EN 2D, vertical U 1D).
Visualization metadata incorrectly named nis_3d_soft/hard as the thresholds for these aggregates.
`last_group_nis` exists inside the numerical filter, but the current exposed/recorded semantic
channels provide the aggregates; this patch does not invent group channels or extend log fields.

`NisThresholdSpec` plus optional MeasurementGroupSpec description/reference metadata supply the
shared GUI/export renderer. GNSS position/velocity now show:

| Reference | Default actual value |
| --- | ---: |
| U / 1D soft | 6.635 |
| U / 1D hard | 10.828 |
| EN / 2D soft | 9.210 |
| EN / 2D hard | 13.816 |

The title explains `max(EN 2D, U 1D)` and explicitly says the lines are group references,
not a unified aggregate pass/fail gate. Values use the source's actual parameter mapping;
float32 representation is preserved. Barometer keeps its existing pair of 1D thresholds.
English/Chinese labels and PNG titles use the same metadata. Other algorithms keep the
existing two-threshold fallback; fake future-estimator tests pass without page branches.
The 3D parameter declarations are retained because this is a presentation correction,
not a change to filter mathematics, parameters or historical data.

The parser/replay already accepts sparse preflight correctly. No parser, sequence-gap,
timestamp, required-stream, comparison-sampling or numerical code was changed or weakened.

### Files and regression coverage

- `src/silverstar_flp/plugins/api/algorithm.py`: generic NIS reference metadata and fallback.
- `src/silverstar_flp/plugins/algorithms/kf6/plugin.py`: visualization declarations only;
  position/velocity no longer reference nis_3d_* gates.
- `src/silverstar_flp/ui/pages/state_estimation.py`, `src/silverstar_flp/export/service.py`:
  metadata-driven reference lines and explanatory title for both surfaces.
- `src/silverstar_flp/i18n/en_US.json`, `zh_CN.json`: four reference names and aggregate meaning.
- `tests/test_estimator_visualization.py`, `tests/test_flight_state_pages.py`: four GNSS
  references, correct actual values, 1D barometer, both languages, generic-renderer regression;
  the GNSS plot contains one data curve plus four references instead of the old three curves.
- `tests/synthetic_parameter_navigation.py`: optional sparse preflight/flight length and missing
  IMU fixture switches; its original default fixture and frozen numerical outputs remain intact.
- `tests/test_sparse_preflight.py`: exact matching synthetic decoder/log, 120 s sparse preflight,
  20 s corrected IMU plus selected Baro inputs; CRC/header/record sequence clean, Data Quality
  CLEAN, KF6/Pure INS replay available, all four pages render, CSV/PNG/export succeeds.
  A separate exact package with missing mission IMU remains unavailable/rejected despite
  continuous SSLOG record sequences. The fixture selects IMU/Baro; it is not a GNSS hardware test.
- `docs/GUI_STYLE_GUIDE.md`, this report: interpretation and acceptance boundary.

### Verification

All output, TEMP/TMP and MPLCONFIGDIR are local to `tests/.pytest_cache/nis_0916/`;
QT_QPA_PLATFORM=offscreen, PYTHONDONTWRITEBYTECODE=1.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_estimator_visualization.py tests/test_sparse_preflight.py -q --basetemp=tests/.pytest_cache/nis_0916/run4 -o cache_dir=tests/.pytest_cache/nis_0916/cache
.venv/Scripts/python.exe -m pytest -q --basetemp=tests/.pytest_cache/nis_0916/full2 -o cache_dir=tests/.pytest_cache/nis_0916/cache
.venv/Scripts/python.exe -m ruff check src/silverstar_flp/plugins/api/algorithm.py src/silverstar_flp/plugins/algorithms/kf6/plugin.py src/silverstar_flp/ui/pages/state_estimation.py src/silverstar_flp/export/service.py tests/test_sparse_preflight.py tests/test_estimator_visualization.py tests/synthetic_parameter_navigation.py --no-cache
```

Focused **9 passed**. Full **257 passed, 8 skipped in 74.54 s**; ruff passes and
`git diff --check` passes. Full coverage includes replay, timestamp semantics, comparison
sampling, touch, state GUI, export and the unchanged frozen `legacy_dynamic_outputs.npz`
comparison for every default algorithm result channel. No golden file was regenerated.
All KF6 plugin callable implementations match HEAD structurally (AST comparison).

Eight skips require unavailable explicitly named real logs: current SS0000, SS0007 (3),
SS0014 and SS_TEST_0 (3). These are not synthetic acceptance passes or hardware claims.

Artifacts: `tests/.pytest_cache/nis_0916/full2.log`; sparse exact .BIN/.ssdecoder pair, four
page screenshots and exported files under
`tests/.pytest_cache/nis_0916/full2/test_sparse_120_seconds_import0/`.
English GNSS reference PNGs under
`tests/.pytest_cache/nis_0916/full2/test_configured_without_valid_0/configured_no_updates_export/Plots_EN/`
were visually inspected: title, reference legends and lines fit without clipping. This fixture
correctly leaves the data plot empty when no valid GNSS updates exist.

The unavailable real logs and hardware acceptance remain the only unverified data sources.
No GNSS quality/reacquisition algorithm, covariance inflation, deployment or sampling logic changed.

<!-- closeout-git-begin -->
### Final Git snapshot

Tracked diff (new files are listed separately by status):

```text
 VALIDATION.md                                      | 122 +++++++++++++++++++++
 docs/GUI_STYLE_GUIDE.md                            |  15 +++
 src/silverstar_flp/export/service.py               |  20 +---
 src/silverstar_flp/i18n/en_US.json                 |   7 +-
 src/silverstar_flp/i18n/zh_CN.json                 |   7 +-
 .../plugins/algorithms/kf6/plugin.py               |  19 +++-
 src/silverstar_flp/plugins/api/algorithm.py        |  23 ++++
 src/silverstar_flp/ui/pages/state_estimation.py    |  27 ++---
 tests/synthetic_parameter_navigation.py            |  53 +++++----
 tests/test_estimator_visualization.py              |  42 ++++++-
 tests/test_flight_state_pages.py                   |   2 +-
 11 files changed, 273 insertions(+), 64 deletions(-)
```

```text
 M VALIDATION.md
 M docs/GUI_STYLE_GUIDE.md
 M src/silverstar_flp/export/service.py
 M src/silverstar_flp/i18n/en_US.json
 M src/silverstar_flp/i18n/zh_CN.json
 M src/silverstar_flp/plugins/algorithms/kf6/plugin.py
 M src/silverstar_flp/plugins/api/algorithm.py
 M src/silverstar_flp/ui/pages/state_estimation.py
 M tests/synthetic_parameter_navigation.py
 M tests/test_estimator_visualization.py
 M tests/test_flight_state_pages.py
?? tests/test_sparse_preflight.py
```
<!-- closeout-git-end -->


## 2026-09-14 — GUI touch-scrolling closeout

Scope: GUI registration/helper, GUI tests and documentation only. Initial working tree was clean;
no reset, checkout, commit, push, version change or cross-repository dependency was introduced.

<!-- touch-git-snapshot -->
### Modified files and Git snapshot

- `VALIDATION.md`
- `docs/GUI_STYLE_GUIDE.md`
- `src/silverstar_flp/ui/main_window.py`
- `src/silverstar_flp/ui/pages/data_explorer.py`
- `src/silverstar_flp/ui/pages/export_settings.py`
- `src/silverstar_flp/ui/pages/overview.py`
- `src/silverstar_flp/ui/pages/replay.py`
- `src/silverstar_flp/ui/pages/state_estimation.py`
- `src/silverstar_flp/ui/plugin_manager.py`
- `src/silverstar_flp/ui/touch_scroll.py`
- `src/silverstar_flp/ui/widgets.py`
- `tests/test_touch_scroll.py`

`git diff --stat` (tracked files only; new files are listed above):

```text
 docs/GUI_STYLE_GUIDE.md                         | 16 ++++++++++++++++
 src/silverstar_flp/ui/main_window.py            |  2 ++
 src/silverstar_flp/ui/pages/data_explorer.py    |  6 ++++++
 src/silverstar_flp/ui/pages/export_settings.py  |  3 +++
 src/silverstar_flp/ui/pages/overview.py         |  5 +++++
 src/silverstar_flp/ui/pages/replay.py           |  4 ++++
 src/silverstar_flp/ui/pages/state_estimation.py |  2 ++
 src/silverstar_flp/ui/plugin_manager.py         |  2 ++
 src/silverstar_flp/ui/widgets.py                |  3 +++
 9 files changed, 43 insertions(+)
```

`git status --short`:

```text
 M docs/GUI_STYLE_GUIDE.md
 M src/silverstar_flp/ui/main_window.py
 M src/silverstar_flp/ui/pages/data_explorer.py
 M src/silverstar_flp/ui/pages/export_settings.py
 M src/silverstar_flp/ui/pages/overview.py
 M src/silverstar_flp/ui/pages/replay.py
 M src/silverstar_flp/ui/pages/state_estimation.py
 M src/silverstar_flp/ui/plugin_manager.py
 M src/silverstar_flp/ui/widgets.py
?? VALIDATION.md
?? src/silverstar_flp/ui/touch_scroll.py
?? tests/test_touch_scroll.py
```
<!-- /touch-git-snapshot -->

### Cause and repair

Ordinary scrolling widgets had no native touch-scroller registration. Added the local
`TouchScroll_Enable` allowlist helper and explicit constructor calls. Coverage: Overview page
and calibration/alignment/timeline tables; Replay form and stored-result/comparison tables;
Data Explorer channel list and channel/record/diagnostic/sequence-gap tables; State Estimation
update table; Export Settings item scroll and failure details; navigation and Plugin Manager
table; StandardComboBox popup views. Existing pixel/item scroll modes stay unchanged.

2D PlotWidget/QGraphicsView, GLViewWidget and the playback slider are not registered, and runtime
coverage tests confirm they have no registered page-scroll ancestor. Flight/State Estimation
charts keep their expandable plotting layout. No Dataset, decoder, semantic adapter, timestamps,
KF6/Pure INS replay, comparison sampling, chart values, export logic or project format changed.

### Executed checks

- `.venv/Scripts/python.exe -B -m pytest tests/test_gui_smoke.py tests/test_comparison_sampling_gui.py tests/test_replay_page.py -q --basetemp=tests/.pytest-work-touch-focused -o cache_dir=tests/.pytest-cache-touch`: **14 passed**.
- `.venv/Scripts/python.exe -B -m pytest tests/test_touch_scroll.py -q --basetemp=tests/.pytest-work-touch-new2 -o cache_dir=tests/.pytest-cache-touch`: **18 passed**.
- Full pytest via `pytest.main(['-q', '--basetemp=tests/.pytest_cache/touch-validation/full', '-o', 'cache_dir=tests/.pytest_cache/touch-validation/cache'])`: **254 passed, 8 skipped**, 58.86 s.
- `.venv/Scripts/python.exe -B -m ruff check src tests --no-cache`: **passed**.
- `git diff --check` and static scroll/graphics inventory: **passed**.

Full-run wrapper sets `QT_QPA_PLATFORM=offscreen`, `PYTHONDONTWRITEBYTECODE=1`, process-local TEMP,
TMP and MPLCONFIGDIR below `tests/.pytest_cache/touch-validation`; QSettings uses IniFormat and
that directory's settings subtree. The full log is `tests/.pytest_cache/touch-validation/full.log`.
New tests cover native viewport registration/type, exclusion of inputs/graphics/headers, retained
mouse row selection and scrollbar movement, actual synthesized finger swipes on page/list/table/text,
main-window coverage and Plugin Manager construction.

### Remaining validation limits

The eight existing opt-in real-log gates skipped because `SILVERSTAR_CURRENT_LOG_ROOT`,
`SILVERSTAR_SS0007_PATH`, `SILVERSTAR_SS0014_ROOT` and `SILVERSTAR_SS_TEST_0_ROOT` were not supplied.
No CF-33 physical touchscreen/stylus or hardware-driver acceptance is claimed. No known remaining
failure in the executed GUI, comparison, replay or export regression suite.

