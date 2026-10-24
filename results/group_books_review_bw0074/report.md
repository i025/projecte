# bw_0074 书籍Group：人工审核准备

本轮仅离线生成显示裁剪和待填表，不调用API/模型，不修改历史结果或正式Energy。所有人工审核结论初始为 **unreviewed**；下文视觉提示不是人工确认。对象为R2展示书架中的书籍陈列集合，R3唱片明确排除。

## 历史真实回答：原样保留

| 侧 | present | shelf_sections | arrangement | 人工审核状态 |
| --- | --- | --- | --- | --- |
| reference | yes | 3+ | mixed | unreviewed |
| render | yes | 3+ | upright | unreviewed |

历史 `mixed → upright` 不改写，仍只是程序比较的candidate_violated，不是已确认重建错误；Reference回答也不是GT。此前合同已披露非严格盲测。

## 放大对照

- [完整R2书籍陈列放大](books_region_detail.png)：无涂黑、无锐化或补全；裁剪框不等于语义Group Mask。
- [上／中／下三个观察窗口](orientation_details.png)：横放书堆、竖放书脊与不确定细件的检查入口；窗口均为事后人工检查显示范围。
- [R2右缘与R3唱片对照](r2_r3_edge.png)：橙线为历史固定Reference ROI，不是Render物体边界预测。
- [待审核的固定网格建议图](distribution_grid_proposal.png)：青色虚线只示空间采样区，没有自动填入分布答案。

![书籍陈列局部对照](books_region_detail.png)

![方向观察窗口](orientation_details.png)

![R2/R3边缘](r2_r3_edge.png)

显示使用Reference原RGB与原生Render细节，Render窗口只依据历史全图fit反算，整数取整仅扩展显示裁剪边缘，没有重新配准或移动ROI。公共坐标1258×855；实际VLM输入是1024×696，放大图不能证明模型当时看到了同等细节。

| 显示窗口 | 公共坐标xyxy，像素 |
| --- | --- |
| R2 bounding window | [97, 87, 883, 550] |
| W1 upper | [97, 95, 883, 230] |
| W2 middle | [97, 230, 883, 355] |
| W3 lower | [500, 355, 883, 550] |
| R2/R3 edge | [763, 75, 1023, 560] |

## 人工审核表（全部待填写）

请分别查看原图、局部与边缘，再记录答案；不要从VLM回答复制勾选。

| 侧 | 清楚可辨竖放书籍 | 清楚可辨横向堆叠书籍 | 可能将唱片误认为书籍 | 严重遮挡／相机可见性问题 | 审核状态 | 审核人／证据窗口／说明 |
| --- | --- | --- | --- | --- | --- | --- |
| Reference | □ 是　□ 否　□ 无法判断（待填写） | □ 是　□ 否　□ 无法判断（待填写） | □ 是　□ 否　□ 无法判断（待填写） | □ 是　□ 否　□ 无法判断（待填写） | unreviewed | 待填写 |
| Render | □ 是　□ 否　□ 无法判断（待填写） | □ 是　□ 否　□ 无法判断（待填写） | □ 是　□ 否　□ 无法判断（待填写） | □ 是　□ 否　□ 无法判断（待填写） | unreviewed | 待填写 |

**仅供定位注意点，未作人工结论：**Reference有竖放书脊和水平堆叠的视觉线索；Render以竖向书脊状陈列较清楚，少数扁平细件可能是书、隔板或底座，须检查。Render的固定R2右缘可能包含R3唱片左缘；无需计入唱片也能找到多处书籍，但三个VLM字段不能揭示模型实际取证位置。不可据此宣称已排除混淆。相机与遮挡是否严重影响判断，由审核人填写；原生Render与最终blend同步未重新验证。

## 事后提出的方向操作定义（尚待审核）

分别记录两个独立字段，各取yes/no/unknown：

- **upright_presence**：至少一处装订书籍身份清楚、相对支撑面竖立；仅封面朝前不足以确定摆放方向。
- **horizontal_stack_presence**：至少两本可辨认装订书籍平放并上下叠置；单个扁平矩形、柜体隔板、底座、鱼缸盖、框画、唱片及唱片套均不算。
- 两项可以同时yes，表达“两种方向明确存在”，不再用未定义比例的“主要／mixed”替代。未见某类只有在范围充分可观察时才能填no；分辨率、类别、遮挡或方向不能可靠判断时填unknown。no也只限当前可见范围，不代表场景Confirmed Missing。

这些定义是**看过结果后的新建议**，没有重新验证；不得倒改旧mixed/upright答案，不能追溯宣称原冻结命题被违反、既往盲测成功或方法准确率提高。

## 为什么3+不能表达分布，以及最小替代记录

3格与更多格均落入3+；书籍可以由左移右、由上移下或集中到另一组柜格而保持3+。柜格划分还受遮挡、开放搁板与视角影响，因此同答不代表位置、范围或分散程度相同。

建议后续先冻结图示的 **3×3参考坐标网格**，两侧使用相同坐标，只审核每格与R2交集。每格记录“可见书籍／可观察但未见／unknown”；完全无ROI交集可记not_applicable。跨格书籍可使多格可见，因此不能把格数当书本数。网格不是实际柜格，不是精确Mask、密度或新的评分规则。本轮不填任何分布判断、不计算距离或Energy。

![最小集合分布表示建议](distribution_grid_proposal.png)

| 固定采样格 | Reference可见书籍状态 | Render可见书籍状态 | 审核状态 |
| --- | --- | --- | --- |
| A1 | 待填写 | 待填写 | unreviewed |
| A2 | 待填写 | 待填写 | unreviewed |
| A3 | 待填写 | 待填写 | unreviewed |
| B1 | 待填写 | 待填写 | unreviewed |
| B2 | 待填写 | 待填写 | unreviewed |
| B3 | 待填写 | 待填写 | unreviewed |
| C1 | 待填写 | 待填写 | unreviewed |
| C2 | 待填写 | 待填写 | unreviewed |
| C3 | 待填写 | 待填写 | unreviewed |

## 来源与轻量检查

- 只读来源：`/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/group_vlm_verification_bw0074` 中reference.png、render.png、render_native.png、R2.png、inputs.json、reference_contract.json、两侧真实answers。
- R2原始ROI：`/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/coarse_evaluation_roi_bw0074/B2_edge_polygons/R2.png`。本轮没有新Group Mask或正式Evidence。
- 已直接逐文件字节比对原结果目录的33个文件，完成后均未改变；没有计算哈希。输出图片均能由Pillow读取，显示窗口位于公共图像范围，历史回答保留原值。
- 新结果目录：`/srv/lab-disks/disk2/users/xymo/projects/e-harness/results/group_books_review_bw0074`。只生成本报告和4张显示图，未新增持久代码、模型、评分或审核通过状态。本轮完成后停止。
