# bw_0074：Direct 响应拒收

一次实际请求返回了四区 JSON，但 R1 Polygon 有 10 个顶点，违反冻结的 3–8 点限制。精确错误：`Expected 3–8 vertices`。

未修补坐标、未接受部分结果，B/C 显示 N/A，没有 Direct Mask。`rejected_regions.json` 保存未接受的实际坐标，不能用于评分。其余材料包括原始脱敏响应、历史 B2 对照与逐区静态诊断。所有候选 reviewed:false。

[本图对照](comparison.html) · [完整实验报告及两图离线复现命令](../report.md) · [失败详情](failure_analysis.json) · [原始回答](vlm_response.json)

成本：1 次请求，2121 Token，22.467 秒，无重试。
