# 冻结 B2 泛化验证：条件测试，完整结论仍受 Plan 缺失限制

用户已确认 bw_0074 B2 的区域粒度和大致完整性符合预期；这不是像素级语义 GT。原算法、参数和旧实验目录保持原样。源文件快照见 source_snapshot；freeze_note.json 记录人工反馈范围。未新增 VLM/API/模型推理、GPU、Blender 或 Agent 执行。

bw_9064 保存的 VLM Plan 是 unavailable/SSLError，后续组合响应未通过 schema 校验；bw_0073 没有保存 Region Plan。没有修复或补造它们。本轮完整 VLM→ROI 泛化测试因此跳过。作为有限补充，仅将既有 manifest 的 role=region 参考框输入冻结 B2，结果称为“缓存框条件几何测试”。框由历史助手从原图提出，不是 VLM 输出；两图均含 5 个旧区域，未补造家具组。

几何计算最长边 1536，所有坐标按统一比例从原图缓存框映射，A/B2 在同一网格比较。bw_0073 原图 7952×4333，缩放可能影响细结构。冻结的 noun aliases 没有扩充；不认识的类别记录在 content_hints.json。B2 不读取 Agent Render 或新 SAM 像素 Mask。

| 图片 | 方法 | ROI 数 | ROI 并集 | 重叠/全图 | 未分配 |
| --- | --- | ---: | ---: | ---: | ---: |
| bw_9064 | A_rectangles | 5 | 100.00% | 6.15% | 0.00% |
| bw_9064 | B2_frozen | 5 | 100.00% | 1.69% | 0.00% |
| bw_0073 | A_rectangles | 5 | 66.63% | 2.29% | 33.37% |
| bw_0073 | B2_frozen | 5 | 61.87% | 0.74% | 38.13% |

这些数值不是分割准确率。背景无需强制分配，主要内容保留情况仍需原图静态审核。逐区图、原图/Plan 状态/A/B2 对照见 comparison.html。

## 局部模拟扰动

直接调用未修改的 numerical_errors，计算 Appearance RGB L1、Spatial 粗边缘分布代理、Statistical 纹理/边缘分布代理。全部候选证据依旧 q=0/未审核；这是固定几何支撑上的数值敏感性实验，没有绕过审核运行正式 Benchmark、Observation 或 3D 分数。Semantic/Perceptual 为 N/A，没有语义验证或 DINO 推理。

统一将图像缩至最长边 768，选择 A 与 B2 同一 Region 的共同独占部分，在最大内接位置放一个小方块；无合适位置则记录跳过。局部编辑为颜色偏移 [60,-60,0]（裁剪到 RGB 范围）及半径 3 的高斯模糊，并保持其余像素完全不变。每个可用 ROI 有 1.0 强度的两种扰动；每图按可用内接方块大小选一个目标测试 0.25/0.5/1.0。目标按几何选择，不代表物体的重要性或真实重建失败。

同一编辑逐项比较矩形 ROI、B2 ROI、Global 和 POLICY.grid=2 的四个 Dense Patch，输出每项实际数值、零扰动 Baseline 和 Δ。没有将 Region 均值/最大值聚合成新的评分。Dense 应查看逐 Patch；其面积加权 RGB L1 平均等于 Global，因此平均也会稀释小范围错误。完整 CSV 与模拟图见 sensitivity.csv、synthetic_cases.json。空间/统计指标共享边缘代理，不能解读为相互独立。

## 复现

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /home/xymo/environments/relateanything-inference/bin/python \
  scripts/region_first_generalization.py --output results/region_first_generalization_repeat
```

输出目录必须尚不存在。只需现有 NumPy/Pillow/SciPy 环境与缓存，不联网或加载模型。测试日志、实际成本及完整性检查见 tests.log、validation.json。
