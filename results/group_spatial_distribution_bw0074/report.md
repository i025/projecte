# bw_0074/R3 集合粗空间分布对照

全部 reviewed=false、provisional/debug。仅离线读取已有图像、Scene Graph、ID 数组和历史回答；新 Blender/GPU/VLM/子 Agent 调用均为 0。未调整 R3、历史证据、五类 Energy 或权重，不计算正式分数。

## Reference 先行与冻结

本轮先查看原始 Reference 和 R3 局部，按可见水平层板与竖向隔板提出 **4 个层带、7 个粗空间单元**，随后将候选写入只读 `/srv/lab-disks/disk2/users/xymo/projects/e-harness/runs/group_distribution_1792771996838547599/reference_frozen.json`，才在本轮读取 Render/ID。前三层各有两个可辨认柜格；唱机下层另保留一个不确定单元。没有按 Blender 三个世界 Z 值决定 Reference 划分。BBox 只是粗检查窗口，不是 Group Mask，不声明精确边界。

这是主 Agent 的参考图静态候选，不是人工 GT 或自动 VLM 提取。此前对话已暴露历史 Render、三层结构和可见性统计，不能声称严格盲测。冻结后未根据生成图改写任何参考命题；通过字节相等检查而非哈希验证。

| 单元 | 参考可见范围 | 集合存在候选 | 粗密度 | 主要方向 |
| --- | --- | --- | --- | --- |
| U1 | 最上层左柜格 | yes | dense | upright_or_leaning |
| U2 | 最上层右柜格 | yes | dense | upright_or_leaning |
| U3 | 第二层左柜格 | yes | dense | upright_or_leaning |
| U4 | 第二层右柜格 | yes | partial | upright_or_leaning |
| U5 | 收录机层左柜格 | yes | sparse | upright_or_leaning |
| U6 | 收录机层右柜格 | yes | dense | upright_or_leaning |
| U7 | 唱机下层可见柜格 | unknown | unknown | unknown |

dense/partial/sparse 仅表示该可见柜格内的定性占据：大部分横向跨度有重复封套、封套与其他内容/间隙共存、小局部簇。没有转换为面积比例、实例密度或数值误差。右缘柜格范围被图像截断。U7 左缘薄片类别和遮挡不明确，三个属性均 Unknown；没有为了得到第四层目标而补造存在性。

## 双方粗对应与属性结论

生成侧沿用 241 个主体候选 ID；G1/G2/G3 按自身可见像素的图像高度排序，分别来自已保存的世界高度层 2.36/1.90/1.45。对应 ID 像素为 1753/3165/1519。命名和几何层归属不能变成 Reference 柜格标签。28 个无审核归属的标题部件未纳入。

| 参考范围 | 生成候选 | 对应依据 | 可比较结论 |
| --- | --- | --- | --- |
| F1：U1/U2 | G1 | 可见最上层陈列、下方另有陈列及收录机层 | 重复薄片主要竖放的粗形态一致；Reference 两柜格而 Render 看似长柜格，单元对应 Unknown |
| F2：U3/U4 | G2 | 收录机层正上方、且上方另有陈列 | 候选差异：Reference 右格含扬声器/间隙，Render 更连续；定义和范围不完全一致，不计算密度差 |
| F3：U5/U6 | G3 | 图像内可见收录机作为上下文定位线索，两侧有陈列簇 | 两侧簇的粗布局一致；分隔形式不同，不能确定逐柜格对应 |
| F4：U7 | 无可靠集合层对应 | 下方唱机区域可见，但参考目标类别不确定 | Unknown；ID 中没有第四候选层不能推出 Confirmed Missing |

以上是图像结构层面的未审核初审，可使用 coarse_consistent / candidate_difference / unknown；唱片类别是否匹配仍 Unknown。无法提供对应参考测量的连续密度、可见面积、方向角误差均 N/A。未将一个生成层面积分摊给两个参考柜格，也不重复计分。没有以“排序相同”证明物理柜格对应：候选依据同时包括可见层板顺序、收录机与唱机上下文；上下文用于定位，不用于证明唱片类别。

上两层及收录机层的 Reference 竖向分隔，在 Render 中未见明确对应，属于可审核的边界/组织差异候选，不能立即确认为建模缺失。三项旧 VQA yes/yes/yes 和 satisfied 原样保留，只适用于原始 Group 范围，不能传播为七个单元逐格已验证。独立类别问题中 Reference 为 vinyl_sleeves、Render 为 ambiguous，故 VINYL 名称、薄盒几何和 ID 支持都不能补足语义类别 GT。

## 固定坐标可比性检查

保持 1920×1300 Render 等比缩放为 1258×852、置于 1258×855 的 (0,1)，无内容对齐；R3 坐标不变。以下是同坐标参考窗口内的生成侧 ID 采样数量，**不是对应柜格占据率，也不是集合缺失判断**。

| 固定参考窗口 | G1 像素 | G2 像素 | G3 像素 |
| --- | --- | --- | --- |
| U1 | 0 | 0 | 0 |
| U2 | 0 | 0 | 0 |
| U3 | 528 | 639 | 0 |
| U4 | 827 | 904 | 0 |
| U5 | 0 | 840 | 954 |
| U6 | 0 | 0 | 0 |
| U7 | 0 | 0 | 1 |

不同生成层跨入同一个参考层窗口，说明直接逐窗口比较会混淆相机/布局与局部集合变化。参考窗口覆盖外的 R3 内支持为 939 像素（含粗框间隙），没有强制分配。R3 外全部 805 像素保留，占 6437 个 Group 像素的 12.5058%，位于左缘。图中仅将显示窗口扩展到包含该条带，没有移动/扩大评价 ROI。

## 相机及技术限制

Reference 相机未知；历史相机高度 1.71 m、焦距数值 26 mm，未满足正式固定 T0 合规证据。视点改变可影响柜格投影高度、宽度、竖向隔板可见性、集合被遮挡的比例及固定 ROI 截断。对上下层顺序、收录机两侧簇可作有限粗描述；对分格数量、密度和固定像素覆盖的影响更大，当前不能分离相机与建模因素。

ID 是已有 512×347、1 sample 的 Cycles IndexOB 支持，保留已存相机但不是历史 PNG 精确 Mask。已有 newer-file 读取器兼容警告；透明阈值、无抗锯齿边界和薄片欠采样会影响像素分布。241 Mesh/228 有采样 ID 不等于唱片数量，像素面积也不是唱片密度。Reference 未有同定义 Group Mask，因此面积与连续密度误差保持 N/A。

## 成立的结论与下一步条件

少量参考粗单元能将全局“多柜格、主要竖放”细化为：上方连续陈列、第二层混合音响/间隙、收录机两侧簇、下层不确定内容；生成侧 ID 使这些候选的像素支持和 ROI 外分布可以复算。当前可形成有上下文解释的粗对应与差异候选，但尚未获得可靠的一对一柜格对应或连续分布误差。

后续需先由独立人工审核参考柜格、边界、语义身份与可见性；在新受控样本中已知同一相机内外参和构图、冻结单元后，对集合位置/排列作预先定义的扰动，再检查 coarse_consistent 与 candidate_difference 能否区分目标变化。不能以任意固定相机重渲染未知相机的现有 Reference 来宣称配准。若要连续密度，应先定义相同的可见面积分母、完成两侧粗 Group 定位和遮挡规则审核；否则继续使用定性占据并允许 Unknown。统一相机也不能自动解决类别歧义和隔板缺失造成的对应失败。

## 检查与复现

已通过已有统计重现、7 个参考窗口范围/互不重叠检查、ID 像素守恒、冻结文件未变及历史源文件大小/mtime 未变检查。结果保持 reviewed=false；没有模型准确率或正式 Energy 测试。

从项目目录执行，目标目录必须不存在：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_spatial_distribution.py --reference-frozen /srv/lab-disks/disk2/users/xymo/projects/e-harness/runs/group_distribution_1792771996838547599/reference_frozen.json --output results/group_spatial_distribution_bw0074_replay
```

该命令只重放冻结候选和缓存，不能重现一个严格盲测。输出 comparison.png、distribution.json、report.md，无 HTML。完成后停止。
