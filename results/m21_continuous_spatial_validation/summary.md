# M2.1 Continuous Spatial Evidence Validation

**reviewed:false · provisional/debug · Synthetic Oracle；没有正式 Spatial 分数。**

复用 M1 RGB、相机记录及 Object-ID 支持，不重新执行 M1/M2，不运行 Blender/GPU/VLM。
离散关系、连续中心距离、可见边界间隙是三个不同量。旧 M2 回答与证据原样保留。

| 测量 | Baseline Reference | Changed | Changed − Reference |
| --- | --- | --- | --- |
| 旧 VLM left_of | yes | yes | satisfied（不修改） |
| Oracle bbox 中心 left_of | True | True | 离散顺序不变 |
| 水平中心间距 / 图宽 | 0.408203125 | 0.224609375 | -0.18359375 |
| 共同行平均边界间隙 / 图宽 | 0.18415178571428573 | 0.00638640873015873 | -0.177765376984127 |
| 共同行平均边界间隙 / px | 47.142857142857146 | 1.6349206349206349 | -45.50793650793651 |
| 相对垂直偏移 / 图高 | 0.044921875 | 0.044921875 | 0.0 |

中心使用可见 Object-ID Mask 的紧外接框中心，复用 measure_pair/compare_pairs；不是 Mask 质心或完整物体三维中心。
边界间隙是在两物体均有像素的每一行，计算第二物体最左像素左边缘减第一物体最右像素右边缘，再对全部共同行取平均；没有共同行时为 N/A。它不是外接框包络间隙，亦不表示三维距离或确认无其他内容的空隙。

## 结果与互补性

两个几何仍保持左右顺序，中心间距与可见边界间隙均减小，因此无需把 satisfied 改为 violated。
已有 Global Appearance=0.03928318397671569；它响应 RGB 差异但不能直接说明间距减小。本轮连续量提供该投影几何解释，既有条件 Energy 数值原样引用，不改公式、权重、聚合或 Runtime blocked。
固定 ROI 的已有 Appearance 诊断在 JSON 中保留；不重新定位 ROI，不把各诊断相加。

## 控制验证

- 不变输入：offset change 为零，见 JSON → controls.unchanged。
- 相同二维平移 (+5,+3) px 且不裁切：{'dx_pixels': 5, 'dy_pixels': 3, 'clipping': False, 'changes': {'relative_distance': 0.0, 'delta_y': 0.0, 'boundary_gap': 0.0}, 'passed': True}。
- 一个对象定位不可用：{'reason': 'First object localization withheld, not confirmed missing', 'values': {'left_of': None, 'relative_distance': None, 'delta_y': None, 'boundary_gap': None}, 'passed': True}。
- 这些是 CPU Oracle 数学/接口控制，不是 VLM 或 RGB 检测有效性测试。

## 来源与限制

anchor/other 来自可信自制 Fixture 的 ID 映射；红色主体实际是长方体，蓝色为立方体，历史模型的“立方体”用词未回写。Oracle 标签没有参与生成新的 Reference RGB Evidence，未宣称从 RGB 自动获得对象对应。
逐侧检查 T0、相机内参、分辨率与保存的执行记录，确认 M2 图片像素与 M1 配对。本机额外验证 PNG Mask 与已有 object_id.npy 相同；公开复现可只用已发布 PNG，原始数组未公开时该项为 null。这些是对历史可信产物的离线读取，不是一次新的可信执行或完整文件真实性证明。
可见边界受采样、遮挡、透明度影响；共同平移不裁切时的二维不变性不适用于任意相机变化。没有可靠定位时返回 N/A，不判定 Confirmed Missing，不重复惩罚语义缺失。

红色可见外接框宽度由58 px变为54 px，中心因此不等于固定物体原点的投影。复用 helper 附带的 bbox_area_ratio_proxy 只作范围代理，不据此判断真实三维尺寸变化。

## 复现

从仓库根目录，在既有 NumPy/Pillow 环境执行；输出目录必须不存在：

```bash
python3 -B scripts/continuous_spatial_pilot.py --output /tmp/projecte-m21-new
python3 -B -m unittest discover -s tests -p 'test_*spatial*.py'
```

[对照 PNG](comparison.png) · [真实测量、控制及来源](spatial_diagnostics.json)。
本轮仅三个结果文件；没有新的 HTML、Mask、Reference Evidence、模型调用或正式分数。完成后停止，不对两个几何继续调参，不启动 M3。

## 实际 CPU 回归

本轮 386/386 项通过，新增13项；其中空间专用32项通过。完整回归时禁止真实网络连接和子进程启动；0失败、0错误、0跳过。测试日志与口径记录在 spatial_diagnostics.json → tests。所有真实VLM/Blender/GPU测试本轮未运行。

公开复现检查：只使用 Git 中已公开的 RGB、二值 Mask 和 JSON，在临时目录免费离线回放，连续测量及旧 VLM 判断完全相同；不依赖未公开的 NPY，不调用模型或渲染器。仅发布自制 PNG、必要代码/测试/索引及这三个结果文件；未发现凭据或敏感绝对路径。
