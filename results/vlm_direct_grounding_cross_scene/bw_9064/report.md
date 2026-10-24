# bw_9064：两区 Direct ROI 候选

一次实际请求为既有桌椅区与冰箱区返回合法非空 Box 和 Polygon。Box 与 Polygon 独立预测，原始坐标未修补；没有冲突消解。

静态检查认为 B/C 主要内容大致完整，历史 A 遗漏盆栽上部。Polygon 减少部分背景，但没有证据表明它比 Box 更完整。细腿、叶尖、冰箱底脚及上下文宽度仍待人工审核。所有候选 reviewed:false，不能作为 GT 或正式评分依据。

[本图逐区对照](comparison.html) · [完整实验报告及两图离线复现命令](../report.md) · [实际坐标](direct_regions.json) · [原图坐标](native_coordinates.json) · [几何审计](geometry_audit.json)

原分辨率二值 Mask 在 `A_historical_native/`、`B_direct_box_native/`、`C_direct_polygon_native/`，均为 1672×941。现有证据加载器可以读取，评分前需人工审核冻结 ROI 和指标适用性。

成本：1 次请求，2057 Token，17.074 秒，无重试。
