# bw_0074 Region-first 第一轮

结构合法的 VLM 自动规划已得到4个有意义的粗区域；未出现逐本书籍/唱片或物体部件拆分。本文语义判断为参考图静态检查，尚未经过人工审核。

|ID|VLM 名称|主要可见内容|定位|
|---|---|---|---|
|R1|工作区|书桌、显示器、台灯和透明椅子|approximate_support|
|R2|展示书架|书籍、地球仪、装饰摆件、飞机图片和小型水族箱|approximate_support|
|R3|唱片与音响区|书架上的大量唱片、收录机和下方的唱盘设备|approximate_support|
|R4|沙发区|蓝色沙发、靠垫和彩色抱枕|approximate_support|

名称和内容直接来自实际 VLM JSON；没有把预期场景名称写入输入或替换模型输出。API仅接收1024×696的参考RGB，无编号图、Agent Render、Anchor或Relation任务。

定位为明确的低成本启发式：以既有 SAM3 Visual 元数据类别别名关联种子 bbox，结合 VLM 相对位置描述给出粗窗口；再取原有 DINO Feature Coarse Label Map 中窗口占据率≥50%的块的并集。没有重新运行 SAM 或 DINO。所有框、Mask 和块选择均为算法侧生成，不是 VLM 输出；候选可靠性保持0。

这些是近似评价支持区域，不能声称完整的语义集合已被自动分割。工作区种子仅显示器/椅子，整张桌、灯和笔记本未独立定位；展示架原有Mask过宽，与工作区/唱片区的分界依赖位置先验；唱片种子不能证明包含下方所有设备。沙发已有整体Mask可复用，但这里的SLIC并集仍不是经过审核的精确沙发Mask。四个粗窗口可用于人工检查粒度，四个完整语义Mask均未验证。

SLIC粗块可能使范围膨胀、合并不相关内容或在两区域间重叠，不强制唯一分区。定位使用有限的中文/英文类别别名，不能泛化为已验证的开放词汇定位器。没有制作新的Anchor/Relation。

本轮粗评价区域不必依赖 SAM；若之后需要精确排除邻近区域、遮挡处的边界或透明椅等细结构，SAM候选才有帮助，仍需要人工审核。已有SAM候选也参与本次定位，因此不能声称此次实现完全不依赖SAM。

覆盖统计（原图像素并集）：{"candidate_region_union": 0.8644873976143326, "candidate_region_overlap": 0.1229706486672431, "remaining_global_dense_patch_fraction": 0.1355126023856674, "dense_coverage": 1.0, "reviewed_region_coverage": 0.0, "note": "Pixel unions, not summed areas; remainder retains Global + Dense Patch. No energy calculated."}

请求：{"model": "openai/gpt-6-sol", "http_status": 200, "finish_reason": "stop", "usage": {"prompt_tokens": 1010, "completion_tokens": 280, "total_tokens": 1290, "completion_tokens_details": {"reasoning_tokens": 115}}, "actual_cost": null, "latency_seconds": 8.788518347078934, "automatic_network_retry_enabled": false}

本轮付费请求总数1；无自动重试、无余额/DNS探测、无JSON Mode，输出上限1500 Token，temperature=0.2。服务端报告少量隐藏 reasoning_tokens；没有要求长篇推理或解释，没有在报告展示推理内容。实际费用未返回，不作推算。

先运行93项CPU离线测试并通过（包含新增5项Region-first测试），详见offline_tests.log。Schema由显式REGION_FIRST_SCHEMA描述并用轻量函数校验，不新增jsonschema依赖。业务Schema校验不代表语义或定位准确。最终产物检查见validation.json。

源码：修改 e_harness/benchmark_evidence.py 增加Region-only Schema/校验；新增 scripts/region_first_pilot.py 复用 VLMClient、OfoxTunnel 与既有产物；扩充 tests/test_region_hierarchy.py。五类能量与权重、正式Runtime及历史产物未变。

最简复现（只读回放，无新API请求）：
```bash
cd /home/xymo/projects/e-harness
/home/xymo/environments/relateanything-inference/bin/python -B -m unittest discover -s tests -v
# 直接打开 results/region_first_pilot_bw0074/comparison.html
```

如要重新绘图，在新的非冲突目录复制input.json、vlm_plan.json、vlm_response.json、vlm_requests.json，再运行：
```bash
/home/xymo/environments/relateanything-inference/bin/python -B scripts/region_first_pilot.py --output <新回放目录> --phase visualize
```

已保留原始模型回复、请求参数（不含凭证/Base64）和Schema。付费request阶段在该目录不可再次运行。本轮结束。

参考图静态检查：4个名称与可见内容初步一致，无逐本或部件拆分。边框是粗ROI，颜色是所选SLIC块并集，两者不必一致。示范图保留了工作区/展示架交叠、唱片设备区范围不确定、沙发支持带入邻近地板/家具的现象；不能将本图作为经过审核的最终语义分区。
