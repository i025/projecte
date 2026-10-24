# R2/R3 Region-level Atomic Evidence & Verification Pilot

本轮打通了可审计的数据和程序流程，但**尚未完成真实语义验证**。已有系统未配置可靠原子验证器，也没有可重放的同题真实验证响应。没有以 Mock 或 RGB/DINO 距离替代 Semantic / Spatial / Statistical。

[完整图像/命题/状态对照](comparison.html) · [Reference证据](reference_evidence.json) · [问题与输入](verification_questions.json) · [真实验证状态](verification_results.json) · [Energy适配](energy_adapter.json) · [单列Mock](mock_verification.json) · [DINO诊断](dino_diagnostics.csv) · [一致性检查](validation.json)

## 数据、来源和冻结边界

- 只使用 bw_0073 的 R2/R3；继承 `results/region_first_real_render_bw0073/pair_audit.json` 的真实 Reference/Render 对应依据。完整路径与相机导出保存于本目录 `pair_audit.json`。Reference为7952×4333，Render为1672×941，工作网格1536×837。
- Reference原始路径：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/data/hf-snapshot/bw_0073/tests/dataset/tasks/bw_0073/references/image_01.jpg`。
- 实际Render：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg/artifacts/workspace/exports/final.png`。
- 复用上一轮等比全图适配后的Render和有效像素图，不重新配准。四张 Box/Polygon Mask 原样复制，Reference和Render共用同坐标；R2/R3均位于有效画面内。未修改顶点、Box、边界、Grounding词表或参数。
- 相机为 historical_camera：保存的相机高度1.5m，正式T0高度2m，Reference相机未知。图像差异混合了相机、布局、几何、光照与材质，不能转为正式Benchmark成绩。
- 原子候选在脚本打开Render像素之前写出。`reference_seeds()`不接收Render，明确是依据Reference观察拟定的手工流程种子：`human_seeded_provisional`。种子由助手拟定，**并非真实人工审核，也不是VLM自动提取**。不能把历史Region Plan的描述或命名当作已验证GT。
- 所有Region、原子证据及问题均 `reviewed:false`、可靠性0；没有发现或读取Key，不使用认证Header。

## Reference原子候选

R2共5条：中央岛台存在；高脚椅组存在；吊灯存在；吊灯在图像投影中位于岛台上方；前侧可辨认4把高脚椅。

R3共4条：后方壁挂橱柜存在；后方台面存在；壁挂橱柜在图像投影中位于台面上方；可辨认炉灶数量未知。炉灶部分不够明确，期望值为null，不能从Render推回或强行填0。

每条只表达一个候选命题，来源、Region ID、简短问题、期望值及依赖均保留在JSON。只观察输入视角可见内容，不推断世界坐标、物体背面或完整隐藏数量。统计候选只检查一个可见数量命题，**不代表已实现密度、尺度、占据或空间分布评测**。

## Verification与实际可用性

四态Schema支持 `satisfied / violated / unknown / unavailable`，校验ID、布尔/非负整数类型、期望值与状态一致性。额外confidence字段被拒绝，不转为可靠性。完整Render和同坐标BBox上下文Crop都已准备；Crop附带原始Mask与裁剪坐标，不能把Crop内所有内容当作该Region的语义成员。未来计数问题不应向验证模型泄露期望数量。

本轮真实状态：**8条Unavailable，1条Unknown，0条Satisfied，0条Violated**。Unavailable表示缺少真实验证器或可重放响应；Unknown表示Reference炉灶数量本身不确定。没有真实响应，不能由RGB差异确认任何类别错误、缺失、数量或空间关系违反。

程序可自动完成加载、Schema校验、问题/图像清单、依赖检查、冲突保留、状态映射和已有RGB/DINO测量；不能凭这些步骤自动确认物体语义。对象存在性、可见数量和关系需要可靠的真实VLM/VQA或人工观察；精确空间/分布验证还需要经审核的实例对应、位置或占据证据，当前没有运行检测器来补造它们。

## 接入已有Energy，保持N/A

原子问题使用既有 `verification_questions` 格式：`energy=semantic/spatial/statistical`、`level=region`、独立ID。实际适配调用原有 `load_document → build_reference → compare → aggregate`，只保存9条原子问题的记录和每个Region的三类能量；不使用内部Global/Dense代理结果生成语义结论。

全部问题可靠性为0，原有compare拒绝它们，故9条记录value=null，R2/R3三类能量均N/A，覆盖率0（0个可计分判断/9个计划问题）。没有总分，没有把N/A当作0误差，也没有改变五类公式与权重。

未来经审核且有真实、有效验证器时，可以通过既有具体指标VLM接口表达单项命题违反；本次Mock只演示既有合法0–1误差返回契约，不制定新的连续计数误差或评分权重。布尔计数命题的违反也不能冒充完整Statistical分布能量。现有空间中心位移/占据接口仍需要独立证据，而不能从ROI名字或固定Mask推导Render对象位置。

## 归因、冲突与重复处罚

- 物体存在但移位：存在性仍可Satisfied；已有 `match_anchors` 将其区分为misplaced，不按missing处理。这里只用可信合成fixture检查逻辑，没有给真实Render赋该状态。
- 同位置类别替换与未检测到：沿用已有semantic_mismatch / unknown区分；未检测到、自称confirmed_missing均不自动建立缺失。
- 确认缺失：必须走现有独立审核的input-view缺失判定路径；合成oracle测试证实其缺失由Semantic承担，Anchor Spatial/Appearance/Perceptual不再附加最大惩罚。
- 计数/关系具有显式存在性前提。前提不可用或冲突时，相关命题Unknown/Unavailable，不把缺失原因再变成关系或计数违反。矛盾回答保留Unknown，相同重复回答不重复计条。
- Mock中的“3把椅子”“缺失吊灯”只是虚构流程输入，**完全不是对实际Agent的判断**。Mock单列，不进入实际结果或Energy适配。没有真实VQA结果时，不能宣称已验证Agent缺失某对象。
- 像素Appearance/Perceptual仍可能对同一图像原因自然响应；这种相关性没有被宣称完全消除。本轮没有把它们与原子违反加权相加，也没有对原子Unknown附加惩罚。
- R2/R3仍有重叠：Box共享82800像素（R3全部），Polygon共享16792像素。原记录见overlaps.json，不直接相加为Region总分。

## 实际Appearance / Perceptual

下列四项逐字段复用上一轮真实测量，不重算或替换为Mock。数值较小表示输入表示下的图像距离较小，不是语义正确概率。

| ROI | Appearance | Perceptual |
| --- | ---: | ---: |
| box_R2 | 0.236250 | 0.186296 |
| polygon_R2 | 0.270866 | 0.156557 |
| box_R3 | 0.311551 | 0.259300 |
| polygon_R3 | 0.318984 | 0.276288 |

R2仍有岛台/椅子/吊灯图像差异，固定Polygon的吊灯部分不能跟随Render中下移的灯，因而不能完整评价移出范围的物体。R3的台面、墙面和柜体图像差异可定位，但不能从RGB差异区分材质、相机或语义错误。Reference炉灶数量的不确定性来自证据提取，不应归咎Agent。

## DINO输入处理受控诊断

仅用已有本地DINOv2在CPU做小范围实际推理；没有改正式Perceptual。每个ROI比较：原公式黑色裁剪；相同ROI外共同填127灰色；外接框原图上下文；全图保留ROI且其余黑色。后两项改变上下文/相对输入尺度，只用于分析，不是候选新公式。ROI内的Reference和Render像素始终不变。

| ROI | 输入处理 | DINO距离 | 相对原公式变化 |
| --- | --- | ---: | ---: |
| box_R2 | official_black_crop | 0.186296 | 0.000000 |
| box_R2 | common_gray_crop | 0.186296 | 0.000000 |
| box_R2 | bbox_context | 0.186296 | 0.000000 |
| box_R2 | full_frame_black | 0.161966 | -0.024330 |
| polygon_R2 | official_black_crop | 0.156557 | 0.000000 |
| polygon_R2 | common_gray_crop | 0.172443 | 0.015886 |
| polygon_R2 | bbox_context | 0.186023 | 0.029466 |
| polygon_R2 | full_frame_black | 0.166861 | 0.010304 |
| box_R3 | official_black_crop | 0.259300 | 0.000000 |
| box_R3 | common_gray_crop | 0.259300 | 0.000000 |
| box_R3 | bbox_context | 0.259300 | 0.000000 |
| box_R3 | full_frame_black | 0.088190 | -0.171110 |
| polygon_R3 | official_black_crop | 0.276288 | 0.000000 |
| polygon_R3 | common_gray_crop | 0.257721 | -0.018566 |
| polygon_R3 | bbox_context | 0.271148 | -0.005139 |
| polygon_R3 | full_frame_black | 0.088833 | -0.187454 |

若实际模型可用，原公式四次重放应与缓存一致。共同填充、框内上下文或全图输入导致的距离变化，说明不同面积/长宽比/裁剪方式的ROI不能直接据数值高低比较质量。灰色不是经验证更正确的方案，全图黑色更低也可能来自共同背景与目标缩小。

同一Reference输入的四种处理自比较均接近0（容差1e-12）。共同黑色填充并未在完全相同输入上凭空产生明显正误差，但会改变不同图像的特征距离及解释。 尚无像素GT、真实语义标签或质量标定，不能把输入敏感性等同于已测出的语义伪差异率。

## Region-first的实际增益和未完成部分

理论上，Region把少量局部评价范围与可审核命题、独立验证问题和失败原因关联，避免只有Global均值而无法追溯局部内容；存在性、关系、数量能分开讨论。相比无语义网格，更适合人工按功能组审核。

本轮实际增加了9条可追踪命题、同坐标验证输入、明确的Unknown/Unavailable原因，以及逐Region图像距离和DINO输入敏感性。**没有实际证明新的语义检出能力或优于Dense的准确率**，没有确认任何真实原子违反，完整的真实语义闭环仍缺验证器和人工审核。Global/Dense仍覆盖Region外内容，不替代或删除困难区域。

## 执行、限制与复现

- 只新增 `scripts/region_atomic_pilot.py` 和 `tests/test_atomic_evidence.py`。核心evidence/metrics/config保持原样，历史Grounding冻结检查不受影响。新辅助函数放在实验脚本，避免修改B2冻结的整份源码。
- 新增14项CPU测试，结合原有145项回归共159项通过；当前日志在tests.log。测试覆盖四态/类型、Unknown、冲突、未检测到、存在性前提、缺失单次处罚、q=0不调用验证器和输入变体像素保持。Mock通过不代表真实语义验证成功。
- 本轮运行耗时约21.623秒，其中DINO诊断16.955秒，CPU单模型、2线程。未运行GPU、SAM、SLIC、Agent或Blender，没有付费请求、下载、正式评分或Git提交。
- 所有结果provisional/debug；不满足固定外参，没有人工GT或真实VQA。失败案例保留，不自动扩展样本。

只浏览现有页面无需运行任何命令。免费离线复现如下，目标目录必须不存在；重复运行请另选目录：

```bash
cd /home/xymo/projects/e-harness
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/xymo/environments/relateanything-inference/bin/python -m unittest discover -s tests -p test_atomic_evidence.py -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/xymo/environments/relateanything-inference/bin/python scripts/region_atomic_pilot.py --output results/region_atomic_verification_bw0073_replay
```

若只重放已有测量和程序流程，可加 `--skip-dino-diagnostics`，新增输入变体Perceptual应报告N/A，不能声称执行了实际推理。本轮完成后停止，等待人工审核。
