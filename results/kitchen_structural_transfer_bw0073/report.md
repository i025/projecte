# Structural Spatial Evidence 跨场景：bw_0073/R4

全部 reviewed=false、provisional/debug。本轮真实执行 2 个独立 gpt-6-sol 单侧图像会话，没有新 Ofox/Blender/GPU/SAM/SLIC 调用或正式 Spatial 分数。

实际状态计数：{"structure_consistent": 3, "candidate_structural_layout_mismatch": 1, "unknown": 0, "unavailable": 0}。

K3 实际获得 present → absent：Reference 的低柜被识别为上下叠置抽屉样前面板，Render 被识别为并排竖向门板。Reference 虽右端裁切，但两条水平接合线和上下排列仍可观察；Render 对该局部给出 clear，故保留外立面布局差异候选。这是实际单图回答产生的结果，不只是接口的潜在检出能力。

K1/K2/K4 的一致只说明粗门板分界、上下层和高低柜关系在本次回答中均可见，不代表面板数量、比例或完整 R4 重建质量一致。当前未出现模型 unknown 或解析 unavailable；仍然保留该处理机制，不人为制造弃权案例。

## Reference-only 冻结与正确配对

实际 Region Plan 确认为 R4「右侧高柜区」，内容为浅木色柜体、深色高柜及下方抽屉柜。复用 `vlm_direct_grounding_bw0073/region_plan.json` 与已存 Direct Box 测量 ROI，范围 [1094, 0, 1536, 762]、图像 1536×837。未修改 Region/ROI，也未以 Render 重定位。

先仅查看 Reference，冻结四条外立面结构候选到只读 `/srv/lab-disks/disk2/users/xymo/projects/e-harness/runs/kitchen_structural_e7f38ad2e3c848ac89a94640e5351baf/reference_frozen.json`，之后才在本轮查看 Render。候选由主 Agent 静态观察准备，不是 GT 或自动提取成果：

K1：深色高柜正面可见并排大型门板或前面板，并由明确的竖向接合边界区分。
K2：高柜上方另有一排较矮前面板，与下方高门板形成上下两层。
K3：右侧台面以下可见至少两块上下叠置的抽屉样前面板，具有水平接合边界与拉手线索。
K4：高柜与其右侧较低台面柜并置，形成可见的高低柜交接。

它们只描述可见门板/抽屉样前面板接合及高低柜组织，不推断隐藏隔板、实际开合机构或完整柜体实例图。原对话已包含历史 Render 相关知识，因此参考准备也不能称为严格盲测。冻结后未依据 Render 改写命题。

配对 Run：bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg。Reference 原始来源及 Render 导出对应由既有 pair_audit 支持；完整路径、相机文件和映射依据写入 structural_evidence.json.protocol。历史相机 z=1.5m、lens=22.5mm，正式协议要求 z=2m；Reference 相机未知，PNG/最终 blend 精确同步也未重新证明。全部仅用于离线诊断。

## 实际独立验证结果

使用相同简短三态协议与四个中立问题，模型只接收自己一侧的完整图（框示固定区域）及相同坐标放大图；不提供种子“应为 present”、另一侧答案或差异假设。输出逐项状态、局部可见性、短可见依据与粗线段，不输出长篇推理。

| 命题 | Reference | Render | 确定性比较 |
| --- | --- | --- | --- |
| K1 | present | present | structure_consistent |
| K2 | present | present | structure_consistent |
| K3 | present | absent | candidate_structural_layout_mismatch |
| K4 | present | present | structure_consistent |

| 命题 | Reference 原始可见性 / 依据 | Render 原始可见性 / 依据 |
| --- | --- | --- |
| K1 | clear / 高柜正面可见多块并排的深色大型门板，门板间有连续竖向接合缝。 | partial / 高柜正面可见相邻的大型灰色门板，其间有竖向接合缝。 |
| K2 | clear / 深色高门上方有一排较矮的浅色前面板，之间有清晰的横向分界。 | partial / 灰色高门板上方可见一排较矮的白色面板，中间有横向分界。 |
| K3 | partial / 右侧低柜可见三块上下排列的抽屉样前面板及重复的水平接缝，右端被裁切。 | clear / 右侧低柜正面可见并排的竖向门板，未见上下叠置的抽屉面板或重复水平分界。 |
| K4 | clear / 高柜右缘与较低台面柜相接，高柜侧边形成明显的竖向交接边界。 | clear / 高柜右缘与右侧较低台面柜并置，高低交接清楚可见。 |

present/partial 的局部正证据可以比较；absent 需要相关局部 clear，否则降为比较 Unknown（原始回答不改写）。任一条 unknown/unavailable 不阻塞其他条目。两侧明确相同为 structure_consistent，不同为 candidate_structural_layout_mismatch。比较只是结构命题是否一致的未审核诊断，不等于正确性或 3D 错误 GT。若 Reference 验证未支持种子，则单独保留 not_confirmed，不让人工式候选自动变成真值。

PNG 中的边界来自两侧独立响应的原始坐标，未修补、配准或从参考复制；它们是外立面接合/组间交接线，不是精确 Mask。回答 absent 时没有可靠边界允许空线段，不能虚构缺失位置。

## Scene Graph 辅助证据的实际可用性

在 Project e results/runs 的已有 Scene Graph/scene summary/object metadata JSON，以及这个正确 Run 的 artifacts/workspace/exports 中检查后，没有找到 bw_0073 对象级图结构或柜门/抽屉几何导出。可用的是 camera_parameters.json；`vlm_direct_grounding_bw0073/geometry_audit.json` 只是 ROI 重叠审计。bw_0074 的 Scene Graph 属于另一场景，未借用。没有打开 blend 或从历史 Agent Python 推导“实际几何”。

因此门板/抽屉几何佐证 **N/A**，不是查询发现几何缺失。相机元数据仅支持坐标和协议限制说明。即使未来有对象名称，也必须区分 Agent 名称声明、实际板件几何、可见门缝和语义柜体；外观接缝不能直接升级为门后内部隔板 GT。

## 迁移性、失败与限制

这轮从书架“内部隔板”迁移到厨房“外立面接合与高低柜关系”，复用的是 Reference 先冻结、独立单图回答、局部可观察性和三态比较原则，没有使用书架厚度、世界 Z 层数或 AABB 隔板阈值，也没有逐柜体实例匹配。

structure_consistent 表示对应粗属性的回答一致，可能遗漏面板比例、数量及细节；candidate_structural_layout_mismatch 表示已得到真实回答差异，仍可能受柜体对应、视角、遮挡或对装饰缝/拉手的识别错误影响。unknown/unavailable 是本轮没有充分证据的条目，不伪造成一致或缺失。

单场景/单次每侧不能证明跨场景稳定检出率；没有独立人工结构 GT，没有新正负对照，也没有对象几何佐证。Reference 右边界有截断，Render 与 Reference 视角不同，固定 ROI 含背景/留边的比例不同；因此不比较线坐标的直接距离，不将门板数量差直接解释为三维拓扑错误。要进入正式 Spatial，需独立审核结构身份、局部对应和可见性，并在同相机受控柜体扰动中校验检出与弃权行为。

保留的失败/未验证项是：对象级几何缓存缺失；“至少两块门板”的粗命题对门板数和比例变化不敏感；抽屉样外观不证明真实抽屉机构；当前没有同相机因果对照来排除历史视角影响。没有把这些限制隐藏在三个一致结果之后。

## 审计与复现

匿名路径、fork_turns=none 和工具轨迹限制了额外信息读取；共享文件系统不是硬隔离，持久日志不能独立重读实际父任务正文，故不宣称严格盲测或固定 API 等价。原始回答、完整实际输入、模型标识和子会话用量都保留。冻结时间早于验证；两份提示除匿名路径外一致，输入图片逐字节相同于准备图；源文件大小/mtime 未变。

实际会话数 2，合计 31.390 秒；Token {"input_tokens": 95133, "cached_input_tokens": 83200, "cache_write_input_tokens": 0, "output_tokens": 1294, "reasoning_output_tokens": 587, "total_tokens": 96427}。统计包含验证子会话平台/图像工具上下文，排除主 Agent；缓存和推理分别已包含于输入/输出，货币成本未知。没有付费 Ofox 请求。

4 项纯 CPU 单元测试在验证前通过：局部 partial 正证据保留而 partial 缺失弃权、单条 Unknown 不阻塞其他差异、缺失字段不补造、非法坐标仅使受影响项不可用。它们验证程序行为，不等于真实视觉准确率。

只重放已有回答并画到新目录，不调用模型：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/kitchen_structural_transfer.py --stage report --work /srv/lab-disks/disk2/users/xymo/projects/e-harness/runs/kitchen_structural_e7f38ad2e3c848ac89a94640e5351baf --output results/kitchen_structural_transfer_bw0073_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_kitchen_structural_transfer.py'
```

输出只包含 comparison.png、structural_evidence.json、report.md；模型输入、冻结候选与会话记录在 runs 目录，无 HTML。完成后停止，不调整提示或扩展图片。
