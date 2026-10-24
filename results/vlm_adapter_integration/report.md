# 真实 VLM Verification Adapter 集成

> 公开发布说明：这是原实验报告的公开副本。实验创建时的“未Commit/Push”是历史快照；当前发布状态以审核分支提交为准。仅路径元数据和省略文件的链接经过整理，原始回答、指标、审核状态与结论未改。服务器原件保留。详见 [PUBLICATION.md](PUBLICATION.md)。

2026-10-24 UTC（北京时间 2026-10-25）。基准 a4009a495da2cf2f4a71aab6f5fc8955022f4494；分支 feat/offline-integration-mvp。本轮未 Commit/Push。

**已跑通 Python → Codex CLI 图片输入 → JSON → 确定性比较 → Offline Manifest 统一诊断。** 全部 reviewed=false、provisional/debug、formal_eligible=false。未计算正式 VLM Energy，没有改变五类 Energy、权重、相机协议或 Runtime blocked 状态。

## 实际输入与冻结内容

- 原样复用 group_abstention_calibration 的两张清晰自制书籍图，896×704。它们来自既有 T1/T2，不是历史 Agent 重建，也没有新建或渲染场景。
- 第一张来源：`../group_abstention_calibration/images/3c06994002024eff9d7deaa6f2346222.png`；第二张：`../group_abstention_calibration/images/f7b8d9afd07646f1803e85746d50bea9.png`。本轮输入副本见 [frozen_inputs.json](frozen_inputs.json)。
- 保存协议的 system/user/schema 与既有 frozen_protocol() 完全一致，没有根据新回答调整。Q1“图中是否存在至少两本水平叠放的书籍？”；Q2“图中是否存在竖直站立摆放的书籍？”。
- yes/no/unknown 的操作定义保持不变：充分证据确认存在 / 区域清晰且能确认不存在 / 模糊、遮挡或类别歧义导致无法判断。模型未接收 construction_expected、实验条件、另一侧答案或源文件名。
- R_shelf、G_books 与 books_horizontal_stack / books_upright_books 沿用既有书籍证据标识。它们只是范围和问题关联，不是新生成的对象清单。冻结 construction_expected 为 yes/yes 与 no/yes，仅在协调侧比较，不是人工审核 GT。
- 冻结输入文件在调用前保存为只读。验证工作目录使用随机图片名，仅有图片、问题文本与 Schema；图片重新编码为同分辨率 RGB PNG，去掉元数据，未改视觉像素。原始图和历史答案未修改。

## 三种运行方式

1. **codex_cli**：subprocess 参数列表，shell=False；`codex exec --image`、`--output-schema`、`--output-last-message`、只读 Sandbox、never 审批、ephemeral 独立会话、忽略用户配置；不以项目目录为 cwd。禁用 shell、额外读图、web、MCP/插件、记忆及子 Agent。每次超时180秒，上限300秒；共用两次请求 ledger，重复图片禁止重试。超时终止整个进程组。
2. **subagent_import**：导入原有 Desktop 子 Agent 的原始回答、实际 Prompt、模型标识及历史 usage，校验包含相同冻结问题。没有从 Python 调度 Desktop 子 Agent，没有启动新的验证子 Agent。见 [historical_import.json](historical_import.json)。
3. **replay**：明确标记 historical_real 或 mock，无模型、网络或外部进程。复用原书籍解析器与 compare_values；[mock_transport_check.json](mock_transport_check.json) 仅测试 Unknown/缺字段，不能用作真实视觉结果。

当前 Adapter 刻意仅开放既有两字段书籍 Schema，未实现通用语义验证框架。后续其他结构/Group问题需要显式接入其已验证 Schema；底层图片传输无需重新搭建。

## 本机能力与隔离审计

本地 Codex CLI **0.163.0**，已有 ChatGPT 登录。显式指定 **gpt-6-sol**；本地模型目录支持图片。真实两次调用均 exit 0，返回合法 JSON，未观察到命令/MCP/web/写文件工具事件。

本地 debug prompt-input 构造检查发现恰好一个 input_image；解码像素与原图相同；冻结问题原文出现；未发现 construction_expected、source_construction、T1/T2 或验证答案文件名。图片 Base64 仅在预检内存中使用，不保存。真实执行也使用 --image 传入同样处理的单张图片，并保存实际 argv、stdin、图片大小与随机别名。

**不能声称严格盲测或强文件隔离。** 只读 Sandbox 允许读取临时目录外文件；CLI 仍有全局开发者上下文和登录状态。禁止模型工具减少泄漏通路，但不是 OS 级访问限制。本地预检含全局开发者上下文，6991 个输入文本字符；没有继承项目实验答案。主协调 Agent 已知源样本构造标签，属于有隔离措施的集成测试，不是独立盲测。

**远端模型快照无法独立核实。** 请求模型为 gpt-6-sol；CLI 事件未返回实际 model 字段，故 model_observed=null，不将请求名称冒充已观察模型版本。CLI 与历史 Desktop Subagent / Ofox 不是同一实验设置。

CLI 0.163.0 禁止覆盖保留的 openai provider。已在无推理本地预检后使用进程内 verification_openai 配置，指向官方 ChatGPT Codex endpoint，request_max_retries=0、stream_max_retries=0、关闭 WebSocket。没有修改共享配置、复制登录文件、读取 .bashrc 或导出凭证；没有权限绕过选项。没有 Ofox、余额检查或额外模型自检。

官方能力说明：[CLI 参数](https://learn.chatgpt.com/docs/developer-commands?surface=cli)、[非交互执行](https://learn.chatgpt.com/docs/non-interactive-mode)、[配置字段](https://learn.chatgpt.com/docs/config-file/config-reference)。实际可用性以上述本机预检和两次执行为准。

## 两次真实视觉回答

| 输入 | 原始回答（未修改） | input tokens | cached input（包含在input内） | output tokens | CLI耗时 |
| --- | --- | --- | --- | --- | --- |
| 清晰 T1（本轮输入1） | `{"horizontal_stack":"yes","upright_books":"yes"}` | 10519 | 0 | 22 | 16.323 s |
| 清晰 T2（本轮输入2） | `{"horizontal_stack":"no","upright_books":"yes"}` | 10524 | 7936 | 22 | 13.678 s |

共 **2次新CLI视觉验证**，严格串行、每图一次、无重试。输入21,043 tokens、输出44 tokens（CLI已报告计数），其中第二次缓存读取7,936；两次CLI耗时合计30.000秒。总计数若按input+output计算为21,087，是派生和，CLI未报告total_tokens所以该原字段保留null。Token含平台上下文，不等于纯图片/问题Token，不与历史子Agent的全会话计数或Ofox美元计费混算。货币费用未知，本轮Ofox请求数为0。

确定性比较：

| evidence_id | 输入1 | 输入2 | 状态 | 数值惩罚 |
| --- | --- | --- | --- | --- |
| books_horizontal_stack | yes | no | candidate_violated | N/A |
| books_upright_books | yes | yes | satisfied | N/A |

这只说明当前接口能区分这两张清晰合成图的目标变化；不证明真实Render泛化、弃权校准、书籍/唱片区分或稳定准确率。两个回答符合未审核construction_expected，也不能升级为GT。

## 统一离线报告

新增可选 Manifest 字段 `vlm_verification`。导入时重解析原始回答并重算比较，不信任外部填写的 satisfied/reviewed/value。非法JSON、缺字段、Unknown、模型不可用和整侧失败均不补造答案。单字段无效时保留其他有效字段；整侧推理失败则该侧答案全部不可用。

[offline_report/report.json](offline_report/report.json) 与 [summary.md](offline_report/summary.md) 记录冻结问题、Region/Group、两侧原始与解析回答、后端、请求、Token、审核状态和不确定性。原流程仍调用 build_reference → compare → aggregate 与独立 structural_report。

该合成配对的实际 RGB Appearance 为 0.005194646；Spatial/Statistical 仅原有图像边缘/纹理代理；Semantic、Perceptual、3D Structural 均为N/A。VLM回答没有数值Energy贡献。该“render”字段仅沿用Manifest接口名，实际是合成负对照，绝非真实Agent Render。

[离线回放检查](offline_modes_checks.json)（原始重复报告留服务器） 重新读取已保存真实CLI回答，无模型执行；Energy与比较状态均与首份统一报告一致。缺少/损坏可选验证文件也不会丢弃可计算RGB结果。没有用相机声明把静态数据升级为正式有效。

## CPU测试与检查

- 新Adapter专用 **19项通过**；原Offline Integration **19项通过**。
- 完整CPU回归 **338项通过，0失败、0错误、0跳过**，约5.16秒。运行时主动禁止网络连接和外部进程；模型/Blender测试均未执行。记录见 [cpu_tests.json](cpu_tests.json)。首次完整回归336项通过的记录另存为 cpu_tests_initial.json；随后补充两个进程清理/模型不可用测试。
- 覆盖非法JSON、重复键、缺字段、Unknown、部分失败、模型不存在、超时杀进程组、缺图片、标签字段拒绝、随机文件名、只读与禁用工具配置、两次预算和无重试、历史Prompt不匹配、导入真假来源、外部伪造比较状态、未审核证据不评分，以及验证失败保留Observation。
- 首次测试入口使用 tests.* 导入失败（tests不是包）；已改为 unittest discover。CLI早期本地配置/参数问题均发生在推理前，未消耗模型验证预算。
- git diff检查确认 benchmark_metrics.py、benchmark_evidence.py、benchmark_config.py、model_client.py 和 runtime_evidence 未改变；既有源码冻结校验仍通过。未运行SAM、SLIC、DINO、GPU、Blender、历史Agent代码；未生成HTML。

## 复现（不发起新模型请求）

在已有兼容Python环境、scene-benchmark相邻依赖和历史自制图片可用时：

```bash
python3 -B -m unittest discover -s tests -p 'test_verification_adapter.py'
python3 -B -m e_harness.benchmark offline --manifest results/vlm_adapter_integration/offline_manifest.json --output /tmp/projecte-verification-offline-new
python3 -B scripts/vlm_adapter_pilot.py prepare --output /tmp/projecte-verification-replay-new
python3 -B scripts/vlm_adapter_pilot.py finish --backend replay --output /tmp/projecte-verification-replay-new
```

最后一条可换为 subagent_import，仍不调用模型。codex_cli是显式的真实推理选项，必须另有授权与新输出目录；本轮两次预算已经用完，不能重跑。脚本在启动前创建独占reservation，拒绝继续已启动实验。

## 下一步可信Blender Fixture的最小接入

只需在独立、获准的CPU测试入口复用现有 render_cpu(fixture=已白名单内置fixture)，将其实际RGB、导出camera/geometry和既有Reference写入Manifest，再运行此离线入口；继续使用串行锁、线程/超时/内存限制和新目录。不要开放历史Agent执行。

目前静态JSON仍不能建立“本次可信渲染进程→实际相机→RGB”的可信绑定。若未来要正式有效，需要在受控渲染与评价的同一调用链核验实际T0、图像尺寸和有效像素，并保留失败状态；不能增加一个布尔字段来替代该检查。本轮不实现、不运行、不解除Runtime blocked。语义评分还需要独立Reference审核与验证器有效性/弃权测试，不能因为CLI接通就将yes/no映射为0/1。

## 交付与未验证项

主要材料：[comparison.png](comparison.png)、[verification_results.json](verification_results.json)、[integration_checks.json](integration_checks.json)、[GitHub 源码Diff](https://github.com/i025/projecte/compare/a4009a495da2cf2f4a71aab6f5fc8955022f4494...feat/offline-integration-mvp)。没有Commit/Push。

未验证：真实Agent Render上的程序化VQA、困难样本与模糊弃权、其他问题Schema、远端精确模型快照、强文件隔离、CLI不同安装版本、可信Blender端到端执行与正式相机绑定、无历史数据的干净安装。核心相邻依赖与第三方素材许可限制仍沿用原文档。

补充检查：replay 与 subagent_import 两种完整脚本路径均已在禁止网络/外部进程下实际运行，新增模型调用为0，状态与真实CLI对照一致；见 [offline_modes_checks.json](offline_modes_checks.json)。内容检查及文件清单见 [公开审查说明](PUBLICATION.md)（本机审查清单未上传）。两处安全扫描命中仅为单元测试中的假 data URL（ASCII ABC）及对应Diff，不是保存的图片请求正文；未发现凭证。所有新Markdown相对链接可解析，未生成HTML。
