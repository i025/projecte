# SLIC Region Merging + VLM Semantic Grouping 实验

视觉合并、两分支多粒度层级、已有 SAM Anchor 保留与可视化已完成。真实 VLM 连接成功，但返回结构不符合契约，规划与语义分组均不可用；本轮不能认定端到端语义构建成功。

## 输入与方法

仅使用 bw_9064、bw_0074 的已核实原始 Reference RGB。manifest.json 记录任务元数据和路径对应；重新直接比较原始与 staged 文件字节相同，不计算哈希。没有读取 Agent Render，没有运行 Blender、Agent 或 SAM2/SAM3。

Fine 复用已有 SLIC-200：工作网格分别为 1536×864、1258×855；所有交付 Label/Mask 以最近邻映射至原始 1672×941、1258×855 网格。底层历史 Label Map 未修改。

RAG 仅连接共享水平/垂直边界的块。Lab 均色距离除以100；灰度 Sobel /4 梯度描述边界；DINO 使用现有 local_dino_extractor 从遮掉块外内容的 bbox crop 提取 CLS（批8），不是重新训练的分割器。

Light 成本=0.65 Color + 0.35 Boundary；Feature 成本=0.45 Color + 0.25 Feature + 0.30 Boundary，Feature 为 cosine distance/2。Medium/Coarse 阈值固定0.075/0.14；合并后按面积重算颜色与特征。保留原始共享边界均值的最大值（上限0.22），并限制原始块均色到新簇均色的最大半径 min(0.34,2.5×threshold)，避免简单传递合并。没有固定目标块数或后验阈值调优。

已有未审核 SAM3 Visual Anchor Mask 仅作为候选边界保护：原始块占据率≥0.65 与≤0.35 的两类不允许进入同一簇。模糊块仍可合并，该保护不能证明真实物体边界正确。未使用模型分数作为可靠性。

## 实测合并结果

|图片|方法|Fine|Medium|Coarse|Coarse 相对 Fine 新增混合像素代理|
|---|---|---:|---:|---:|---:|
|bw_9064|light|201|37|21|0|
|bw_9064|feature|201|54|24|0|
|bw_0074|light|136|98|70|1097|
|bw_0074|feature|136|114|85|0|

所有 Fine/Medium/Coarse 分区覆盖率100%，层内不重叠；跨层有意重叠，使用像素并集统计，不能把覆盖率相加。语义候选并集0%、语义 Unknown 100%、已审核语义覆盖0%。CSV 混合像素在工作网格计算（9064:1536×864，0074:1258×855），coverage_grid 仅说明覆盖率网格；merge_diagnostics 则在原图网格定位疑似块。混合像素是与同一批候选 SAM Mask 的一致性代理，且这些 Mask 也参与保护，不能作为独立准确率。

## VLM 实际调用与失败

环境已继承 VLM_API_KEY / VLM_BASE_URL / VLM_MODEL，没有读取或输出 .bashrc 内容、没有写入密钥。复用 scene-benchmark/benchmark/vlm.py 的 VLMClient、持久请求账本、PNG data URL、JSON mode 与安全错误处理；Session hook 使用固定 system prompt 和 temperature=0.2。

本结果目录有2次实际 VLM 尝试：首次 gpt-5.1 因原代理 TLS 失败，没有 HTTP/Token 回报；随后按用户指定最后一次额度，仅使用本地缓存确认的完整 ID openai/gpt-5.1，以及现有 BlenderWorld/scripts/ofox_tunnel.py。该临时回环 CONNECT 通道连接用户给定供应商 IP 47.83.144.71，URL/SNI/证书校验仍为 api.ofox.ai，未使用127.0.0.1:7897，未关闭 TLS 校验。

用户另述跨对话计数5/6；这不是本地生成的五条记录，单独记在 vlm_budget.json。本次只消耗最后1次，独立最终账本限额1，自动重试关闭。没有 DNS、模型目录或额外余额探测。

为了仅用最后一次请求覆盖两图，规划和分组合并为一次双图请求；每个 PNG 都由原图缩小副本与对应编号图组成。这偏离原先每图两阶段的计划，已记录实际 Prompt 和输入。Light Coarse 最多取32个最大区域供分组，未展示小块保持 Unknown，没有强制全图语义化。

最后请求 HTTP 200，耗时 15.245s，服务端 reported usage：{"prompt_tokens": 3353, "completion_tokens": 659, "total_tokens": 4012}；finish_reason=stop，actual_cost=None（未返回）。输出上限6000 Token，无自动重试。

返回能解析为 JSON，但层级错误：bw_9064 的 anchors/relations 被放进 regions 数组，后面混入损坏的分组字符串；bw_0074 与 group 字段缺失。严格契约校验将四个 scene/stage 全部标为 unavailable。保留 raw_answer / parsed_answer，但不挪动字段、不修复 ID、不把局部看似合理的内容升级为 Evidence，也没有据此生成书籍或唱片集合。

余额记录按用户给定的 [Ofox 余额接口文档](https://ofox.ai/zh/docs/api/openapi/balance) 实现白名单字段；首次查询因 SSLError 不可用。最新指示不再消耗连接检查，未做后置查询。因此没有可信的本轮余额差值，也没有猜测费用。账户余额差值即使可得也属于账户级，可能包含其他并发调用。

## 静态检查与结论

1. 连续区域：bw_9064 的地板和大片墙面明显少碎片；但近色墙面与顶棚会误合并，不能据块数下降认定语义质量提高。
2. DINO：尚无明显整体优势。它减少了复杂图相对候选 Anchor 的新增混合，但保留更多碎片，且 bw_9064 Feature Coarse 丢失部分建筑表面边界。两分支权重不同，未做独立 DINO 消融或人工 GT，不宣称因果改进。
3. VLM Anchor：原始回复提及桌、椅、盆栽和冰箱，可作为连通性观察，但结构失败，不能作为有效 Anchor 规划。正式候选列表仅保留原有 SAM3 Visual 每图5项，与 VLM 输出来源明确分开。
4. 书籍/唱片集合：未验证成功。复杂图 Coarse 仍有混合内容和碎片，VLM 没有有效回复；不能复制原任务示例冒充模型分组。
5. 幻觉：原始坏回复将 wall corner 列为 Anchor，粒度有疑问；无有效分组可判断误组率。需要人工看图核对，不能报告语义准确率。
6. 仅 SLIC+VLM：当前可构建可追溯视觉层级，但本次没有证明语义层有效。VLM 也不能从混合块中恢复精确边界。
7. SAM2/SAM3：在精细椅腿、透明椅、小盆栽、冰箱与背景分离等实例轮廓仍有价值。需要人工确认；没有可靠匹配时保留 mask_unavailable，不将零检测等同缺失。
8. 读取：Evidence JSON 沿用 regions/anchors/relations，并新增可选 label_map+label_value；load_document 支持 levels 子集读取，Fine 无需成百上千份重复 Mask。语义组若通过契约则保存成员 ID 及 Mask 并集；本轮 groups 为空、Unknown 完整保留。
9. 用量：本地2次 VLM 尝试、1次 HTTP200，服务端仅成功请求报告4012 Token、15.245s；首次失败耗时另见账本。不把用户所述外部请求纳入本地 Token 总量。
10. 审核：全部自动 Region/Anchor/Relation reviewed=false、mask_reviewed=false、reliability=0；未执行人工审核，没有冻结 GT。请重点查墙/顶棚误合并、混合书脊区域、沙发过分割、透明椅及细小物体边缘。

## 资源、测试与限制

CPU 单元测试先运行。GPU 两次只读检查均显示8卡被其他任务占用，约30–32GiB/卡、16个计算进程；没有可用空闲卡。DINO 只用CPU、2线程，模型只加载一次，两图特征推理约29.45s，不重复特征推理。没有安装依赖、下载模型或改共享环境。DINO 负载与每图算法时长详见 merge.json；CSV 同层重复列出的加载/特征时间不得逐行求和。

完整 CPU 单元测试88项通过（含新增13项），详见 test_results.log；产物检查852个节点、原图坐标 Mask/Label、DAG、引用、原始 SLIC 保留、现有 loader 和56个 HTML 本地链接通过，详见 validation.json。VLM JSON 语法通过但契约失败，语义质量验收未通过；无人工 GT，IoU / Boundary F1 跳过，SAM/Blender/正式评分未运行。结构合法不代表语义或边界准确。Light Coarse 在 bw_0074 的候选 Anchor 混合代理增加，故“无明显跨 Anchor”不能笼统宣布通过。

## 文件改动与复用

- 修改 e_harness/benchmark_evidence.py：新增简单 RAG 合并、VLM 契约与 DAG 检查；load_document 增加可选层筛选和 Label Map 引用。未改五类能量数学公式或聚合权重。
- 新增 scripts/build_vlm_region_hierarchy.py：分阶段实验、既有网关调用、层级构建与静态报告。
- 新增 tests/test_region_hierarchy.py：受控 CPU 图像与网关 mock（不消耗真实请求）。
- 复用 local_dino_extractor、既有 SLIC/SAM 产物、compare_region_segmentation 的边界/配色函数、VLMClient、OfoxTunnel；未修改这些共享模块、Runtime blocked 或历史产物。

## 最小复现

查看 comparison.html 或各图片 comparison.html；原始坏回复见 vlm_final.json。无需联网或模型重跑。以下构建命令在新目录执行；不要重用已有结果目录。

```bash
cd /home/xymo/projects/e-harness
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -v
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
OUT=results/vlm_region_hierarchy_reproduction
/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase prepare
/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase merge
/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase dino
# 离线回放已记录的真实 API 回复；不会再发送请求
cp results/vlm_region_hierarchy/vlm_final.json results/vlm_region_hierarchy/vlm_final_requests.json results/vlm_region_hierarchy/vlm_requests.json "$OUT/"
cp results/vlm_region_hierarchy/bw_9064/vlm_plan.json "$OUT/bw_9064/"
cp results/vlm_region_hierarchy/bw_9064/numbered_for_final.png "$OUT/bw_9064/"
cp results/vlm_region_hierarchy/bw_0074/numbered_for_final.png "$OUT/bw_0074/"
/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase build
/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase report
/home/xymo/environments/relateanything-inference/bin/python -B scripts/build_vlm_region_hierarchy.py --output "$OUT" --phase validate
```

本次真实 VLM 账本已封口；不提供会自动再消耗余额的复跑链。若只复现输出，可复用 vlm_final.json / Prompt / 输入 PNG 与两份账本，再执行 build、report、validate；脚本拒绝覆盖。下一轮若要新请求，须先重新获得明确预算。
