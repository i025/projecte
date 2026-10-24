# Region-first 端到端泛化验证

**两张图都得到合理的粗粒度 VLM Plan，但冻结的定位链路没有稳定保留这些区域的主要内容。当前 B2 不适合直接作为正式自动默认定位器。** 它在 bw_9064 与矩形完全相同；在 bw_0073 仅获得岛台区的部分支撑，且进一步裁掉台面内容。本轮没有修改 B2、参数或词表，也没有补框。

所有内容检查是助手基于参考 RGB 的自动初审，不是人工像素审核。全部 Evidence 保持 `reviewed:false`、`mask_reviewed:false`、`reliability:0`，没有正式还原分数。

## 实际流程与输入

每张图各发送一次独立的原始参考 RGB（最长边 1024，清除附加元数据），沿用 bw_0074 成功的 System/User Prompt、Schema、解析器、`openai/gpt-6-sol` 和 OfoxTunnel。没有在 Prompt 中加入任务预期区域名称，没有发送 Agent Render，没有要求 Anchor、Relation、Mask 或 bbox。

定位最长边统一为 1536；bw_9064 使用 1536×864，bw_0073 使用 1536×837。两方案使用同一实际 Plan、同一模型候选缓存和同一坐标网格。原图、Run 输入与任务 ID 的关联记录在各图的 input.json；原始/已暂存参考文件按字节直接比对一致，没有哈希校验。

- **A**：复用已有冻结名词映射、位置窗口和最初矩形上下文规则，匹配缓存模型输出的外接框。名称匹配优先于内容词匹配；无名称匹配时使用内容词，沿用 10% 横向/4% 纵向上下文扩展等原规则。
- **B2**：把同一 A 窗口和同一内容线索输入冻结的 `content_hints`、`coarse_polygons(..., snap=True)`，不改变源码、参数、词表或边界。没有可靠 A 窗口的 Region 保留为 N/A，不送入 B2，原 Region ID 仍保留在输出中。
- 缓存来自 SAM3 Text / Visual 已有模型预测；没有重新推理，也没有直接使用历史 `prompt_bbox`、manifest 人工区域框或上一轮五个表面采样框替代新 Plan。历史 Visual 预测仍有人工/助手 bbox 提示来源，所以本实验依赖已有提示分割缓存，不能声称对陌生图无需候选即可全自动运行。

## VLM Planning 初审

| 图片 | 实际 Region Plan | 初审结论 |
| --- | --- | --- |
| bw_9064 | R1 桌椅区；R2 冰箱区 | 数量 2 合理，包含主要可见家具；桌椅合组，没有逐把椅子拆分。背景不单列符合协议。没有明显重复或可确认的幻觉。 |
| bw_0073 | R1 窗边水槽区；R2 中央岛台区；R3 后方料理区；R4 右侧高柜区 | 数量 4 合理，有明确的局部功能意义；岛台含四把高脚椅和上方吊灯，没有拆物体部件。后方炉灶的可见范围被遮挡，标为 Uncertain，待人工确认。 |

没有确证的 Planning Failure。结构合法和初审合理不代表 Plan 已成为 GT。两份实际 JSON、原始模型文本和完整脱敏响应分别在 `bw_*/vlm_plan.json`、`vlm_response.json`、`provider_response.json`。

## 逐 Region 的主要发现

| 图片 / Region | A | Frozen B2 | 失败归因 |
| --- | --- | --- | --- |
| bw_9064 R1 桌椅区 | 桌椅大致保留，盆栽叶片上部遗漏 | 与 A 逐像素相同，遗漏仍在 | 部分 Grounding Failure：名称中的“椅”主导初始包络，“绿植”无法匹配冻结的“盆栽”；B2 只能向内调整，不能修复上游遗漏 |
| bw_9064 R2 冰箱区 | 可见冰箱主体大致完整 | 与 A 逐像素相同 | 外沿、阴影为 Uncertain；没有像素 GT，不声称边界准确率 |
| bw_0073 R1 窗边水槽区 | N/A | N/A | Grounding Failure：相关 window/cabinets/countertop 缓存存在，但冻结词表不能关联此描述 |
| bw_0073 R2 中央岛台区 | 主要依赖椅子缓存；仅部分台面前沿在框内，吊灯等主要内容遗漏 | 进一步裁掉台面内容，趋近“椅子区” | 初始 Grounding Failure，加单窗口边缘收缩引起的 Conflict / Boundary Failure；不是区域间冲突排序问题 |
| bw_0073 R3 后方料理区 | N/A | N/A | Grounding Failure：缺少类别关联，“后方中央”不能被既有位置解析器定位；另有炉灶可见性 Uncertain |
| bw_0073 R4 右侧高柜区 | N/A | N/A | Grounding Failure：柜体/高柜/抽屉柜与 cabinets 缓存缺少词表关联 |

详细判断和原因见 [initial_review.json](initial_review.json)。原图与每个 Region 的独立对照见 [comparison.html](comparison.html)，每区还保存 `per_region/R*.png`。全景四面板为 `bw_*/comparison.svg`，其中包含原始中文 Plan；使用客户端字体显示，不下载字体或依赖。

## 辅助几何统计

“有窗口”仅指可生成几何候选，不表示语义完整。缺失 Region 的空 Mask 明确标为 Grounding Failure，不参与任何正式评分。

| 图片 | 有几何窗口 / 规划数 | A ROI 并集 | B2 ROI 并集 | A 重叠 | B2 重叠 |
| --- | ---: | ---: | ---: | ---: | ---: |
| bw_9064 | 2 / 2 | 16.72% | 16.72% | 0% | 0% |
| bw_0073 | 1 / 4 | 19.64% | 13.57% | 0% | 0% |

bw_0073 唯一可用的 R2 从 252472 像素缩到 174482，减少约 30.89%，同时丢掉更多台面，不能把面积减少当成准确率提升。本轮 A 本来就没有重叠，B2 没有执行区域对的冲突边界决策；因此**没有证据证明它在新 Plan 下能减少无意义重叠而不损失重要内容**。未分配区域保留给 Global/Dense，本轮没有运行这些下游评价。

## 五个结论

1. **Plan 是否合理？** 两图的粗功能分组基本合理，没有明显过细拆分；bw_0073 后方炉灶的可见性需人工核实。全部仍是候选。
2. **A/B2 哪个保留内容更好？** bw_9064 两者相同且桌椅区均部分漏项；bw_0073 的 A 比 B2 多保留一部分台面，但两者都没有完成岛台+椅子+吊灯整组定位，其他三区均失败。
3. **是否减少无意义重叠且无损？** 本轮没有重叠可减少，反而出现额外内容裁剪，不能宣布泛化成功。
4. **失败主要来自哪里？** 主要是 Plan 到缓存的名词关联、位置解析和初始包络；B2 的保守护栏仅保护已识别内容，无法保护未识别的台面和吊灯，并可能加剧边界损失。Planning 本身没有被确证为主要失败来源。
5. **是否适合作为正式默认？** 当前不宜直接作为自动默认定位器。粗 ROI 表示仍可保留；现有 B2 继续作为冻结、待人工审核的候选方法。定位链路需要后续独立改进与验证，本轮不实施任何修补。

## 实际调用、检查与成本

| 图片 | HTTP / finish | 输入 Token | 输出 Token | 总 Token | 请求耗时 |
| --- | --- | ---: | ---: | ---: | ---: |
| bw_9064 | 200 / stop | 857 | 143 | 1000 | 7.515 s |
| bw_0073 | 200 / stop | 857 | 286 | 1143 | 9.490 s |

共 **2 次付费请求、2143 Token、约 17.005 s 请求时间**；没有重试或验证请求。供应商未返回费用金额，标为 unknown，不估算费用，也不另查余额。输出上限每图 1500 Token，没有设置长推理输出。接口返回少量 reasoning_tokens（45/90），保留在原始 usage 中。

请求前 **118 项 CPU 测试通过**，覆盖单图负载、成功 Prompt、Schema/解析器、禁重试、每图与总预算、历史提示框不用于新窗口、词表未知时失败及脱敏。最终离线检查还核对：原始两次响应能重新解析、ROI ID/尺寸/像素坐标、多边形栅格化、未审核状态、六个独立区域图、HTML/SVG 链接、B2/词表与冻结快照文本一致、请求次数和凭证未写入产物。见测试日志与 validation.json。

未执行 Agent、Blender、SAM3、DINO、五类能量、结构评分或局部扰动；没有修改历史产物、正式 Runtime、评分公式、权重或 Git 提交。

## 不产生新付费请求的复现

在项目根目录复用本轮实际 Plan，选择不存在的新目录：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /home/xymo/environments/relateanything-inference/bin/python \
  scripts/region_first_e2e.py replay \
  --source results/region_first_e2e_generalization \
  --output results/region_first_e2e_generalization_replay
```

`replay` 只读取保存的响应并重新定位、绘图，不走 request 阶段。原始实际 VLM 输出已保留；API 预算已用满，不应再次运行付费 request 阶段。

代码改动仅新增实验脚本 `scripts/region_first_e2e.py` 和 CPU 测试 `tests/test_region_e2e.py`。本轮到此停止，等待人工审核。
