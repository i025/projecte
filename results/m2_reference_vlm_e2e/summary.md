# M2 Reference Evidence + Real VLM End-to-End

**reviewed:false · provisional/debug · no formal Benchmark score.**

Saved first-party M1 RGB → Reference-only CLI planning → frozen evidence → independent Reference/Changed VQA → deterministic comparison → existing Offline Evaluator.

No new Blender execution, Ofox, GPU, SAM/SLIC/DINO or Agent code. Prior M1 receipts are provenance only; static replay remains pose_consistent_unverified.

## Actual calls

| Stage | Source | Status | Input tokens | Output tokens | Seconds |
| --- | --- | --- | --- | --- | --- |
| planning_response | live_model | valid | 10073 | 197 | 15.967060456983745 |
| reference_answers | live_model | valid | 9878 | 21 | 15.442218411015347 |
| render_answers | live_model | valid | 9876 | 21 | 12.993526036152616 |

Requested model(s): gpt-6-sol; observed remote snapshot may be null. Token counts are CLI-reported usage (including platform context), not Ofox billing. No retry. Temporary cwd and tools disabled do not guarantee filesystem confinement.

## Frozen questions and actual answers

| ID / Region / Group / Anchor | Question | Reference | Changed | Comparison |
| --- | --- | --- | --- | --- |
| e1 / r1 / N/A / N/A | 前景有几个显著的彩色立方体？ | 2 | 2 | satisfied |
| e2 / r1 / N/A / N/A | 红色立方体是否位于蓝色立方体左侧？ | yes | yes | satisfied |

These are model answers, not GT. Same count/order can miss metric displacement; satisfied does not establish reconstruction fidelity. No after-the-fact question edits.

## Existing measurements

| Energy | Conditional debug value |
| --- | --- |
| semantic | N/A |
| spatial | 0.002285003662109375 |
| appearance | 0.03928318397671568 |
| statistical | 0.003341700152893731 |
| perceptual | N/A |

Structural: N/A. Geometry is diagnostic; unreviewed structural checks are not scored. Spatial/Statistical numeric image proxies are distinct from VQA answers. All automatic semantic evidence has reliability zero, with no Energy contribution.

## Reproduce without model calls

```bash
python3 -B -m e_harness.benchmark offline --manifest results/m2_reference_vlm_e2e/offline_manifest.json --output /tmp/projecte-m2-replay-new
python3 -B -m unittest discover -s tests -p 'test_reference_vlm_pilot.py'
```

Use the documented dependencies and a new output directory. Live driver execution requires separate authorization for up to three requests. Strong input isolation, verifiable model snapshots, independent human review and harder evidence-validity experiments remain necessary. Runtime remains blocked.


## 本轮审计结论与限制

- 本轮只复用 M1 两张 256×256 自制图片及 Changed Geometry；解码 RGB 与 M1 逐像素相同。Reference RGB 在规划时单独输入，Changed 像素在参考候选冻结后才读取。M1 执行链保留于相邻实验目录，本轮新增 Blender 执行数为 **0**。
- 实际规划为 **1 个 Region（r1）、0 个 Group、0 个 Anchor、2 条原子证据**。简单图像不强制生成更多区域或对象。归一化粗框 [105,580,790,940] 原样映射至像素 [26.88,148.48,202.24,240.64]；不根据 Changed 调整。所有自动候选 reliability=0、reviewed=false。
- 两侧真实回答都是 `{"e1":2,"e2":"yes"}`，比较均为 **satisfied**。可见红色主体明显右移，但依然在蓝色主体左侧，数量也不变。因此本次原子证据**没有检测到已知位移**。流程闭环成功并不代表证据检出能力充分；没有为取得 violated 而补题、调 Prompt 或修改参考证据。
- “立方体”是规划模型的用词；红色主体的投影和构造并非等边立方体，类别精确性待审核。背景小黄元素未被命题覆盖。这些是规划粒度/覆盖限制，不能将模型命题当作 GT。
- 现有 Global Appearance=**0.03928318397671569**；Dense Patch 四项为 **0、0、0.13906840405433005、0.018064331852532683**。固定 r1 Appearance 诊断=**0.151559181475883**，不参与局部或正式聚合。r1 没有与其他命名区域重叠；Global/Dense 与命名 ROI 的重复观察不直接相加。
- 有/无 VLM 两次离线回放的 Energy 对象完全相同；所有条件误差值与 M1 一致。Coverage 会因候选内容不同而变化，不应据此宣称质量变化。Observation=0.014969962597239594 只是既有条件 debug 聚合，不是正式成绩。
- Geometry 读入成功，保留 **36 条**候选结构检查；缺乏审核与语义 triage，独立 Structural 仍为 N/A。Semantic 无已审核证据，Perceptual 未运行 DINO，均为 N/A。Spatial/Statistical 数字仍为已有边缘/纹理代理，与两条 VQA 命题的回答不同。
- 实际没有 Group/Anchor，所以本轮只在 CPU 测试中验证可选 Group/Anchor ID 关联；不能声称已经完成真实 Group/Anchor 验证。真实调用中没有 violated/unknown/unavailable，相关状态通过明确的 Mock/故障输入测试，不能当成真实视觉有效性证据。

## 调用与测试

- **3 次**真实 `codex exec --image`，串行、每任务一次，无自动重试、无意外工具事件。Codex CLI **0.163.0**，请求 `gpt-6-sol`；三次 `model_observed=null`，无法核实远端快照。
- CLI 报告输入 **29,827** tokens，输出 **239** tokens，输入加输出算术和 **30,066**；服务未提供 `total_tokens`，原字段保留 null。三次本地调用延迟合计 **44.4028 秒**；不含 CPU 测试和离线回放，不表示 Ofox 消费金额。
- 本地无推理预检查证明送入一张图片且解码像素一致；实际调用均使用随机文件名、相同 VQA 合同、只读 sandbox、禁用工具及用户配置继承。全局 CLI 上下文与认证仍存在，文件读取范围不能由临时 cwd 完全隔离，**不声称严格盲测**。原始请求输入文本/Schema、回答、模型和 usage 保存在 JSON；不保存 Base64、凭据或完整会话日志。
- 最终 **373/373 项 CPU 测试通过**，其中 **20 项 M2 新测试**；网络连接与真实子进程启动在回归中被禁止。覆盖合法/非法 Schema、缺字段、未知与不可用、超时、调用预算、错误图片配对、Group 缺失/端点关联、VLM 不可用但图像评价继续。模型与 Blender 不由单元测试启动。
- 开发初期遇到现有 Python 环境缺少已声明的 jsonschema 依赖，以及测试中将 `required` 里的 `red` 子串误判为泄漏；在真实调用前修正。jsonschema 4.26.0 及其小型依赖仅安装到独立 /tmp 目录，共享环境未变。本轮测试未运行新的 Blender/GPU/模型任务。

## 文件与复现

[对照 PNG](comparison.png) · [冻结参考证据](reference_evidence.json) · [原始规划与输入](planning_response.json) · [真实 VQA 与确定性比较](verification_results.json) · [完整离线报告](report.json) · [端到端检查](validation_checks.json) · [CPU 测试](cpu_tests_final.json)。PNG 只使用自制合成像素；为适配无中文字库的服务器，图上用 evidence ID/类型标识，完整原文问题保留于 JSON 和本报告。

最短离线复现（安装仓库声明依赖和既有 sibling evaluator，输出目录必须不存在）：

```bash
python3 -B -m e_harness.benchmark offline \
  --manifest results/m2_reference_vlm_e2e/offline_manifest.json \
  --output /tmp/projecte-m2-offline-review-new
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

该命令不调用模型、不运行 Blender；只使用保存的真实回答。公开副本的路径已转换为相对路径或临时路径占位符，原始模型回答、证据和指标没有改写。重新运行 live driver 会再次消耗最多三次模型请求，不属于离线复现，需另行授权。

完整 Benchmark 的剩余阻塞：参考语义与 ROI 人工审核、能量化位移/尺度等更有区分力的 Reference-only 证据、真实跨场景验证、可靠 Group/Anchor 对应、强文件隔离与可核实模型快照、可信执行资格和独立结构检查标定。Runtime blocked、五类能量公式与权重均未改变。本轮只在审核分支发布，不合并 main；到此停止。

最终另补测可选 JSON Schema 依赖缺失时，VLM 诊断返回 unavailable 而 RGB 指标继续；完整回归从372项增至373项，早期372项记录仍保留在服务器。
