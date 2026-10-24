# 五场景 Reference Region Extraction 对照

本轮仅生成参考 RGB 的候选。没有运行 Agent、Blender、VLM 或重建评分，也没有更改正式 Evidence Extraction、Runtime blocked 状态、五类能量或权重。

## 来源与坐标

Inventory → run config.task.path → input.json.task_id/files → dataset task.json.reference_images 已逐图核对；路径见 [manifest.json](manifest.json)。仅从原始 RGB 制定提示，没有读取 Agent Render。

| 任务 | 原始尺寸 | 工作尺寸 | 固定测试候选框 | 文本概念 |
|---|---|---|---:|---:|
| bw_9064 | [1672, 941] | [1536, 864] | 10 | 7 |
| bw_0074 | [1258, 855] | [1258, 855] | 10 | 8 |
| bw_0073 | [7952, 4333] | [1536, 837] | 12 | 8 |
| bw_0043 | [1024, 617] | [1024, 617] | 3 | 4 |
| bw_0075 | [2250, 1500] | [1536, 1024] | 4 | 3 |

SLIC 与模型输入都采用同一张最长边≤1536的工作 RGB。二值 Mask 最近邻恢复到原始网格，bbox 是恢复后 Mask 的原始像素 xyxy；这不恢复降采样丢失的细节。统计采用明确记录的工作网格，Overlay 也采用工作尺寸。

## 实测候选统计

下表的 Unknown 是原始 Mask 并集之外的残余，不是语义正确率。补入 Unknown 后基础覆盖为100%；所有候选未审核，因此审核语义覆盖始终0%、审核语义 Unknown 始终100%。SLIC 100%仅表示视觉网格覆盖。Regions计数包含一个非空残余Unknown；完整逐Mask信息保存在 candidates.json / mask_metadata.json。

| 任务 | 方法 | Mask/视觉块 | 原始覆盖 | 残余Unknown | 重叠像素 | 重复对 | Anchors |
|---|---|---:|---:|---:|---:|---:|---:|
| bw_9064 | slic_200 | 201 | 100.00% | 0.00% | 0.00% | 0 | 0 |
| bw_9064 | sam2_auto | 8 | 34.29% | 65.71% | 20.45% | 2 | 0 |
| bw_9064 | sam2_prompted | 10 | 95.04% | 4.96% | 0.01% | 0 | 5 |
| bw_9064 | sam3_text | 10 | 95.34% | 4.66% | 0.00% | 0 | 5 |
| bw_9064 | sam3_visual | 10 | 96.03% | 3.97% | 0.02% | 0 | 5 |
| bw_0074 | slic_200 | 136 | 100.00% | 0.00% | 0.00% | 0 | 0 |
| bw_0074 | sam2_auto | 27 | 24.26% | 75.74% | 1.25% | 0 | 0 |
| bw_0074 | sam2_prompted | 10 | 77.80% | 22.20% | 10.18% | 0 | 5 |
| bw_0074 | sam3_text | 15 | 49.39% | 50.61% | 16.15% | 0 | 5 |
| bw_0074 | sam3_visual | 10 | 72.90% | 27.10% | 6.29% | 0 | 5 |
| bw_0073 | slic_200 | 144 | 100.00% | 0.00% | 0.00% | 0 | 0 |
| bw_0073 | sam2_auto | 18 | 21.67% | 78.33% | 14.69% | 1 | 0 |
| bw_0073 | sam2_prompted | 12 | 47.19% | 52.81% | 0.00% | 0 | 7 |
| bw_0073 | sam3_text | 45 | 60.21% | 39.79% | 24.65% | 0 | 9 |
| bw_0073 | sam3_visual | 12 | 42.99% | 57.01% | 0.01% | 0 | 7 |
| bw_0043 | slic_200 | 174 | 100.00% | 0.00% | 0.00% | 0 | 0 |
| bw_0043 | sam2_auto | 3 | 25.84% | 74.16% | 0.00% | 0 | 0 |
| bw_0043 | sam2_prompted | 3 | 48.84% | 51.16% | 0.00% | 0 | 1 |
| bw_0043 | sam3_text | 7 | 25.02% | 74.98% | 22.23% | 0 | 1 |
| bw_0043 | sam3_visual | 3 | 47.12% | 52.88% | 0.00% | 0 | 1 |
| bw_0075 | slic_200 | 195 | 100.00% | 0.00% | 0.00% | 0 | 0 |
| bw_0075 | sam2_auto | 3 | 0.44% | 99.56% | 0.00% | 0 | 0 |
| bw_0075 | sam2_prompted | 4 | 76.26% | 23.74% | 1.76% | 0 | 0 |
| bw_0075 | sam3_text | 4 | 42.80% | 57.20% | 27.99% | 0 | 0 |
| bw_0075 | sam3_visual | 4 | 66.22% | 33.78% | 0.00% | 0 | 0 |

重复对阈值为候选间IoU≥0.9，包含关系单独记录，部分重叠也单独记录。它们是候选结构诊断，不是针对GT的IoU，也不能直接视为分割错误或空间冲突。没有人工审核Mask，accuracy IoU、Boundary F1均为N/A。

## 公平性、时间与资源

- SLIC不使用人工提示。SAM2 Auto采用固定16×16自动正点网格，单层无裁剪、每批8点，pred-IoU阈值0.88、稳定性阈值0.95、官方NMS阈值0.7；所有图相同。原始网格保留在run.json。官方流水线NMS后单个Mask与原始点的对应没有返回，明确记unknown，不反推。
- SAM2 Prompted与SAM3 Visual使用逐项相同的原图候选bbox，均由助手静态查看RGB拟定为固定测试松框，未经人工确认，不是人工GT。SAM3 Visual使用官方predict_inst单实例分支，multimask_output=False；不使用概念搜索框接口冒充实例提示。
- SAM3 Text是另一组由助手从RGB拟定的固定概念提示，保存每图完整词表、每词耗时、实例数、原始分数及框。保留跨概念重复，不以模型分数当可靠性；置信阈值0.5只用于官方候选过滤。不能与无需人工提示的方法直接排优劣。
- 两模型原始参考工作图及bbox相同，但内部编码分辨率不同（SAM2为1024×1024，SAM3为1008×1008）；SAM2使用FP32，SAM3采用官方支持的BF16 autocast。这些设置均保留，未进行数值精度或阈值搜索。
- SLIC+SAM2与SLIC+SAM3均以同一SLIC-200网格为基础，分别保留对应统一框提示的原始SAM Mask。联系记录像素支持比例，可以多对多；不切碎全部超像素、不强制唯一语义归属、不自动合并或覆盖Unknown。上层Mask/Anchor未变化，因此组合没有新增模型准确性证据。
- GPU只使用复查空闲的单张A100 40GB（UUID见资源JSON），SAM2与SAM3严格串行；CPU线程2。SAM2显存硬预算20%、SAM3硬预算40%，这是资源上限而非SAM3需求估计。实际分配/保留峰值逐项保存。

| 方法 | 已完成图数 | 平均实际调用秒 | 最大已分配MiB | 最大保留MiB |
|---|---:|---:|---:|---:|
| slic_100 | 5 | 1.046 | N/A | N/A |
| slic_200 | 5 | 1.089 | N/A | N/A |
| slic_400 | 5 | 1.123 | N/A | N/A |
| sam2_auto | 5 | 0.704 | 565.5 | 892.0 |
| sam2_prompted | 5 | 0.349 | 776.3 | 1032.0 |
| sam3_text | 5 | 2.034 | 4109.3 | 4678.0 |
| sam3_visual | 5 | 0.616 | 4126.9 | 4732.0 |
| slic_sam2 | 5 | 0.028 | N/A | N/A |
| slic_sam3 | 5 | 0.029 | N/A | N/A |

时间口径：SLIC是算法调用；SAM2 Auto共用已加载模型，wall不含一次模型加载；SAM2 Prompted复用已有适配器，wall含本次适配器加载、预处理和推理，另存纯forward时间。SAM3 Text含图像编码与该图全部概念查询；SAM3 Visual实际wall仅含复用编码后的实例分支调用，shared_encoding_seconds及full_image_compute_seconds给出编码成本。组合wall仅含CPU支持联系构建，另记继承源耗时。不能把这些不同口径的wall当作公平的模型速度排名。

## 不可用项与环境

- sam3_auto: Official image API exposes text/concept and interactive prompts; no supported no-prompt AutomaticMaskGenerator found in this checkout. Not emulated with text prompts.

SAM3权重唯一下载源为[ModelScope facebook/sam3](https://www.modelscope.cn/models/facebook/sam3)，仅sam3.pt和必要配置，未重复下载model.safetensors。代理绕过与DNS映射只作用于下载进程，未修改系统配置。下载记录见sam3_download.json。使用[官方SAM3源码](https://github.com/facebookresearch/sam3)，本地checkpoint、显式load_from_HF=False，BPE来自官方代码资源。没有申请模型权限、Hugging Face模型下载或自建哈希校验。

额外依赖经用户授权装在独立/tmp环境，复用现有PyTorch；环境路径与安装日志保留。官方源码的包元数据NumPy上限与现有Python3.13环境可能不一致，没有为满足元数据降级共享NumPy/PyTorch；这里只验证实际源码导入、checkpoint加载与本轮图像推理，不声称完整训练/视频依赖兼容。

## 逐图静态观察（均不是人工GT审核）

### bw_9064

- SAM2 Auto finds ceiling/side-wall candidates but misses the large back wall, table and whole-chair masks at this fixed budget. The refrigerator is represented by parts and duplicate wall masks exist.
- Prompted candidates need contact-boundary review at the table/plant and chair legs; coverage is not semantic validation.
- SAM3 Text returns 1 table, 2 chairs, 1 refrigerator, 1 potted plant, 3 walls, 1 ceiling and 1 wood-floor candidate. This is useful reference-side discovery with seven concept prompts, not no-prompt automation or verified recall.

### bw_0074

- SAM2 Auto produces several shelf-level record/book groups and individual display objects; it does not recover the whole bookcase or transparent chair as a complete instance.
- Prompted books/records/bookcase masks mix hierarchy levels and sometimes include cabinet structure, other objects or many holes. Transparent chair and sofa boundaries need review.
- SAM3 Text returns books=8 but vinyl records=0 at confidence threshold 0.5. Bookshelf=2 appears to recover much of the cabinet structure while leaving contents as holes; shelf structure and book/record collections require different upper-layer Regions.

### bw_0073

- SAM2 Auto misses the four foreground stools at this grid/threshold budget. Unified loose boxes produce four separate stool candidates, retaining leg gaps and some disconnected fragments.
- Ceiling and floor masks contain many holes/fragments around lights, shadows and stool occlusion; thin structures are resolution-limited by the 7952x4333 to 1536x837 working resize.
- SAM3 Text returns chair=0, cabinets=26, countertop=3, plant=4, bowl=4 and window=6. The cabinet concept mixes object/door/drawer granularities; these counts are not true object counts. The four foreground chairs are omitted by this fixed text prompt, whereas the same loose boxes yield four separate SAM3 Visual masks. No prompt-word or threshold tuning was performed after this failure.

### bw_0043

- SAM2 Auto and Prompted both return a visually complete flower silhouette. This supports whole-flower candidate utility, not petal-instance completeness or boundary accuracy.
- Leaves/background prompts yield disconnected fragments; narrow leaves and hidden portions remain uncertain.
- SAM3 Text returns flower=1 and petals=6, but leaves=0 and stem=0. Whole-flower/petal overlap is legitimate hierarchy, not automatically a conflict. The text run does not demonstrate recovery of surrounding narrow leaves.

### bw_0075

- This reference is a textured painted landscape, not a photograph of discrete furniture objects. No physical-object Anchor was forced into the prompt list.
- SLIC breaks broad painted sky/cloud/hill bands into many visual patches. SAM2 Auto finds only tiny local shapes; Prompted follows some large bands but leaves brushstroke holes and fragments.
- SAM3 Text returns painted sky=1, clouds=3, painted hills=0. Sky/cloud candidates overlap substantially (27.99% of working pixels); the depicted-content concepts do not provide a reliable exclusive partition. The visual boxes recover several broad bands but leave holes and unassigned brushwork.

## 结论与适用范围

1. 大面积Region：优先查看带明确区域意图的SAM提示结果；SLIC适合作为稳定全图覆盖基础，几百块切分不是最终语义Region。书柜或绘画带状纹理应保留集合Region候选，完整程度需要人工审核。
2. 重要Anchor：统一框提示提供可逐实例对比的条件；SAM2/SAM3实例Mask均需审核接触边界、透明椅、细腿、花瓣与枝叶。没有人工边界GT，不能宣布总体最优。
3. SAM3重复实例：以每词实际实例数和逐图观察为依据；一次chair查询得到多个候选是额外发现能力，不等于召回率提升，重复/误检也必须保留。与SAM2人工逐椅框比较时必须计入提示差异。
4. 过/欠分割：SLIC在连续表面与复杂笔触上明显切碎；SAM候选可能把物体集合与柜体混合，也可能只提取局部、漏掉椅子或大片背景。连通分量多也可能来自真实遮挡，不能自动记错。
5. 组合价值：用于保存覆盖与候选层级值得保留；本实验的简单联系不会改善原Mask边界，也没有证明分割准确率更高。不做不受审核的语义合并。
6. 可自动化：密集视觉网格、模型候选、来源/坐标保存、覆盖/重叠/重复统计、预览与清单检查。仍需人工：语义类别、重要性、组/实例粒度、完整性、边界与冲突裁决。
7. 层级：Global原图 → Dense SLIC多粒度底层 → 可重叠Coarse Regions/集合 → 独立Anchor实例；以支持联系而非唯一父节点表达。残余及不能可靠解释的内容保留Unknown；所有reviewed=false、mask_reviewed=false、reliability=0。

## 复现

从项目根目录运行，每轮选择不存在的新目录。以下路径需要当前临时环境仍存在；清理/tmp后需按已授权隔离方案重建。

```bash
export REGION_OUT=results/multiscene_region_extraction_new
export PYTHONPATH=/tmp/project_e_slic_deps_rlhjhcvv
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase prepare
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase slic
# 必须先复查空闲GPU；下列UUID不是GPU预约。只允许顺序执行。
export CUDA_VISIBLE_DEVICES=GPU-158426a4-6684-7863-8cbe-ed6595f97683
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
timeout 600 /home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase sam2
cp results/multiscene_region_extraction/sam3_environment.json "$REGION_OUT"/
timeout 600 /tmp/project_e_sam3_env_yhqvf4jo/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase sam3
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase combine
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase diagnostics
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase report
/home/xymo/environments/relateanything-inference/bin/python -B scripts/compare_multiscene_regions.py --output "$REGION_OUT" --phase validate
```

本轮已执行15次SLIC、五图SAM2 Auto与五图SAM2 Prompted；SAM3完成情况见上表及sam3.log。静态检查结果见[validation.json](validation.json)。未计算未经审核的准确率或五能量/重建分数。

## 本轮实际检查结果

- 通过：4项受控统计语义检查；40份候选文档；238张原图尺寸二值Mask及唯一ID、bbox、未审核状态；78条层级Mask联系；269个HTML本地链接；现有Evidence加载器的真实候选读取。
- 通过：五个staged参考图与数据集原文件直接字节比较完全相同，未计算哈希，见[reference_source_checks.json](reference_source_checks.json)。
- 完成：15组SLIC、5组SAM2 Auto、5组SAM2 Prompted、5组SAM3 Text、5组SAM3 Visual及10组CPU组合，共45组可用方法×图像记录；SAM3 Auto共5组明确N/A。
- 未执行：无人工GT的IoU/Boundary F1、五类能量评分、重建Benchmark、Agent和Blender。
- GPU已释放：进程退出后显存3 MiB、利用率0%、无计算进程，见[post_exit_resources.json](post_exit_resources.json)。
- SAM3源码推理通过；独立环境实际NumPy 2.5.2、ftfy 6.3.1与官方包元数据声明不完全一致，未改共享依赖。完整实测环境见[sam3_compatibility.json](sam3_compatibility.json)。

提示来源澄清：provided_prompt_count记录外部提供的固定测试提示数量，human_reviewed_prompt_count为0。这些框/词由本次助手静态查看Reference RGB拟定，bw_9064物体框复用此前未审核草稿；不代表无外部提示、真实人工GT或人工耗时测量。自动网格点另记prompt_count=256、provided_prompt_count=0。
