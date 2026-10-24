# bw_0073：冻结 Reference ROI 与真实 Agent Render 离线诊断

本轮完成1个真实配对、37个固定评价范围的 Appearance / Perceptual 测量。Region 可以把差异组织到水槽、岛台、后方料理区和右侧柜体等功能范围；本轮**没有证明 Polygon 或语义 Region 的数值评价优于 Box / 普通空间 ROI**。这不是正式 Benchmark 成绩。所有候选及测量保持 `reviewed:false`、`q=0`、`provisional_debug`，没有生成 Observation 总分。

[完整对照页面](comparison.html) · [失败案例](failure_cases.html) · [自动初审记录](initial_review.json) · [全部数值](metrics.csv) · [配对/相机审计](pair_audit.json) · [检查结果](validation.json)

## 1. 真实数据及可比性

- Task：`bw_0073`；Agent：`codex 0.147.0 / gpt-6-sol (openai)`。
- Run：`bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg`。
- 原始 Reference RGB：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/data/hf-snapshot/bw_0073/tests/dataset/tasks/bw_0073/references/image_01.jpg`。
- 真实 Agent Render：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/bw_0073-codex-fixed-camera-v1-rgb-only-key2-generation/bw_0073/task__bA358eg/artifacts/workspace/exports/final.png`。
- 从既有 Direct Grounding 的 provenance、Inventory、Run task 配置、Agent 输入清单和 artifacts manifest 确认对应关系。原始 RGB、当时 Agent 输入 RGB 与 ROI 来源 RGB 的文件内容完全相同；采用直接字节比较，没有哈希校验。没有用其他 Run 或合成图片替代。
- Reference 原始分辨率7952×4333；Render 为1672×941 RGBA，Alpha全部255。Reference 工作网格沿用历史1536×837。坐标为左上原点、x向右、y向下；原归一化0–1000 Box/Polygon及8个原始分辨率 Mask 原样保存于 `frozen_reference/`。本轮直接复用这些 Mask，不重新解释或修改顶点。
- 渲染相机依据同一导出目录的 `camera_parameters.json`：焦距22.5 mm，K中fx=fy=1045、主点(836,470.5)，camera-to-world位置(0,-6,1.5)。当前 Project e 固定T0位置是(0,-6,2.0)，所以标记 `historical_camera`。不凭Run名里的 fixed-camera 宣称合规。
- Reference 相机未知；没有打开 `.blend` 验证PNG与相机导出的同步性，故 `render_blend_sync=unknown`。视角/FOV、构图、几何、光照和材质可能同时影响图像差异。不能把数字当作纯材质误差或独立空间误差。

## 2. 冻结范围与图像处理

Reference Region 先冻结，再读取 Render 进行尺寸适配。Render 做一次内容无关的等比全图缩放至1487×837，放入1536×837网格，左留24、右留25像素。没有裁剪、搜索配准、拉伸到匹配物体、重检测、移动或优化ROI。缩放仅有整数舍入误差。

Reference 与 Render 使用**同一张冻结Mask的同一像素坐标**。数值支持域为 `frozen_ROI & render_valid`；留边和透明像素代表不可观测，不能按灰色场景或零误差计入。全图有效比例96.81%，各ROI有效比例随结果报告。这是有效数据筛选，不是根据Render内容重新生成ROI。部分边缘ROI有约4–7%像素无法比较，保留为缺失而非补全。

37个范围包括：Global 1、默认Dense Patch 2×2共4、普通网格4×4共16、Direct Box 4、Direct Polygon 4、总面积相近矩形4、有效面积相近矩形4。最后两组只是对照，不代替冻结ROI。

普通矩形由Polygon的面积、外接框中心和长宽比确定，不使用图像误差或语义类别。发现左右留边会令“总面积相近”与“实际观测面积相近”不同后，保留原33条测量，另增加4个有效面积对照；最终面积偏差不超过0.21%。该更正详见 `control_adjustment.json`。位置仍来自Polygon几何，不能冒充独立的语义盲测；独立空间基线是固定网格。Box本身就是普通矩形，其面积对照与自身完全相同，没有重复推理冒充另一种方法。

`frozen_rois.json` 记录最初33个范围；补充4个范围单列在 `observed_area_controls.json`。两份合起来是最终37个范围。`initial_33_scope_metrics.json` 保留补充前的全部实际测量，未改写它们的数值。

## 3. 指标及实际结果

直接调用未修改的 `benchmark_metrics.py` 中 `numerical_errors` 的Appearance和 `perceptual_error`，不调用正式聚合器，不临时将候选标为reviewed。

- Appearance：有效Mask内RGB三通道归一化绝对差均值，[0,1]。这是可复核的图像颜色差，受几何错位、曝光/色调等因素影响，不等同于材质识别。
- Perceptual：已有本地DINOv2，CPU、224输入、尺度1和0.5，原有 `(1-cos)/2` 再平均。使用现有局部裁剪和Mask外黑色填充，保持原有公式。它是特征距离代理，不是语义类别正确概率。
- Semantic：N/A。没有经过审核的语义证据/验证器，本轮没有新VLM。
- Spatial：N/A。没有可靠的Render对应证据和已确认相机对齐；不把现有边缘代理冒充空间正确性。
- Statistical：N/A。缺少经过审核、适用于本次区域的占据/元素分布证据；没有因为内部helper能算边缘代理就将其报告为可信元素分布分数。
- Structural与正式Observation Energy：未运行 / N/A。

以下都是该真实配对的条件图像距离，数值越小仅表示该范围内更相近，不能据此比较ROI算法的准确率。不同范围的大小、上下文与有效像素不同。

| 范围 | Appearance | Perceptual | Render有效像素占ROI |
| --- | ---: | ---: | ---: |
| Global | 0.21227 | 0.22794 | 96.81% |
| Dense 2×2 [0,0] | 0.17995 | 0.17180 | 96.88% |
| Dense 2×2 [0,1] | 0.18520 | 0.15088 | 96.74% |
| Dense 2×2 [1,0] | 0.26011 | 0.17385 | 96.88% |
| Dense 2×2 [1,1] | 0.22365 | 0.20524 | 96.74% |
| Box R1 | 0.24235 | 0.24919 | 95.54% |
| Box R2 | 0.23625 | 0.18630 | 100% |
| Box R3 | 0.31155 | 0.25930 | 100% |
| Box R4 | 0.22196 | 0.18731 | 94.34% |
| Polygon R1 | 0.29754 | 0.20964 | 93.13% |
| Polygon R2 | 0.27087 | 0.15656 | 100% |
| Polygon R3 | 0.31898 | 0.27629 | 100% |
| Polygon R4 | 0.24840 | 0.20051 | 93.00% |

## 4. 普通ROI对照

| Region | Polygon App / Perc | 普通有效面积矩形 App / Perc | 对照/Polygon有效面积 |
| --- | ---: | ---: | ---: |
| R1 | 0.29754 / 0.20964 | 0.28650 / 0.26157 | 0.99882 |
| R2 | 0.27087 / 0.15656 | 0.26351 / 0.17117 | 1.00008 |
| R3 | 0.31898 / 0.27629 | 0.32180 / 0.26632 | 1.00206 |
| R4 | 0.24840 / 0.20051 | 0.24388 / 0.17492 | 0.99918 |

Polygon与相近有效面积的普通矩形响应接近，方向并不一致。R3 Polygon的Appearance为0.31898，普通矩形为0.32180；不能将局部归一化后高于Global的响应归功于语义分区。

4×4普通网格也能指出差异：左下 `[3,0]` Appearance 0.36515，右侧 `[2,3]` 为0.30841；默认Dense 2×2左下为0.26011。它们能发现位置异常，但会按网格切开完整功能区域。Region增加的是以可解释功能组组织问题的能力；Region名称并未输入RGB/DINO数值计算，所以没有证实额外的语义数值收益。

网格上方多个格子的Perceptual较高，但Appearance较低，提示两者关注不同的纹理/结构及上下文特征；不把两类指标当成同一种误差，也不将不同范围的DINO距离当作可直接相加的量。

## 5. 每个Region的可见差异与失败

以下均为自动静态初审，**不是人工审核通过**；没有Pixel GT，不报告分割准确率或真实物体遗漏率。逐项图示在 `comparison.html` 和 `details/`。

- **R1 窗边水槽区**：拱窗与矩形窗、搁板和台面颜色/纹理的差异清晰。Polygon更集中于左侧内容，但其Appearance高于Box仅表示样本像素不同，不证明它更准。相机/曝光等因素混杂。
- **R2 中央岛台区**：岛台、椅子、吊灯的尺寸和位置不同。关键限制是Render吊灯下移，Reference Polygon的上部独立范围不会跟着移动，漏掉了实际吊灯的一部分。按固定坐标可测原位置差异，但不能完整评价移出范围的物体。Box保留更宽上下文。Polygon Perceptual 0.15656低于Box 0.18630，不能解释为它更完整。
- **R3 后方料理区**：后墙/台面纹理、柜体以及摆件相关图像差异集中，Polygon Appearance 0.31898，而Global 0.21227，说明局部差异会被全局均值稀释。这里并不推断某个类别真的缺失。Box全部落在R2 Box内，重复覆盖尤其严重。
- **R4 右侧高柜区**：柜体比例、高度、颜色和位置存在可见差异。Render中柜体较低，Reference ROI的上部在Render中包含更多天花板；保持原样，不根据重建结果调边界。这也是固定ROI受到视角和布局影响的案例。

DINO对非矩形ROI的上下文存在限制：R2 Polygon在外接裁剪框内的有效占比约55%，R1约65%，其余是现有流程的黑色填充。填充、尺度和上下文都可能影响距离；本轮没有消融实验，不能认定填充是距离变化的唯一原因。也不能以“Polygon距离更低”宣布ROI定位更好。

## 6. 重叠、未分配范围与聚合

Box重叠占全工作网格7.56%，Polygon为1.36%；未分配分别15.32%和40.05%。它们只是几何诊断，不是优劣分数。R3 Box的82800个像素全部属于R2 Box；Polygon的R2/R3仍共享16792像素。

`overlaps.json` 保存全部成对重叠及每个Region的独有/共享Appearance。例如R2 Box独有部分0.21543、共享部分0.28793；R3 Polygon独有部分0.33246、共享部分0.27765。这些支持解释误差来自哪里，**没有把各Region条件损失相加**。DINO不具有像素可加性，不能用同样方式拆出加性总分。正式Observation Energy始终为null。

未分配背景仍由Global和Dense Patch观察。保留四个功能区不是删除其他困难区域；普通网格发现的地板/柜体差异也原样展示。

## 7. 本轮结论

1. **能否定位真实局部差异？** 能，四个功能区均显示清楚的Reference/Render图像差异，R3等局部均值高于Global；相机未确认对齐，不能作纯外观/几何归因。
2. **比Global/Dense多了什么？** 给出按完整功能范围组织的可读诊断，减少人工在网格之间拼接问题。普通空间ROI同样能产生高局部响应，尚无证据说明语义ROI数值上优越。
3. **Polygon比Box更有利吗？** 有减少不相关上下文及R2/R3混合的组织优势，但重要物体移出范围、DINO填充和有效面积等因素仍在；不支持统一替代Box或宣称更准确。
4. **比普通ROI的额外收益？** 本例可解释性更强；控制面积后数值方向混合，未证明独立收益。需要人工确认目标误差和更多真实配对，才能判断排序/检出优势。本轮不扩展。
5. **哪些指标可信？** RGB差异计算和同坐标/缺失处理通过检查；DINO计算有效、自比较为零，但区域质量意义仍是代理。Semantic、Spatial、Statistical及正式成绩缺证据，均N/A。

## 8. 实际执行与检查

- 145项轻量CPU单元测试通过（包含7项本次新增测试）；详细日志 `tests_final.log`。检查全图适配/留边、有效面积对照、不改冻结ROI、RGB条件误差，以及原正式比较器仍拒绝未经审核Region。
- 本地DINO CPU实际测量37个范围，初始33个范围耗时32.922秒，补充4个对照12.783秒，测量阶段共约45.705秒（不含浏览、准备和单测）；两次模型加载，均离线、2个CPU线程。
- 实际Reference自比较：Global、Box R2、Polygon R2的Appearance和DINO Perceptual均为0。没有合成扰动替代真实Render。
- GPU、付费VLM、SAM、SLIC、Blender、Agent调用均为0；未运行正式评分、排行榜或3D检查。
- 未修改五类公式、权重或Runtime状态；`source_snapshot/` 保存3个核心模块以及本次脚本/测试。本轮仅新增 `scripts/region_real_render.py`、`tests/test_real_render.py` 及本结果目录，没有Git提交。
- 后续无需重新推理即可浏览全部图片和CSV。检查细节见 `validation.json`。若缺少本地DINO则明确Perceptual N/A，不替代特征。

## 9. 免费离线复现

从仓库目录执行以下单个CPU流程。目标目录必须不存在，避免覆盖；如重现多次请更换 `out`。环境复用本机已有Python和DINO，不下载依赖/模型，不访问API。重新测量可能有少量数值舍入及耗时差异。

```bash
cd /home/xymo/projects/e-harness
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /home/xymo/environments/relateanything-inference/bin/python - <<'PY'
from pathlib import Path
import unittest
from scripts.region_real_render import prepare, evaluate
from scripts.region_grounding_experiment import save
suite = unittest.defaultTestLoader.discover('tests', pattern='test_real_render.py')
assert unittest.TextTestRunner().run(suite).wasSuccessful()
out = Path('results/region_first_real_render_bw0073_replay').resolve()
prepare(out)
save(out/'offline_checks.json', {'passed': True, 'test_module': 'test_real_render'})
evaluate(out)
PY
```

复现脚本会生成测量JSON/CSV和对照图；本次静态视觉诊断、失败案例和文字报告是对现有图像的独立解读，不作为算法自动质量标签。

本轮已完成并停止，等待人工审核冻结ROI的实际适用性，不会自动开始正式重建评分。
