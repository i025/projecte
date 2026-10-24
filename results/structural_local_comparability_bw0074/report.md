# 结构证据局部可比较性：bw_0074/R3

**可以保留有依据的局部结果，避免整层 Partial 无条件阻塞所有条目；但不能凭拆分命题解决尚未建立的精确对应。** 本轮得到 3 条局部水平层板一致候选，保留 2 条已有的几何条件性结构差异假设；第二层冲突、左外框与完整柜格计数分别保持 Unknown。两条差异假设并非本轮新视觉识别成果，也未升级为确认缺失。

全部 reviewed=false、provisional/debug，正式 Spatial Energy=N/A。新增 VLM/子 Agent/Ofox/Blender/GPU 调用均为 0；未运行历史 Agent 代码、修改 ROI、历史证据、权重或正式公式。

## 逐命题比较

| ID | 命题 | Reference 可观察性 | Render 可观察性 | 结果 / 依据 |
| --- | --- | --- | --- | --- |
| H1 | 第 1 条内部水平层板在相邻开口间可见 | visible | visible | structure_consistent / local_observations |
| H2 | 第 2 条内部水平层板在相邻开口间可见 | visible | visible | structure_consistent / local_observations |
| H3 | 第 3 条内部水平层板在相邻开口间可见 | visible | visible | structure_consistent / local_observations |
| V1 | 第 1 个粗开口内存在将左右分开的内部隔板 | visible | partial | candidate_structural_layout_mismatch / conditional_geometry |
| V3 | 第 3 个粗开口内存在将左右分开的内部隔板 | visible | partial | candidate_structural_layout_mismatch / conditional_geometry |
| V2_review | 第二层疑似内部隔板：参考提取存在冲突 | unknown | partial | unknown / insufficient |
| frame_left | 固定 R3 内的完整左外边框是否可比较 | visible | cropped | unknown / insufficient |
| exact_counts | 整层完整独立柜格数量是否相同 | unknown | partial | unknown / insufficient |

H1–H3 的证据分别是双方保存的内部水平层板线段，几何还提供对应的连续薄水平板支持。原先“左边界超出 ROI”影响完整层范围，但不否定这些已报告的可见线段。按粗开口顺序比较的是层板存在性，不计算精确位置误差，仍待人工审核。

V1/V3 保留 Reference 明确内部隔板候选及生成侧全深薄板查询为空的条件性证据。Render 对应粗开口部分可见，但**该参考隔板在 Render 的精确对应位置与可见性仍 Unknown**；不能把粗开口顺序当作精确位置匹配，也不能把旧 zero/partial 改成已确认 absent。故 image_only_status 仍 Unknown，仅在“孤立全深薄板几何表示、粗层次可比”的前提下保留 candidate_structural_layout_mismatch。没有从 Reference 像素坐标复制隔板位置到 Render。

V2 的原始“0 隔板、clear”与事后参考图审核候选冲突，不能因为 Render 也报 0 就判一致。冲突仅影响此命题，H2 等其他条目继续可用。精确柜格计数本就依赖完整边界与参考清单，因此继续 Unknown。左外框属于外边界命题，明确不计入内部隔板；其在固定 R3 中被裁切，不等于整个书柜不可观察。

这是诊断状态列表，不是总分，不把隔板存在与柜格合并当作两次独立惩罚，也不将 Unknown 填成零。

## Reference 第二层审核与漏检处理

单独的 `reference_row2_review.png` 同时展示第二层整段及疑似缝隙放大图。裁剪来自先前 U3/U4 候选边界，仅用于事后审核，未加入原始 VLM 线段。审核状态 unreviewed，`possible_internal_divider=null`。判断应检查该竖条是否连接上下层板、具有柜体厚度/饰面、确实分开开口；排除书脊、封套边缘、阴影和外框。不能由名称或颜色独立确定类别。

防止漏检造成不完整证据的最小机制是：保留原始自动提取结果、另记冲突/遗漏候选、暂停依赖完整清单的数量结论，并提出有定位的人工审核项。本轮没有自动纠正漏检，也没有证明未来提取器能发现所有遗漏。新方法不是将事后审核意见伪装为 Reference GT。

## 几何查询漏检风险：实际重放和合成探针

旧查询在所有现有 Mesh AABB 上重放，结果仍为 0 个内部全深薄竖板候选。以下 **synthetic AABB probes** 仅验证原查询的表示限制，不渲染、不修改历史场景：

| 探针 | 是否被原查询接纳 | 含义 |
| --- | --- | --- |
| isolated_panel | True | Simple full-depth isolated panel is retained |
| thin_full_depth_panel | True | Thickness alone is not rejected; pixel visibility may still be poor |
| thin_shallow_panel | False | A visible shallow divider can fail the 80% depth/front-back rules |
| panel_merged_with_shelf | False | A merged object AABB is wide, hiding internal partition topology |
| tilted_panel_25deg | False | World AABB becomes too wide despite the source panel being thin |
| outer_frame | False | Outer frame is not an internal divider |
| same_shape_nonstructural_insert | True | Geometry-only rule can also accept a nonstructural insert of the same shape |

要区分“薄”与“浅”：旧规则没有最小 x 厚度门槛，独立且全深的极薄隔板仍会被接纳；浅隔板因深度不足被漏掉。合并 Mesh 的整体 AABB 和倾斜后的宽 AABB 会掩盖分隔结构；相同形状的非结构插片反而可能被误收。故查询为空不能证明任意形式的隔板不存在，查询命中也不能证明其结构身份。旧模型的 certainty、名称、Mesh 数量都不是几何或类别 GT。

## 同相机 synthetic 最小对照

使用 Pillow 绘制一个安全、确定性的正视正交 2D 柜框，画布 640×480，目标隔板 bbox 为 [313,80,327,400]。没有 Blender、光照随机变化或历史 Agent 代码。A/B 的观察窗口相同 [160,40,580,440]，两者都裁掉左外框；A 有内部隔板，B 只移除该隔板。C 沿用 A 几何、同一相机和像素坐标，仅将观察窗口改为 [360,40,580,440]，使隔板被裁掉；灰区表示未观察范围，未重新缩放或对齐。

| Synthetic 情形 | 目标位置是否可观察 | 比较结果 |
| --- | --- | --- |
| present | 是；左外框仍被裁切 | structure_consistent |
| absent | 是；相同位置明确无隔板 | candidate_structural_layout_mismatch |
| cropped | 否；源场景仍有隔板 | unknown |

这验证了“局部可观察的缺失”与“目标不可观察”能被确定性比较区分，也验证外框裁切不会无条件影响可见的内部目标。输入位置与存在性来自构造 Oracle，不是模型检测；标签仅 construction_expected、reviewed=false。**三个对照通过不代表 VLM 能识别隔板、理解裁切或可靠预测可见性。**

## 限制与下一步条件

历史 Reference 相机未知，Render 相机不同，粗层带顺序不能自动建立精确局部对应；已有 Scene Graph 读取器与原 PNG 逐像素一致性也未认证。当前两条差异仍是已知表示假设下的候选。若要升级，需要独立审核 Reference 第二层及其他隔板、可靠的局部对应范围、遮挡/裁切判定，以及覆盖浅板、倾斜板、合并几何的结构证据。以后可在同相机真实渲染正负对照中测试实际视觉提取器；本轮不扩展。

## 运行与复现

3 个 synthetic 比较对照、7 个 AABB 查询探针均按构造预期通过；历史原始回答逐字保留，源文件大小/mtime 未改变。单元测试另覆盖局部 Unknown 不影响邻条、裁切不能被几何强行升级、参考冲突阻止虚假一致。

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/structural_local_comparability.py --output results/structural_local_comparability_bw0074_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p 'test_structural_local_comparability.py'
```

目标目录必须不存在。输出 comparison.png、structural_evidence.json、report.md，另有要求的 reference_row2_review.png 与三个标明 synthetic 的构造图；不生成 HTML。完成后停止。
