# bw_0074/R3 Blender Scene Graph 审计

仅 Reference Group **bw_0074_R3_records**。所有对应和观察均 reviewed=false、provisional/debug；不产生正式Energy，不修改Reference/ROI或历史结果。

## 来源与读取

Run：`official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8`。Reference：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/data/hf-snapshot/bw_0074/tests/dataset/tasks/bw_0074/references/image_01.jpg`；Render：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/modern_living_room.png`；blend：`/srv/lab-disks/disk2/users/xymo/projects/BlenderWorld/runs/official-showcase-10-images-v2/bw_0074/bw_0074__KcPDLD8/artifacts/workspace/exports/final.blend`。
Run config的task.path → input.json的task_id/files → 原始参考图；同一Run artifact manifest将/workspace/exports映射到同一交付目录，其中包含这张PNG和final.blend。PNG的Camera、Scene、File、Frame及尺寸与保存场景相符；历史build_scene.py仅作为文本/AST读取，其305行保存final.blend，310行渲染PNG，未执行。确认同一重建来源，不等于重新验证blend与PNG逐像素同步。

没有已有Scene Graph或Object-ID文件。使用原有受限CPU启动器读取7.3MB输入副本，--factory-startup --disable-autoexec --offline-mode、open_mainfile(use_scripts=False,load_ui=False)，载入前清理回调；文本自动执行、Python drivers均禁用。独立用户/网络/PID/mount命名空间，原Run目录与输入副本只读bind mount；私有配置和空GPU可见列表，2核/线程、低优先级、60秒墙钟及CPU监测阈值、1GiB RSS停止阈值、8GiB地址空间上限、进程数4。监测阈值不是整任务内核配额；没有改正式Runtime blocked状态。

实际提取 0.921 秒，采样峰值RSS 290.2 MiB，退出0且清理完成。没有渲染/保存、历史Python执行或GPT/API调用。实际保存场景无Text块、driver或外链库。几何只读基础Mesh和存储变换，不求值修改器，不做遮挡或碰撞检查。

## 名称、层级与几何

共 900 对象、720 Mesh datablocks、175 Curve；所有对象都在一个Collection，全部无parent。Object名称常有明确建模意图，Mesh数据名仍多为Cube.*。没有独立唱片Collection、Group ID或标题块归属层级。

名称找到 **241 个VINYL封套主体候选**，各有独立基础Mesh，均为8顶点/6面长方体并带小倒角/法线修改器；另有 **28 个LP标题小块Mesh**，没有parent关联。因此不能把269个组件称为269张唱片，也不能将241个声明直接当作真实可见唱片数量。历史脚本文本显示一封套主体加间歇独立标题块的建模意图；没有逐封套的内部圆盘或精确封套结构验证。

另找到136个书籍主体名称。书籍与唱片有不同名称/材料名、粗空间分区，但都使用薄长方体，几何不构成可靠类别判别。封套局部XYZ尺寸范围为[[0.0080526, 0.0188676], [0.2956737, 0.3699093], [0.1910456, 0.4091566]]（场景单位米），高度/深度比[0.5268744, 1.3176886]；均有正厚度，排列近竖直。部分形状并非近方形，这可作为外观可辨识性的疑点，不能当作已确认语义或几何错误。

| 名称提示行底Z | 主体组件数（非GT数量） | 实测基础AABB底Z范围 | 长轴偏离世界+Z角度范围（度） |
|---|---|---|---|
| 1.45 | 43 | [1.4497441, 1.4500488] | [0.0127254, 3.4279369] |
| 1.90 | 99 | [1.8997843, 1.9000567] | [0.0003782, 3.3900776] |
| 2.36 | 99 | [2.3596823, 2.3599861] | [0.1097329, 3.3817723] |

名称提示三层与实际几何高度吻合，最低层在X方向分为两簇；所有候选中心Y约-0.28m。可读取世界坐标、范围、长轴方向和候选中心分布，无需Reference逐实例ID。但这些是模型组件组织，不是经过可见性验证的真实物体密度。

## 相机、投影与对应

保存相机位置约(2.07,-5.22,1.71)m，PERSP，实际lens=26.0mm、sensor_width=36.0mm、1920×1300、frame1，矩阵和内参见scene_graph.json。相机数据名含“30mm”，数值却是26mm，是名称不可充当参数真值的具体例子。历史相机不满足正式固定外参证据，Reference相机未知。

Group候选由名称、材料名、三层薄片几何及保存相机投影共同支持；宣称意图比较明确，视觉类别是否正确仍未审核。241个基础包围盒均可投影；215个包围盒与固定R3相交、184个完整落在R3内。这不是可见数量或分割准确率；部分候选投影在固定ROI之外，不能判缺失。

PNG与场景的相机名、场景名、分辨率及输出名一致，几何投影大致落在Render右侧陈列带。comparison.png右栏只画基础8角包围盒投影，未求值倒角，也不处理遮挡；projection_full_frame.png保留全幅位置。所有pass_index为0，Object Index/Material Index/Cryptomatte均关闭，因此**实际可见Mask、可见对象数、Group可见范围/密度均N/A**。不能用bbox并集冒充可见Mask。

历史中立分类实验的Render回答为ambiguous，而Scene Graph名称宣称VINYL；这体现“建模意图明确，但图像类别可辨识性不足”的候选落差，不足以确认唱片被建成书籍。仍需独立视觉/人工审核或经过验证的VLM，且不得追溯修改此前三个satisfied。

## 对Energy的帮助与结论

- Semantic：名称和材料名可提供可审计的语义意图与候选检索，但不能证明类别正确；需要图像可辨识证据和独立审核。
- Spatial：实际世界变换、几何范围和保存视角的bbox投影可用；可见位置仍需要可靠Object-ID/遮挡支持与Reference对应，历史视角差异限制归因。
- Statistical：可以对候选集合汇总方向、三层组织及中心位置分布，避免Reference逐张匹配；不能把Mesh计数、bbox面积或组件分布直接当作真实可见数量/密度。
- Appearance/Perceptual沿用既有图像比较，本轮未重算；五类Energy/权重及独立3D Structural Energy均未改。

值得将Scene Graph作为辅助证据来源，优先支持候选生成、语义意图审计和几何验证；当前不足以作为自动Group类别GT、正式匹配或评分输入。主要瓶颈是语义正确性、组件归属、像素可见性及Reference–Render对应，不是读出更多Mesh。

## 复现

离线重画（不启动Blender，目标目录必须不存在）：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/audit_scene_graph.py --stage replay --output results/blender_scene_graph_audit_bw0074 --destination results/blender_scene_graph_audit_bw0074_replay
```

需要重新提取时，只运行本轮可信读取器，仍不渲染；资源不可用或只读mount失败即停止，无降级执行：

```sh
/home/xymo/environments/relateanything-inference/bin/python -B scripts/audit_scene_graph.py --stage extract --output results/blender_scene_graph_audit_bw0074_reextract
/home/xymo/environments/relateanything-inference/bin/python -B scripts/audit_scene_graph.py --stage report --output results/blender_scene_graph_audit_bw0074_reextract
```

5项CPU单元测试通过，覆盖留边坐标转换、bbox交集、组件候选边界、不得由几何生成可见Mask/语义GT，以及读取器禁止保存/渲染/文本执行的约束。真实来源、完整命令、资源日志、源文件前后状态及最终检查在 `runs/scene_graph_audit_1792767018825950306`。本轮无HTML、无新渲染、无GPU、无Agent/GPT/API调用、无Git提交；审计后停止。
