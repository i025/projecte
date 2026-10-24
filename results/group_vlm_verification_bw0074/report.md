# 首次真实Group-level VLM Verification：bw_0074 / R2

仅书籍陈列集合bw_0074_R2_books。复用group_level_evidence_pilot中已冻结Reference合同、B2 R2 ROI和同Run真实Agent Render；未使用不存在的vlm_direct_grounding_bw0074目录，也没有修补无效历史Polygon。唱片属于R3，排除。

## Reference与问题来源

present复用冻结books_presence候选；shelf_sections是新增exploratory柜格覆盖问题；arrangement四分类是exploratory延伸。冻结books_orientations只说两方向均存在，不给“主要方向”比例或mixed阈值，不能把mixed当预期GT。采用用户给定中立System/User、两侧同一Prompt和枚举Schema；本地Reference期望没有进入请求。主代理已有历史Render知识，非严格盲测；没有按Render修改冻结证据或问题。

输入固定1258×855公共网格，同一ROI缩放至1024×696；每侧发送全图和R2轮廓标记图各一张、保留上下文。Render全图等比适配沿用历史参数，不按对象重对齐。原生Render另存render_native.png，最终blend同步及Reference相机未知，只能provisional/debug。

## 实际回答与比较

| 字段 | Reference | Render | 比较 |
| --- | --- | --- | --- |
| present | yes | yes | satisfied |
| shelf_sections | 3+ | 3+ | satisfied |
| arrangement | mixed | upright | candidate_violated |

发生明确答案变化的字段：['arrangement']。保存的是模型实际回答，不是Reference GT。逐字段严格枚举校验：某字段非法/缺失即unavailable，不删除其他合法字段；unknown是明确弃权。整包语法、HTTP失败停止，不重试、不补答。未将任何候选变化转为正式Energy，score/value均null，q=0，reviewed=false。

调用记录：2/2次；prompt tokens=3856，completion tokens=287，总tokens=4143；累计请求延迟=16.693754753796384秒。模型openai/gpt-6-sol。费用只看供应商实际返回值，未返回则unknown，不估算。详细HTTP、Token、延迟和错误见request_summary.json及两侧provider_response.json（已脱敏）。不因HTTP 200判定Schema或语义可靠。

## 解释与人工待审

- 一次Reference/Render请求只能检查这对图的可用性，不能证明模型稳定或可靠；需要人工核对是否确实识别书籍、没有混入R3唱片。
- 柜格数是离散覆盖类别，不是连续Spatial位置。3+饱和，既不区分3和更多，也不说明书籍是否集中到同一侧。开放书架分区、遮挡、视角会影响判断。
- 排列是粗粒度Statistical/VQA分类，不是密度/面积。upright/horizontal/mixed未规定占比，少量横放书是否应判mixed存在语义歧义，必须审核。
- 两侧相同只代表这些问题未发现差异，不覆盖书封/书脊、逐本身份、精细分布和颜色纹理；两侧不同也可能来自可见性、相机或识别误差。
- 若区域内present=no，最多是可见区域的候选缺失；保留书籍移出固定R2的Misplaced/Unknown可能。没有建立新Object Matching系统或Confirmed Missing证据。

## Region-only对照与Energy条件

原有R2 Appearance=0.265884，直接复用、不重新计算；Perceptual仍N/A。本轮没有运行DINO/SAM/SLIC/GPU/Blender。

Group回答提供“是否书籍”“占用柜格类别”“方向类别”三个可审语义诊断入口，是Region像素差异没有直接给出的内容。新增问题数量不代表准确率提升。Semantic存在性可在人工核实两侧回答与可见范围后进一步研究映射；柜格Spatial和方向Statistical均需先审核操作定义、模型判读及离散分类到既有指标的适用性。当前没有校准误差映射，三项正式Energy全部N/A，无综合分数。

## 测试、边界与复现

付费前完成tests_offline.txt与offline_checks.json：严格JSON、逐字段保留、未知/错误、固定同侧图片、预处理及无重试。实际预算通过持久预留和VLMClient账本限制，每侧只发一次session.post，经OfoxTunnel；没有余额/模型列表/额外自检请求。凭证只在请求阶段内存读取，Provider元数据先脱敏再交给客户端写账本；不保存认证Header或请求图像Base64。

离线重放（只读已保存实际答案，不发请求）：

```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_vlm_verification.py replay --source /srv/lab-disks/disk2/users/xymo/projects/e-harness/results/group_vlm_verification_bw0074 --output results/group_vlm_verification_bw0074_replay
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -p test_group_vlm.py -v
```

正式五能量、权重、Region Plan与ROI未改，未提交Git。所有候选仍reviewed:false。是否语义判读正确，仍需comparison.html逐字段人工审核；后续不自动扩展。

## 静态审核候选（不是新增VLM回答或人工GT）

- present：两侧R2可见装订书籍，yes/yes与可见证据大体一致。 无需计入R3即可支持yes；但三个答案不能证明模型实际使用了哪些书籍/柜格。
- shelf_sections：两侧各可辨至少三个含书的独立柜格，3+/3+在这一粗类别下合理。 3+存在饱和，不能推出精确数量、占用位置、覆盖范围或分散程度一致。
- arrangement：Reference兼有竖立书籍与多个水平书堆；Render主要为竖立书脊，mixed→upright具有可见候选依据。 Render少数扁平结构不易区分书堆与隔板/底座；主要方向与mixed没有比例阈值。不能据此确认冻结“两方向存在”命题被违反。

固定R2在Render右边界可能略含R3唱片左缘；无需使用它们即可解释yes/3+，但不能排除模型受其影响。相机与遮挡不同、取证位置未返回，全部保留人工审核；没有为此移动ROI或追加请求。

最终检查：16项离线CPU测试通过；两次真实响应Schema均合法；离线重放答案与比较一致，无新增调用；固定ROI、冻结Group和正式评分源码保持不变。见final_checks.json。
