# bw_0074/R3 Group可见性最小实验

全部reviewed=false、provisional/debug。只处理既有241个封套主体候选，没有重新做语义发现、匹配或正式评分。

## 对应证据与单次渲染

同一Run `official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8`。来源blend：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/final.blend`；历史PNG：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/modern_living_room.png`。按轨迹的Write/Edit记录仅重建文本，逐字等于导出脚本；最后一次执行先保存场景再渲染，交付结果确认两文件，随后没有场景修改。静态读出的相机位置/目标/26mm焦距与已审计场景矩阵及PNG的Camera/Scene/Frame/分辨率匹配。原blend与此前审计副本字节相同。门控记录见JSON.protocol.correspondence。这是文档和数值对应证据，不是逐像素同步认证；仍属历史相机诊断，未用正式T0替换相机。

无可复用的本Run ID/Segmentation/Cryptomatte Pass。使用原Cycles、原相机和遮挡几何/材质/灯光；仅在内存给241个主体赋互异Object Index，其他对象保持ID0和正常遮挡。28个标题部件缺少已审核归属，全部排除，未当作额外唱片；它们仍可遮挡主体。用同一次渲染的IndexOB和Combined输出提取数据，没有第二次渲染。

最长边512（512×347），1 sample，CPU两线程，无自适应采样/去噪；用极小pixel-aspect补偿整数分辨率取整，保留保存相机的物理画幅比例和全部内外参。未保存blend。Autoexec/use_scripts禁用、清除载入回调，空用户配置、空GPU可见列表、断网/PID/mount命名空间，原Run和输入副本只读绑定；宿主UID 1005，不提权。原有监控器设置90秒墙钟、60秒CPU、1GiB RSS停止阈值、8GiB地址空间上限、低优先级/两核亲和性；监测阈值不等于整任务内核配额。首次资源预检发现默认CPU1繁忙，在启动任何Blender前停止；第二次从允许范围选择空闲核[5, 6]，实际只启动一次渲染。两次预检均保留，实际采用的记录为 `/srv/lab-disks/disk2/users/xymo/projects/e-harness/runs/group_visibility_1792769066374241102/resource_preflight_2.json`。PID视图仅能看到当前命名空间任务，不能声称检查了全部宿主进程。

## 实际结果

真正提取Cycles IndexOB数据（原始EXR及逐对象uint16数组在work），并非BBox并集。原始Mask为[512, 347]，6437像素；R3内5632 / 26316像素，占21.4014%。805个Group像素在固定R3之外，占Group的12.5058%。没有移动ROI。

228/241个候选主体Mesh在本次低分辨率采样中各贡献至少一个ID像素；不是历史高分辨率的完整可见数量，更不是唱片实例GT。其他未采到像素的对象可能被遮挡、太薄或落在子像素，不能认定缺失。

| 名称层架Z（已用几何底Z核对） | 候选主体Mesh | 有ID像素的Mesh | Group像素 | R3内 | R3外 |
|---|---|---|---|---|---|
| 1.45 | 43 | 41 | 1519 | 1218 | 301 |
| 1.90 | 99 | 94 | 3165 | 2834 | 331 |
| 2.36 | 99 | 93 | 1753 | 1580 | 173 |

BBox并集有8048像素，其中1611没有对应Group ID支持。差集包含空包围盒内部、其他对象/标题遮挡、低分辨率漏采和边界效应，不能全部称作遮挡面积。低层BBox越过收录机的部分是特别需要审核的代理失真案例。Group ID在BBox之外有0像素，保留原值，不裁剪美化。

总进程墙钟1.945秒，采样峰值RSS 401.0MiB；清理完成=True。完整原始输出、命令及资源日志在 `runs/group_visibility_1792769066374241102`。一次预约文件阻止本次自动重试。
配置的是2个渲染工作线程和两核亲和性；监测到的进程原生线程总数峰值为11（含主线程和IO/库辅助线程），并未硬限制总线程数为2。采样累计CPU时间最大2.61秒。若将“两线程”理解为包含所有辅助线程的严格总数上限，本轮未满足该更严格口径，不隐瞒此资源边界。

## 失败案例与技术警告

完整日志保留两项警告：

- `Warning: File written by newer Blender binary (402.67), expect loss of data!`：本地读取器为4.2.0，不能认证它完整保留原写入器的全部状态。相机参数、候选变换及输出尺寸检查通过，ID输出有效，但**本轮Mask只代表当前读取器中的条件性可见支持，不是原历史PNG逐像素可见性的认证**。如果要求严格历史渲染器等价，此项仍为阻塞；没有下载或更换软件重试。
- 退出时出现 `ValueError: list.remove(x): x not in list`，来自Cycles注销时试图移除已被安全读取器清理的version_update回调。Pass已输出、数组校验通过、进程退出0并清理完成；没有隐藏该异常，也没有为修复退出回调再渲染。

## 可用信息和限制

实际获得的是这一低资源配置下的渲染通道可见支持，含真实遮挡，优于BBox定位代理；不等于高分辨率、抗锯齿或人工审核的像素GT。IndexOB的透明度阈值、透明材质、薄片与边缘漏采均可能影响结果，阈值和原始设置保存在visibility.json.pass_settings。原始visibility_mask.png不含上采样；comparison的Mask仅为同坐标显示而最近邻放大。

三层归属来自既有名称提示，并在读入场景中以实际几何底Z核对，允许按层汇总可见像素分布；不从聚合Mask推断实例数量。逐对象ID仅支持统计本次采样到的候选Mesh，未解决语义类别GT或标题归属。无额外去遮挡/xray渲染，因此未采到像素的原因不逐对象强行归类。

Scene Graph名称提供候选身份，几何变换提供排列方向，ID Pass提供生成侧可见范围/分布；三者结合可辅助Group-level Spatial/Statistical。但Reference只有存在、多柜格、主要竖直的候选证据，没有可靠唱片Mask GT，故不做Mask IoU；生成侧几何也不能证明图像语义一致。此前Render类别ambiguous和三个satisfied均不改写。

值得作为可选诊断工具保留，前提是场景/相机对应、读取器兼容性、语义组审核、Pass透明度与边界规则明确、资源允许。目前不作为正式评分依据。7项纯CPU离线测试通过，涵盖逐ID统计、N/A处理、固定ROI留边映射、BBox不得冒充Mask、一次渲染预约与可信读取器约束；它们不等于像素准确率验证。没有API/GPT子Agent、没有运行历史生成代码、没有修改Runtime/ROI/Evidence/Energy、没有Git提交或HTML；完成后停止。

## 离线复现

只重放已保存的ID数组和设置、生成新报告，不启动Blender；目标必须不存在：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/group_visibility.py --stage replay --output results/blender_group_visibility_bw0074 --destination results/blender_group_visibility_bw0074_replay
```

本次新渲染已完成或消耗一次尝试，不自动重跑。可信读取/渲染代码为scripts/group_id_blender.py，实际命令与一次预约在work目录；重跑需要新的明确实验授权，不使用replay触发渲染。
