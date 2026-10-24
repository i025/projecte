# Reference-only 原子证据草拟（已冻结）

本文件与 reference_evidence_frozen.json 在 Reference-only 阶段一次写入后冻结。两区域各 7 条，共 14 条；其中 13 条是未复核的可见观察草稿，1 条为 unknown（R3_SEM_03，expected=null）。所有条目 reviewed=false、reliability=0，不是人工 GT，也不是外部 VLM 自动提取。

## 范围与来源

只观察指定的 Reference 和 R2/R3 既有二值 Mask。读取 region_plan.json 与 C_direct_polygon/evidence.json 用于继承区域 ID、图像大小、候选 Mask 路径及边框。仅在许可的通用 benchmark_evidence.py 中检索原子证据/加载字段关键词，没有读取其他历史结果、Render、差异图、评价/验证结果或 Report。未使用网络、付费 API、GPU、模型服务、Blender 或其他 Agent。

Mask 是既有未复核候选区域，不能证明对象的精确边界或区域内容完整性。条目的 scope.bbox 是本次观察的参考图像支持范围，坐标原点为左上角，使用 [left, top, right, bottom) 像素约定；支持范围可能略超过候选 Mask，以保留完整可见对象，不能自动当成新分割 Mask。

## 选择原则

R2 选择交叠环带吊灯、果盘、吊灯与岛台的二维位置关系、椅子排列、可见椅子数量，以及岛台脉纹和椅面色系。R3 选择壁柜、盆栽、两项二维相对位置、搁架器皿数量和中央背景脉纹。不逐件罗列无关小物件，不推断背面、遮挡处或完整场景库存。

颜色与脉纹分别标为 appearance，不能用视觉颜色距离替代 Semantic。脉纹类别只能说明可见图样，不证明真实大理石、皮革或其他材质。Spatial 仅指图像上下、左右、横向排列及近似水平对齐，不推断三维世界坐标或深度。

region_plan.json 虽提及炉灶，但在 Reference 中相关部位被前景遮挡且细节不够明确。因此 R3_SEM_03 保留 unknown，expected=null；后续不得把它当作肯定或否定证据计分。

## 冻结与计分边界

本 JSON 是来源透明的 assistant_reference_only_visual_draft。保留原始候选 Mask，不改动原图或 Mask。14 条证据的 ID 唯一、字段齐全，支持边框均在 1536×837 图像范围内；冻结前完成结构自查。计分时应排除 unknown，且任何自动评分仍需明确这些条目没有人工语义复核。第二阶段不得回写本证据文件以迎合 Render。

未生成局部检查图：环境缺少 Pillow；最终观察仍完全来自 view_image 展示的原始 Reference 与既有 Mask。
