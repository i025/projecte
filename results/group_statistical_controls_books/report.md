# 独立书籍排列控制实验 — Verification Pending

完成 1 组 A/B/C 独立合成样本的离线准备；真实 VLM 请求 **0 次**，没有模型预测、检出率或正式 Statistical Energy。预期标签仅为 `construction_expected`，全部 `reviewed:false` / `unreviewed`。

## 冻结协议与数据来源

在生成图片前保存只读 `frozen_protocol.json` 与 `expected_labels.json`。两个问题分别判断“至少两本清楚可辨的横向堆叠书籍”和“清楚可辨的竖放书籍”，都只接受 yes/no/unknown。严格采用用户给定 Prompt，不根据图片或后续结果修改定义。旧 mixed→upright 实验只作为研究背景，本组未读取或使用 bw_0074 Reference/Render，也不声称进行全新研究者盲测。

场景由本轮新写并静态检查的 `construction/books_control_scene.py` 构建，只用基础几何、材质和固定相机；没有打开历史 .blend、执行 Agent 代码或调用 GPU/大型模型。每本书含封面、书脊和米色页块，避免使用单块彩色矩形代替所有书籍线索。没有文字、实验条件或预期标签写进原始 PNG。供模型观察的仅为 `images/sample_01.png` 至 `sample_03.png`；comparison.png/HTML 的标题仅供审核，不作为模型输入。

## 构造条件

| 条件 | Horizontal | Upright | 控制方式 |
|---|---|---|---|
| A | yes | yes | 3 本竖放 + 两组各 3 本横向书堆 |
| B | no | yes | 将同 6 本横放书转竖；原 3 本竖放不变 |
| C | yes | yes | A 的几何完全不变，仅改 9 本封面颜色 |

三侧均为同 9 本书，书本尺寸、书架、相机、分辨率、光照、曝光、随机种子相同。B 的旋转必然要求中心高度及间距变化；投影轮廓、可见页块、遮挡和阴影也会变，**并非只改变一个像素级因素**。C 的灯光不变，但封面色影响物理反射与间接光，不能保证非书籍像素完全相同。逐本差异在 construction_checks.json，实际相机/物体矩阵在 construction/*_render.json。

## 实际运行

复用现有受控 CPU 启动器，严格串行、两核亲和性、nice=10、每图 120 秒墙钟/60 秒 CPU、1 GiB RSS 停止阈值；CPU Cycles 768×640、8 samples、固定 seed、无去噪。保持正式 Runtime blocked 未改。总启动墙钟约 20.381 秒，采样峰值 RSS 最大 284.0 MiB。

| 条件 | 成功 | 启动墙钟 s | 采样峰值 RSS MiB |
|---|---|---|---|
| A | True | 6.907 | 284.0 |
| B | True | 6.757 | 282.7 |
| C | True | 6.717 | 283.2 |

资源记录和日志位于 launch_A/、launch_B/、launch_C/。本轮不生成第二组布局，避免扩大实验。

17 项纯 CPU 单元测试全部通过，失败 0、错误 0、跳过 0。数据检查 11 项全部通过，额外检查冻结时间、请求消息、HTML 链接与 unreviewed 状态通过。这些检查覆盖构造约束、解析/四状态/非评分适配与文件可读性，不代表真实 VLM 检测通过。

## 验证准备与 Benchmark 连接

pending_requests.json 保存完全相同的 System/User、预定模型 openai/gpt-6-sol、低 temperature、400 输出 Token 上限、每次一个完整 RGB、零重试；只有本地 image_ref，未保存 Base64、认证信息或预期标签到模型消息中。它是待授权请求描述，不是已发送的 HTTP 请求。现有 OfoxTunnel/VLMClient 可在下一轮获准后把 image_ref 在内存转为 image_url；当前 request() 在读取凭证/创建客户端之前直接拒绝。

复用现有 group_questions → replay_atomic_answers → group_energy_rows 适配链，生成兼容的 Group/Region/Atomic evidence 与 N/A 记录（benchmark_applicability.json）。每图与预期比较，以及 A/B、A/C 成对比较，都保持 unavailable（Verification Pending）。解析器保留另一有效字段，区分 unknown 与 unavailable；明确相同→satisfied、明确不同→candidate_violated，均不直接生成 Energy。group_evidence.json 提供 Group-level Statistical 候选输入，可靠性为 0，scorable=false，不新增第六类 Energy，也不改变正式公式/权重。两个事实分别有唯一 Group 所有者，无需逐实例成员匹配或额外 Anchor 罚项。

## 审核重点与限制

人工需确认两处横向书堆是否清晰、B 是否确实没有横向书堆、竖放书是否可辨，是否将书架横板/金色纹饰/页块误认成横向书。请在 human_review.json 另存人工结论；本轮不自动确认。没有逐本人工 GT、真实 VLM 结果或独立准确率，合成域结果即使成功也不能直接证明真实图像有效。此组没有唱片/文件夹干扰项，也没有严重遮挡、模糊、未知样本，无法测量这些失败模式或 unknown 校准。

静态可视性候选观察（reviewed=false）：A/C 左上与右下各有三层薄体、左下有竖体；B 三组均呈竖体，未发现整本裁切。但 8 samples 噪点明显，页块细节较弱，类别可能与文件夹/唱片套混淆；书架横板、书脊饰带、隔板交接黑条与顶部暗缝可成为杂线索；C 浅色书脊可能降低分层边界对比。此处不构成人工审核通过，本轮保留原图，不事后改场景或 Prompt。详见 static_visibility_notes.json。

最小真实验证需要 **3 次请求**（A/B/C 各 1 次，独立观察；不额外调用成对比较）。当前授权 **0 次**，等待用户批准后才能执行。后续需要不含历史 bw_0074 调参泄漏的独立真实图、人工按冻结定义审核的正/负/unknown 标签，以及唱片/文件夹、单本平放、遮挡、分辨率和多视角困难对照；报告误报、漏报、弃权及外观不变性，才能判断该候选是否适合接入正式 Statistical Energy。一次二值成功不构成分数校准。

## 离线复现

在仓库根目录使用现有 Python 环境，无需安装依赖。使用新的空输出目录，不能覆盖本轮结果：

```sh
/home/xymo/environments/relateanything-inference/bin/python scripts/group_statistical_controls.py --stage prepare --output results/group_statistical_controls_books_repro
/home/xymo/environments/relateanything-inference/bin/python -m unittest discover -s tests -p test_group_statistical_controls.py -v
/home/xymo/environments/relateanything-inference/bin/python scripts/group_statistical_controls.py --stage render --output results/group_statistical_controls_books_repro
/home/xymo/environments/relateanything-inference/bin/python scripts/group_statistical_controls.py --stage finalize --output results/group_statistical_controls_books_repro
```

render 仅运行本轮可信合成 fixture，使用原有命名空间及资源限制；若资源/隔离不可用即停止，不降低隔离标准。离线测试使用明确的构造答案测试解析比较逻辑，不将其写成真实 VLM 输出。测试结果见 tests.txt / tests_result.json；数据检查见 offline_checks.json。初次使用点号模块路径的测试启动因 tests 非包而失败，已改为 discover；原错误保存在 initial_tests.txt / initial_tests_result.json，不是测试断言失败。未修改正式评分、历史结果或 Git 提交。
