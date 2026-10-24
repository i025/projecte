# bw_0073：VLM Direct Region Grounding

**一次 VLM 调用为四个既定 Region 都返回了合法、非空的独立 Box 与 Polygon。本图中两者明显比历史 Grounding 更接近完整功能区域；Polygon 在岛台与吊灯分离表示上有实际收益，但不是所有区域都比 Box 更完整。** R1 的部分壁灯仍被 Polygon 遗漏，R3 的遮挡归属仍有冲突。所有结果都是 `reviewed:false` 的候选，不是语义 GT 或正式评价结果。

[完整总览和逐 Region 对照](comparison.html) · [总览 PNG](comparison.png) · [实际坐标](direct_regions.json) · [原分辨率坐标](native_coordinates.json) · [静态初审](initial_review.json)

## 实际输入与调用

本轮只使用 bw_0073。四区名称、位置和完整内容逐字来自上一轮实际文件 `results/region_first_e2e_generalization/bw_0073/vlm_plan.json`，复制为 `region_plan.json`；没有重新规划或在代码中写入预期位置。

Reference RGB 的原始尺寸为 **7952×4333**，原路径和对应任务来源见 `input.json`。请求复用此前由同一原始参考 RGB 得到的无标注整图（1024×558）；不裁图、不发送 Agent Render 或历史 Overlay。展示图使用 1536×837，全部方法使用相同视野。

使用 `openai/gpt-6-sol`、OfoxTunnel、现有 VLMClient/JSON 解析器，一次调用同时要求直接输出 bbox 和 1–2 个 Polygon，temperature=0.1，输出上限 2200 Token，关闭 JSON Mode、自动重试和额外验证请求。Prompt 保存于 `prompt.json`，实际脱敏响应保存于 `provider_response.json`、`vlm_response.json`。

调用为 **HTTP 200 / finish_reason=stop**，并通过四个 ID、范围、bbox 顺序、多边形顶点数、面积、自交等校验。没有修补坐标、移动顶点、补造缺失结果或进行冲突消解。

## 三种方法与坐标保存

- **A Historical**：原样复用上一轮 `bw_0073/B2_frozen` 的四张 Mask，历史词表关联和 B2 都没有重跑。预览 Mask 与历史文件逐像素一致；原分辨率 A Mask 仅作最近邻上采样，并明确记录来源。
- **B Direct Box**：只使用本次模型实际返回的 `bbox` 字段。
- **C Direct Polygon**：只使用同次返回的 `polygons`，同一 Region 的多块取并集，Region 间不裁剪。

四个实际 bbox 都与对应 Polygon 的外接矩形不同，见 `geometry_audit.json`。例如 R2 的 Box 为 `[335,108,687,857]`，而 Polygon 的包络为 `[333,110,680,855]`；后者只用于审计，没有生成或替代 B。

归一化点 `(x,y)` 按 `(x×7952/1000, y×4333/1000)` 映射到原图连续像素边界，原始归一化值不变。Mask 按像素中心采样；Box 为左上含、右下不含，多边形使用扫描线偶奇填充并取分块并集。0/1000 对应图像边缘，不将边缘点错误钳到最后一个像素。

`A_historical_native/`、`B_direct_box_native/`、`C_direct_polygon_native/` 保存原始分辨率的二值 PNG 和 `evidence.json`；一位存储避免大数组开销。无 `_native` 的目录是同源预览 Mask/Overlay，供逐区检查，不代替原分辨率结果。

## 逐 Region 的视觉初审

以下为助手基于原始参考内容的静态检查，没有人工审核的精确 Mask，不计算 IoU、Boundary F1 或准确率。

| Region | A Historical | B Direct Box | C Direct Polygon |
| --- | --- | --- | --- |
| R1 窗边水槽区 | N/A | 窗户、水槽、台面、下柜、搁板和壁灯大致保留；墙面与地板混入较多 | 主要水槽/台面/下柜得到保留，背景较少；部分上方壁灯落在外面，完整性不及保守 Box |
| R2 中央岛台区 | 主要只有椅子附近，岛台和吊灯遗漏 | 岛台、四把椅子、吊灯均被纳入；两者之间的后方料理区也被大面积带入 | 两块真正分离的 Polygon 分别表达吊灯和岛台椅子组，保留中间空隙；没有退化成只有椅子 |
| R3 后方料理区 | N/A | 后柜、石材背板和可见台面范围大致定位；包含前景吊灯下部、部分岛台边缘 | 粗缺口减少部分混入，没有吞掉整片岛台；仍存在前景吊灯和岛台后缘的归属冲突 |
| R4 右侧高柜区 | N/A | 柜体组与抽屉柜大致完整，带入顶墙及地板三角区 | 单块粗多边形较好地表达整组柜体的透视外形，背景较少，没有逐柜门拆分 |

**Uncertain**：R1 窗拱/壁灯边缘、R2 台面摆放物/椅脚边缘、R3 遮挡后的炉灶可见范围及前后景归属、R4 柜脚/接触边界。没有推断不可见结构。

R1 的两个 Polygon 实际相交，内部相交约 1166144 个原图像素，保存并集时只计一次；它不是完全分离的两块。R2 两块的相交为 0，实际实现了“上方吊灯 + 下方岛台”的不连续表示。没有为了更好看而删点、合并形状或裁掉冲突。

## 辅助统计，不是准确率

“有效非空 ROI”只表示几何坐标合法并能生成 Mask，不等于内容完整性通过。全部仍未获得人工审核。

| 方法 | 有效非空 ROI / 4 | 原图 ROI 并集 | 原图 Region 间重叠 | 原图未分配 |
| --- | ---: | ---: | ---: | ---: |
| A Historical | 1 / 4，且部分内容遗漏 | 13.58% | 0% | 86.42% |
| B Direct Box | 4 / 4 | 84.69% | 7.54% | 15.31% |
| C Direct Polygon | 4 / 4 | 59.93% | 1.36% | 40.07% |

Box 中 R2 包含了 R3 的整个 Box，R2/R3 重叠约占全图 **6.42%**；Polygon 将该对的重叠降至约 **1.30%**，但仍可见遮挡归属问题。总体重叠变化本身不是质量结论；可见收益主要是 R2 保留完整组件同时减少中间背景，代价和风险则包括 R1 壁灯遗漏。

未分配内容继续留给 Global/Dense；本轮没有执行它们，也没有修改正式重复计分或五能量聚合规则。

## 对五个问题的回答

1. **是否定位全部四区？** Box 和 Polygon 都为 4/4 返回了合法非空候选；内容质量仍有遗漏与 Uncertain，不能称 100% 分割准确率。
2. **Box 与 Polygon 哪个更完整？** Box 更保守，R1 的主要描述项保留得更多；Polygon 的 R2 多块表示在完整性和背景控制之间更合适。没有统一赢家。
3. **是否比历史 Grounding 更符合功能区域？** 本图静态对照支持这一判断，特别是原来完全未定位的 R1/R3/R4，以及完整岛台+吊灯组。但这只是单图、单次候选观察。
4. **Polygon 有实际收益吗？** 有，尤其是 R2 的分离组件和 R4 的整体斜边。收益不是“重叠最小”或“覆盖最大”；R1 的漏项证明 Polygon 也可能裁掉有效内容。
5. **复杂 SLIC/DINO/SAM3 是否还应是默认必经链路？** 本图不支持把复杂缓存关联链路作为粗 ROI 的必要前置。简单 Direct Box/Polygon 候选路线值得优先人工审核，复杂方法可保留为精细边界或 Anchor 的按需辅助。本轮没有比较这些模型本身的全部能力，也没有足够证据自动更换正式默认方案。

## 实际成本与检查

- 新付费请求 **1 次**，无重试、无额外模型验证；输入 **1300 Token**、输出 **1183 Token**、总计 **2483 Token**，耗时 **20.089 s**。输出 usage 含 reasoning_tokens=920，但实际回答仅为要求的 JSON，没有解释性推理文本。
- 供应商未返回费用金额，记为 unknown，没有查余额或估算账单。
- 请求前 **125 项 CPU 测试通过**，含 Schema、非法/退化/自交坐标拒绝、原分辨率映射、边界像素、不连续 Polygon、Box 独立性、PNG/加载器/可视化和单次预算检查。
- 原分辨率二值 Mask 和 JSON 尺寸检查、历史预览像素一致性、原始响应重解析、坐标未修改、HTML 链接和离线复现检查见 `validation.json`；测试日志保留在输出目录。
- 没有新依赖、GPU、SAM3、DINO、SLIC、Blender、Agent 执行、局部扰动或五类能量/正式 3D 评分。B2 源码/参数/词表、历史 Run 和旧结果没有修改，未自动提交 Git。

## 不产生新 API 请求的复现

在项目根目录选择不存在的新目录：

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /home/xymo/environments/relateanything-inference/bin/python \
  scripts/vlm_direct_grounding.py replay \
  --source results/vlm_direct_grounding_bw0073 \
  --output results/vlm_direct_grounding_bw0073_replay
```

`replay` 读取保存的实际回复重新转换与绘图，不调用模型。当前付费预算已用完，不应再次运行 request。

本轮新增源码为 `scripts/vlm_direct_grounding.py` 与离线测试 `tests/test_direct_grounding.py`。完成这次单图实验后停止，供人工审核。
