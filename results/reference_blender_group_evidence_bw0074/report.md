# bw_0074/R3 Reference–Blender Group Evidence 离线对照

全部 reviewed=false、provisional/debug，不生成正式分数。本轮新增 Blender/GPU/VLM/分割调用均为 0；只读取已有 JSON、PNG 与 ID 数组，新增三个输出文件及一个轻量复现脚本。历史结果和 Reference Evidence 未修改。

## 属性级结论

| 属性 | Reference | Render | 可比较结论 |
| --- | --- | --- | --- |
| 集合存在 | 参考候选及历史 VQA yes，无审核 GT | 历史 VQA yes；候选几何有 6437 个 ID 支持像素 | 保留旧 satisfied 作为回答一致；真实唱片存在性仍 Unknown，ID 不能证明类别 |
| 语义身份 | 后续完整/局部分类均 vinyl_sleeves | 后续完整/局部分类均 ambiguous；对象名含 VINYL | Unknown；名称是建模意图，薄盒几何也不能区分书籍/封套 |
| 粗空间分布 | 历史问题是至少两个独立柜格，回答 yes | 同问题 yes；另有三个世界高度层的实际采样像素 | 定性回答一致；高度层不等于柜格，缺少参考侧同定义定位，分布差值 N/A |
| 排列方向 | 可辨认封套主要竖直：yes | 同问题 yes；几何接近世界 +Z（最大偏角约 3.43°） | 图像竖直与世界竖直的轴定义不同；缺少参考连续测量，方向误差 N/A |

历史真实模型回答来自 **Codex Subagent / gpt-6-sol**，并非 Ofox。原始字符串保存在输出 JSON。后续身份问题是 post-hoc exploratory，问题、裁剪和可见范围不同；不能把 ambiguous 当作对旧二值回答的直接逻辑否定，也不能追溯改写三个 satisfied。局部输入仍有残余上下文，Render 局部只包含部分层架，不能视作严格上下文因果消融。历史已有 Render 知识，本轮也不是盲测。

## 可重算的生成侧可见分布

原始 ID 网格 512×347，分母为候选主体 ID 的并集 6437 像素；不在放大图上计算面积。三层归属使用已保存的对象 ID 映射，并核对其基底世界 z 范围，没有按图片位置猜层。

| 世界高度提示 m | 候选 Mesh | 有采样像素 Mesh | ID 像素 | 占 Group 像素 | R3 外像素 |
| --- | --- | --- | --- | --- | --- |
| 1.45 | 43 | 41 | 1519 | 23.60% | 301 |
| 1.90 | 99 | 94 | 3165 | 49.17% | 331 |
| 2.36 | 99 | 93 | 1753 | 27.23% | 173 |

三层像素守恒（1519+3165+1753=6437）。228/241 个候选主体在这一次低分辨率 ID Pass 中至少贡献一个像素；这不是唱片数量，也不是历史全分辨率 PNG 的可见实例数量。13 个无像素 Mesh 可能被遮挡或未被低分辨率采样，不能直接判定缺失。28 个标题部件因归属未审核而排除，但仍正常遮挡。三层由几何归属区分，不意味着 Reference 已确认有三个可匹配柜格。

### R3 外 12.51%

805/6437=12.5058% 的 Group 像素在固定 R3 外，**全部位于左缘**；三层分别 301、331、173 像素。其原生网格范围为 [347, 89, 359, 176]（xyxy，右下界不含）。同坐标展示范围为 [853, 220, 882, 433]，仅是低分辨率 Mask 的最近邻映射，不是精确历史边界。

这证明当前生成侧候选支持超出固定参考 ROI，支持“该 ROI 对当前视图的生成集合覆盖不足”的诊断。它不能单独区分参考 ROI 范围不足、Agent 布局偏移或历史相机差异。Reference 相机未知；历史保存相机 z=1.71 m、镜头数值为 26 mm，不能由数据名中的 30mm 推定内参，也不满足固定 T0 合规证明。未移动 ROI、未做内容对齐或重新投影来提高结果。图中详细窗口仅用于展示 R3 及左侧条带。

## 比纯 VLM 增加什么

Scene Graph 增加可追溯的 241 个主体候选、几何层归属、世界范围及轴方向；Group-ID 增加考虑遮挡的像素支持、投影范围、分层面积占比和 ROI 外支持位置。它们使生成侧部分 Spatial/Statistical 属性成为可重复测量的数据，不再只有 yes/no。

但双方尚无同定义、可靠的参考 Group Mask、分层定位或方向测量，语义身份也未审核，因此不能计算可信的 Reference–Render 分布误差、Mask IoU、密度误差或正式 Spatial/Statistical Energy。物体名称不是语义 GT；ID 不包含类别；像素面积不是数量；对象中心直方图不是可见密度。世界 +Z 近似竖直可检验建模组织，却不能替代参考视角的图像关系验证。仍需要参考侧粗集合定位/可见性审核、语义验证和可比较相机条件。

## Mask 技术限制

复用一次已有 Cycles IndexOB CPU Pass（512×347、1 sample、alpha threshold 0.5）；本轮未渲染。Mask 保留历史保存相机，但它是当前读取器状态下的低分辨率支持，**不是历史 PNG 的精确 Mask**。旧记录包含 newer-file 警告 `File written by newer Blender binary (402.67), expect loss of data!`；清理阶段另有 `ValueError: list.remove(x): x not in list`，当时输出完成且退出码 0。边缘无抗锯齿、透明材质阈值及细薄几何欠采样均有限制。BBox 代理的 8048 像素比 ID 多 1611，差值混合空包围盒、遮挡、排除标题和采样效应，不能称为纯遮挡率。

## 检查与复现

通过：原始 ID 与已存二值 Mask 一致；旧统计完整重现；241 个对象及层归属可解析；层像素和 ROI 外分区守恒；坐标转换与历史记录完全一致；读取前后源文件大小及 mtime 未变。未新增模型或正式评分测试。图像标签为英文以使用已有字体，JSON/报告保留中文语义。

从项目目录运行（必须指定未存在的新目录）：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_reference_blender_group.py --output results/reference_blender_group_evidence_bw0074_replay
```

输入路径及原始回答见 `group_evidence_comparison.json`。输出仅 `comparison.png`、该 JSON、`report.md`。结论：**生成侧部分空间/统计证据已更客观可测；跨参考和重建的可靠误差仍为 Unknown/N/A，不能升级为正式 Benchmark 成绩。**
