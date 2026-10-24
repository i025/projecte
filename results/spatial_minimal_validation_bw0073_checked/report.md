# Spatial Energy 最小有效性验证：bw_0073 R2

本轮验证二维投影度量，不产生正式 Spatial Energy。0 次 API 请求、0 次 GPU/模型/Blender运行。所有真实图像候选 reviewed:false、reliability:0。

## 结果

- 受控 Oracle 几何：8/8 对照通过；新增19项CPU测试及现有Benchmark/Missing Evidence回归合计94项通过（1.999秒），见tests.txt（exit=0）。
- 主自动定位路径：Reference 仅有吊灯、台面候选，没有完整岛台；Render 无可复用的对象定位结果。两侧自动 Δx、Δy、面积比均 N/A，不能称为已打通自动 Spatial Energy。
- 人工式草拟粗框经正常审核门控也全部 N/A。显式 allow_provisional 的有条件 debug 测量另列，不能冒充自动检测、人工 GT 或 Energy。
- 条件粗框：Reference Δx=-0.003255、Δy=-0.400239；Render Δx=0.000326、Δy=-0.287336。
- Render−Reference：Δx变化=0.003581、Δy变化=0.112903。y向下为正；条件下吊灯与岛台 bbox 中心的竖向距离变小。水平变化很小且草拟范围含零，不能认定水平错位。
- BBox面积比代理：0.319712 → 0.218188，点估计变化 -0.101524，但草拟边界下的变化范围也跨零，不能稳健认定面积代理减小。不是物体可见投影面积比；柜体遮挡、粗框内的椅子/空洞和边界定义都会影响它。真实可见 Mask 面积比两侧均 N/A。
- 草拟边界极值传播的 Δy变化范围=[0.07646356033452806, 0.1445639187574671]；Δx变化范围=[-0.014973958333333204, 0.024088541666666574]；BBox面积比变化范围=[-0.24995329873378655, 0.05960108978529602]。这些只是在给定草拟边界下的敏感性，不是置信区间，也不覆盖模型或相机系统误差。

## 来源与冻结

原始图像、Run、相机和既有全图适配见 pair_provenance.json。1536×837公共网格，左上原点、x右/y下；bbox为连续像素边界xyxy，中心分别除以W/H。复用历史 Render 等比全图适配1487×837、左侧24像素留边；没有裁剪、内容对齐、搜索或变形。真实原图7952×4333、Render1672×941。

Reference既有冻结证据只读经load_document读取；其中Region和关系scope框没有用作物体框。Reference候选由只获Reference访问的独立检查者草拟并冻结，再由只获Render访问的独立检查者提供Render候选；两者未交换坐标。主代理此前知道Render内容，故本轮不是严格盲测。草拟框不是自动定位成功，也没有升级审核状态。

R2 ROI保持原文件像素不变。紫色线表示固定ROI，蓝色框表示岛台可见台面+可见柜体、排除椅子与摆件的粗外包范围，橙色框表示吊灯含顶座/悬挂线/灯体。框内仍会包含遮挡物和背景。Render吊灯部分位于固定R2之外，但全图可见；不能据此判断Missing。完整岛台的近侧底沿被椅子遮挡，两侧粗框的确定性有限。

## 现有缓存与面积限制

只读复用6份Reference SAM缓存，见cached_reference_candidates.json及cached_reference_masks.png。三份吊灯框主要一致，但细链漏分、环带孔洞被填充等问题未审核。其余三份仅是台面，不是完整岛台。候选Mask像素数仅为文件统计，不是真实可见面积。没有可靠的两对象、两侧可见Mask，未混用Mask面积与BBox面积，也没有从Region Mask推造物体。

## 度量有效性与重复处罚

复用area_mask、reliability、load_document；现有match_anchors提供匹配/缺失状态，compare提供单物体中心偏移和定性关系，但没有本轮连续相对偏移或面积比。只增加spatial_diagnostics.py的两个诊断函数及CPU实验/测试，没有改benchmark_metrics.py、benchmark_evidence.py、benchmark_config.py或正式聚合。

相对偏移为pendant−island，比较为Render−Reference；中心是BBox中心，非Mask质心。BBox面积按连续宽×高计算，Mask面积按[0,1]权重和计算，两种量分开存储，比例不截断为[0,1]。Unknown、不可定位、语义不匹配、Confirmed Missing不产生最大Spatial惩罚；输入视角不可见、scene-only和冲突对象不可计算。允许Misplaced但仍可见的匹配对象，不要求两个对象仍在原ROI内。

Oracle包含不变、灯水平移动20px、灯竖移12px、灯面积4倍、共同平移、Unknown/Confirmed Missing/类别不匹配三类N/A；另检验水平移动0/5/10/20/40px的响应。已知灯Mask有空洞，证明Mask比和BBox比不同。正/负对照只检验数学，不证明真实定位有效。没有把连续有符号量塞入[0,1]Energy，也没有将同一缺失重复计分。

## 失败、Uncertain与正式评分缺口

主要瓶颈是完整岛台与吊灯的可靠对象定位、可见范围定义及两图对应，而不是本轮坐标算术。当前缺少独立审核的两侧对象框、可见Mask及一致语义对应；真实灯具几何形态也不完全相同，bbox中心受外形变化影响。Reference相机未知，历史Render相机高度1.5m，正式协议2m，未重新验证blend/PNG同步。即使粗框差值稳定，也不能把它认定为真实三维位置/尺寸错误。相对度量抵消共同平移，但不消除视角、透视、缩放和遮挡影响。此前“吊灯位于岛台上方”的yes/yes只能判断方向，不能排除间距变化。

SAM/检测器只产生可审候选，不是缺失验证器；本轮不运行新模型。自动定位缺失和未审核是明确失败/阻塞项，不以草拟框替代。本轮未产生正式Energy，无综合分数。

## 复现

在项目根目录执行（只使用已保存图像/候选及CPU）：

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /home/xymo/environments/relateanything-inference/bin/python -B scripts/spatial_minimal_validation.py --inputs results/spatial_minimal_validation_bw0073_checked --output results/spatial_minimal_validation_bw0073_replay
```

输出目录必须全新；离线重放使用冻结的草拟候选，不会重新“自动提取”对象。comparison.html可直接打开；tests.txt、validation_checks.json列出实际检查。API/SAM/SLIC/DINO/GPU/Blender全部未执行；自动定位端到端准确性、人工GT和正式Spatial评分未验证。

## 执行记录

首次输出目录 `results/spatial_minimal_validation_bw0073/` 保留了测试运行器的导入失败：该目录不是可导入的 tests 包，3个模块未加载，不能算作测试通过。改为 unittest discovery 后在当前新目录重跑，94项全部通过；8个Oracle对照两次均通过。旧输出未覆盖。
