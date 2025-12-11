# 仿真动画生成 - 用户指南

**版本**: 2.0 (LS-PrePost 4.8兼容版)
**功能**: 自动将LS-DYNA仿真结果（d3plot文件）渲染为GIF/AVI/MPEG动画
**最后更新**: 2025-11-17

---

## 📋 功能概述

本系统提供**专业自动化方案**，通过后端Python程序自动调用LS-PrePost软件，将d3plot仿真结果渲染为高质量动画。

**核心优势**：
- ⚡ **全自动渲染** - 无需手动操作LS-PrePost
- 🎨 **自定义视角** - 支持7种相机视角
- 📊 **多种云图变量** - 应力、应变、位移、速度等
- 🔄 **异步任务队列** - 后台处理，不阻塞前端
- 🎬 **专业质量** - 使用LS-PrePost原生渲染引擎
- 🎞️ **多种格式** - GIF (Web展示), AVI (高质量), MPEG (兼容性)

**版本兼容性**：
- ✅ 基于 **LS-PrePost 4.8** (ANSYS 2022 R2集成版)
- ⚠️ 不支持 **MP4格式** (4.8限制，可用FFmpeg转换)

---

## 🎯 前置条件

### 1. 软件要求

| 软件 | 版本要求 | 说明 |
|------|----------|------|
| LS-PrePost | 4.8+ (ANSYS 2022 R2) | 必需，用于渲染动画 |
| Python | 3.11+ | 后端服务 |
| LS-DYNA | 任意版本 | 生成d3plot文件 |
| FFmpeg | 可选 | 用于格式转换 (GIF→MP4等) |

### 2. 仿真流程

```
K文件 → LS-DYNA求解器 → d3plot文件 → LS-PrePost → GIF/AVI动画
        ↑ 本系统生成           ↑ 用户运行      ↑ 本系统自动调用
```

**重要**：动画生成功能需要用户先运行LS-DYNA仿真，产生d3plot文件。

---

## ⚙️ 配置步骤

### 步骤1: 确认LS-PrePost安装

检查LS-PrePost 4.8是否已安装（通常随ANSYS 2022 R2一起安装）。

**Windows典型路径**：
```
E:\ansys22r2\ANSYS Inc\v222\ansys\bin\winx64\lsprepost48\lsprepost4.8_x64.exe
```

**Linux典型路径**：
```
/opt/ansys_inc/v222/ansys/bin/linx64/lsprepost4.8
```

### 步骤2: 配置系统

编辑文件：`backend/config.json`

```json
{
  "lsprepost_executable": "E:\\ansys22r2\\ANSYS Inc\\v222\\ansys\\bin\\winx64\\lsprepost48\\lsprepost4.8_x64.exe",
  "animation_output_dir": "D:\\Simulations\\animations"
}
```

**注意事项**：
- Windows路径使用双反斜杠 `\\` 或单斜杠 `/`
- 确保路径指向实际的LS-PrePost 4.8可执行文件
- 如果文件不存在，复制 `backend/config.json.template` 并修改

### 步骤3: 验证配置

启动后端服务：
```bash
cd backend
python app.py
```

如果配置正确，会看到：
```
[INFO] 动画生成器初始化成功
[INFO] LS-PrePost路径: E:\ansys22r2\...\lsprepost4.8_x64.exe
```

如果看到错误：
```
[ERROR] LS-PrePost可执行文件不存在: ...
```
说明配置路径有误，请检查 `config.json`。

---

## 🚀 使用流程

### 完整工作流

```
┌────────────────┐
│ 1. 生成K文件   │  ← 使用Web界面配置参数，生成K文件
└────────┬───────┘
         ↓
┌────────────────┐
│ 2. 运行仿真    │  ← 在LS-DYNA中运行K文件，生成d3plot
└────────┬───────┘
         ↓
┌────────────────┐
│ 3. 生成动画    │  ← 使用本系统自动渲染动画 (GIF/AVI/MPEG)
└────────┬───────┘
         ↓
┌────────────────┐
│ 4. 播放/下载   │  ← 在线播放或下载文件
└────────────────┘
```

### 详细步骤

#### 第1步：运行LS-DYNA仿真

假设你生成了K文件：`bullet_sim_20251117_143022.k`

1. 在LS-DYNA中运行该文件
2. 等待求解完成，产生d3plot文件
3. 记录d3plot文件的完整路径

**d3plot文件示例路径**：
```
D:\Simulations\bullet_sim_20251117_143022\d3plot
```

#### 第2步：创建动画任务

1. 打开Web界面：`http://localhost:8000`
2. 滚动到"仿真动画生成"部分
3. 填写表单：

| 字段 | 说明 | 示例 |
|------|------|------|
| d3plot文件路径 | 服务器可访问的绝对路径 | `D:\Simulations\bullet_sim\d3plot` |
| 相机视角 | 7种预设视角 | 等角视图 (Isometric) |
| 云图变量 | 显示的物理量 | 应力 (Stress) |
| 视频分辨率 | 输出视频分辨率 | 1920x1080 (Full HD) |
| **输出格式** | **GIF/AVI/MPEG** | **GIF (推荐)** |
| **起始帧** | **动画起始帧号** | **1** |
| **结束帧** | **动画结束帧号 (留空=自动检测)** | **留空** |
| **显示选项** | **部件/图例/坐标轴** | **全选** |

4. 点击"开始生成动画"

#### 第3步：监控任务进度

- 任务创建后，前端会显示任务卡片
- 状态自动更新（每3秒轮询一次）
- 查看进度条了解渲染进度

**任务状态**：
- 🟡 **等待中 (pending)** - 任务已创建，等待处理
- 🔵 **处理中 (processing)** - 正在渲染动画
- 🟢 **已完成 (completed)** - 动画生成成功
- 🔴 **失败 (failed)** - 渲染失败，查看错误信息

#### 第4步：播放或下载动画

任务完成后，任务卡片会显示两个按钮：
- **播放** - 在网页中直接播放动画 (GIF显示为图片, AVI/MPEG使用视频播放器)
- **下载** - 下载文件到本地

---

## 🎨 参数说明

### 相机视角

| 视角 | 英文名 | 说明 |
|------|--------|------|
| 等角视图 | Isometric | 默认视角，适合整体观察 ✅ 推荐 |
| 正视图 | Front | 从前方观察 |
| 后视图 | Back | 从后方观察 |
| 俯视图 | Top | 从上方俯视 |
| 仰视图 | Bottom | 从下方仰视 |
| 左视图 | Left | 从左侧观察 |
| 右视图 | Right | 从右侧观察 |

**推荐**：首次使用选择"等角视图"，可以看到完整的穿甲过程。

### 云图变量

| 变量 | 英文名 | 说明 | 适用场景 |
|------|--------|------|----------|
| 应力 | Stress | 材料的应力分布 | ✅ 分析材料破坏、塑性变形 |
| 应变 | Strain | 材料的应变分布 | 研究变形程度 |
| 位移 | Displacement | 节点位移大小 | 观察整体运动轨迹 |
| 速度 | Velocity | 节点速度大小 | 分析动态响应 |
| 加速度 | Acceleration | 节点加速度大小 | 研究冲击载荷 |
| 塑性应变 | Plastic Strain | 塑性应变分布 | 分析永久变形区域 |

**推荐**：穿甲仿真通常使用"应力 (Stress)"查看材料的受力情况。

### 输出格式对比 ⭐ 新增

| 格式 | 浏览器支持 | 文件大小 | 画质 | 推荐用途 |
|-----|----------|---------|------|---------|
| **GIF** ✅ | 原生支持 (`<img>`) | 中等 (5-20MB) | 中 (256色) | **Web展示、快速预览** |
| **AVI** | 需转换 | 大 (50-200MB) | 高 (无损) | 高质量存档、后期编辑 |
| **MPEG** | 支持 (`<video>`) | 小 (3-10MB) | 中 | 兼容性播放 |

**格式选择建议**：
- 🌐 **Web展示**: GIF (推荐)
- 📊 **PPT演示**: AVI → FFmpeg转MP4
- 📁 **存档备份**: AVI (高质量)
- 📧 **邮件分享**: GIF (文件小)

**MP4转换** (如需MP4格式):
```bash
# AVI → MP4
ffmpeg -i animation.avi -c:v libx264 -crf 23 -preset medium animation.mp4

# GIF → MP4
ffmpeg -i animation.gif -movflags faststart -pix_fmt yuv420p animation.mp4
```

### 帧范围控制 ⭐ 新增

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| **起始帧** | 动画起始帧号 (从1开始) | 1 | 1 |
| **结束帧** | 动画结束帧号 (留空=自动检测) | 自动 | 30 或 留空 |

**使用场景**：
- **完整动画**: 起始帧=1, 结束帧=留空 (推荐)
- **截取片段**: 起始帧=10, 结束帧=50 (只输出第10-50帧)
- **关键帧**: 起始帧=1, 结束帧=20 (减小文件大小)

### 显示选项 ⭐ 新增

| 选项 | 说明 | 默认 |
|------|------|------|
| **显示所有部件** | 使用 `pall` 命令显示所有几何 | ✅ 勾选 |
| **显示图例** | 显示云图颜色条 (`showlegend 1`) | ✅ 勾选 |
| **显示坐标轴** | 显示XYZ坐标系 (`showtriad 1`) | ✅ 勾选 |

**推荐**：
- 首次使用全部勾选
- 如需清晰截图，可取消勾选坐标轴

### 视频参数

| 参数 | 可选值 | 推荐 | 说明 |
|------|--------|------|------|
| 分辨率 | 1280x720, 1920x1080, 3840x2160 | 1920x1080 | Full HD足够，4K文件较大 |
| ~~帧率~~ | ~~已移除~~ | - | LS-PrePost 4.8 movie命令不使用fps |

---

## 📂 文件位置

### 生成的文件存储位置

所有动画文件存储在 `config.json` 中配置的 `animation_output_dir` 目录：
```
D:\Simulations\animations\
├── animation_20251117_143022_a1b2c3d4.gif      ← GIF动画
├── animation_20251117_143055_b2c3d4e5.avi      ← AVI动画
├── cfile_a1b2c3d4.cfile                        ← CFILE脚本（调试用）
└── ...
```

### 文件命名规则

```
animation_{时间戳}_{任务ID前8位}.{格式}
```

示例：
```
animation_20251117_143022_a1b2c3d4.gif
animation_20251117_143055_b2c3d4e5.avi
```

---

## ⚠️ 常见问题

### Q1: 创建任务时提示"d3plot文件不存在"

**原因**：
- 路径错误或使用相对路径
- 服务器无法访问该路径（权限问题）
- d3plot文件尚未生成

**解决**：
1. 使用**绝对路径** (如 `D:\Simulations\case1\d3plot`)
2. 确认LS-DYNA仿真已完成，d3plot文件确实存在
3. 确保后端服务有权限访问该目录

### Q2: 任务失败，错误信息"Invalid command"

**可能原因**：
- CFILE脚本语法错误（罕见，系统自动生成）
- LS-PrePost版本不兼容

**排查步骤**：
1. 检查使用的是 LS-PrePost 4.8 而非其他版本
2. 查看 `lspost.msg` 文件中的详细错误
3. 手动测试CFILE:
```cmd
"E:\ansys22r2\...\lsprepost4.8_x64.exe" c=cfile_xxx.cfile -nographicscls
```

### Q3: 为什么不支持MP4格式?

**原因**：LS-PrePost 4.8 (ANSYS 2022 R2集成版) 不包含MP4编码器。

**解决方案**：
1. **方案A (推荐)**: 使用GIF格式 (浏览器原生支持)
2. **方案B**: 生成AVI，然后用FFmpeg转MP4:
```bash
ffmpeg -i animation.avi -c:v libx264 -crf 23 animation.mp4
```

### Q4: GIF文件太大，如何优化?

**方法1: 降低分辨率**
- 从1920x1080改为1280x720
- 文件大小减少约50%

**方法2: 减少颜色数** (使用gifsicle)
```bash
gifsicle -O3 --colors 128 animation.gif -o animation_optimized.gif
```

**方法3: 减少帧数**
- 起始帧=1, 结束帧=20 (只输出前20帧)

**方法4: 转换为MP4** (体积更小)
```bash
ffmpeg -i animation.gif -c:v libx264 -crf 23 animation.mp4
```

### Q5: 任务状态一直是"处理中"，但很久没完成

**可能原因**：
- d3plot文件很大，渲染需要较长时间
- LS-PrePost进程卡住

**解决**：
1. 耐心等待（大模型可能需要5-10分钟）
2. 检查服务器CPU和内存使用情况
3. 查看后端控制台输出:
```
[INFO] 开始调用LS-PrePost渲染动画...
```
4. 检查 `lspost.msg` 文件实时输出:
```cmd
tail -f lspost.msg
```

### Q6: 如何批量生成多个视角的动画?

**当前版本**：需要手动创建多个任务

**操作步骤**：
1. 创建任务1：等角视图 + 应力 + GIF
2. 创建任务2：正视图 + 应力 + GIF
3. 创建任务3：俯视图 + 位移 + GIF

所有任务会并发执行（异步队列）。

---

## 🔧 高级功能

### 查看CFILE脚本

系统生成的CFILE脚本存储在：
```
{animation_output_dir}/cfile_{任务ID}.cfile
```

**LS-PrePost 4.8 格式示例**：
```cfile
$# LS-PrePost 4.8 GIF Animation Script
$# 生成时间: 2025-11-17 14:30:22

$# 1) 打开 d3plot 文件
openc d3plot "D:\Simulations\bullet_sim\d3plot" nodialog

c 2) 显示所有部件
pall

c 3) 设置视角
isometric

c 4) 自动居中缩放
ac

c 5) 设置云图变量
fringe 1 1

c 6) 显示选项
showlegend 1
showtriad 1

c 7) 输出动画
movie GIF 1920x1080 "D:\Simulations\animations\animation_..." 1 999

c 8) 退出
exit
```

**手动运行CFILE**（调试用）:
```cmd
cd D:\Simulations\animations
"E:\ansys22r2\ANSYS Inc\v222\ansys\bin\winx64\lsprepost48\lsprepost4.8_x64.exe" c=cfile_xxx.cfile -nographicscls
```

**查看执行日志**:
```cmd
type lspost.msg
```

### API接口文档

访问完整API文档：
```
http://localhost:8000/docs
```

主要端点：
- `POST /api/animation/generate` - 创建任务
  - 新增参数: `output_format`, `start_frame`, `end_frame`, `show_all_parts`, `show_legend`, `show_triad`
- `GET /api/animation/status/{task_id}` - 查询状态
- `GET /api/animation/list` - 列出所有任务
- `GET /api/animation/download/{task_id}` - 下载动画文件

---

## 📊 性能参考

### 渲染时间估算

| d3plot大小 | 时间步数 | 分辨率 | 格式 | 预估时间 |
|-----------|---------|--------|------|----------|
| 100 MB | 100 | 1920x1080 | GIF | 1-2 分钟 |
| 500 MB | 500 | 1920x1080 | GIF | 3-5 分钟 |
| 1 GB | 1000 | 1920x1080 | GIF | 5-10 分钟 |
| 1 GB | 1000 | 1920x1080 | AVI | 10-15 分钟 |

**注意**：
- GIF渲染速度快于AVI
- 实际时间取决于CPU性能和模型复杂度

### 文件大小参考

| 格式 | 分辨率 | 时长 | 预估大小 |
|------|--------|------|----------|
| GIF | 1920x1080 | 10秒 | 10-20 MB |
| GIF | 1280x720 | 10秒 | 5-10 MB |
| AVI | 1920x1080 | 10秒 | 50-100 MB |
| MPEG | 1920x1080 | 10秒 | 3-8 MB |

---

## 💡 最佳实践

### 1. 规划仿真输出

在运行LS-DYNA时，合理设置d3plot输出频率：
- 太密集：文件大，渲染慢
- 太稀疏：动画不流畅

**推荐**：穿甲过程持续30µs，输出100-200个时间步即可。

**K文件配置示例**:
```
*DATABASE_BINARY_D3PLOT
         0.3        0         0         0
```
(每0.3µs输出一帧，30µs共100帧)

### 2. 选择合适的输出格式

| 用途 | 推荐格式 | 原因 |
|------|---------|------|
| Web展示 | **GIF** | 浏览器原生支持，无需插件 |
| PPT演示 | **AVI** → FFmpeg转MP4 | 高质量，PPT支持MP4 |
| 论文插图 | **GIF** (高分辨率) | 易于插入文档 |
| 存档备份 | **AVI** | 无损压缩，方便后期处理 |
| 邮件分享 | **GIF** (低分辨率) | 文件小，易传输 |

### 3. 组织d3plot文件

建议目录结构：
```
Simulations/
├── case1_v1600_by1000_ty800/
│   ├── bullet_sim.k
│   ├── d3plot
│   ├── animation_iso.gif
│   └── animation_front.gif
├── case2_v2500_by1500_ty800/
│   ├── bullet_sim.k
│   ├── d3plot
│   └── ...
```

### 4. 定期清理文件

动画文件会占用大量磁盘空间，建议：
- 完成分析后，下载需要的动画
- 定期清理 `animation_output_dir` 目录
- 保留重要案例的动画文件

**批量删除CFILE脚本**:
```cmd
cd D:\Simulations\animations
del cfile_*.cfile
```

---

## 📞 技术支持

### 日志查看

**后端控制台**：
```
[INFO] 动画生成器初始化成功
[INFO] 任务 a1b2c3d4 已创建并开始处理
[INFO] CFILE脚本已生成: D:\...\cfile_a1b2c3d4.cfile
[INFO] 开始调用LS-PrePost渲染动画...
[SUCCESS] 任务 a1b2c3d4 完成: D:\...\animation_..._.gif
```

**LS-PrePost日志** (`lspost.msg`):
```
Reading d3plot file...
Frame 1 / 100
Frame 50 / 100
Frame 100 / 100
Writing GIF file...
Finished!
```

### 错误排查

如果遇到问题，检查以下内容：
1. ✅ LS-PrePost 4.8 是否正确安装
2. ✅ `config.json` 路径是否指向正确的可执行文件
3. ✅ d3plot文件是否有效（可用LS-PrePost手动打开测试）
4. ✅ 服务器权限是否足够（可读取d3plot，可写入输出目录）
5. ✅ 磁盘空间是否充足（AVI文件可能很大）

### 报告Bug

如发现问题，请提供：
- 后端控制台日志输出
- `lspost.msg` 文件内容
- 任务ID和错误信息
- d3plot文件大小和时间步数
- LS-PrePost版本 (4.8 x64)

---

## 🎓 示例案例

### 案例1：标准穿甲仿真GIF动画

**场景**：典型穿甲测试，需要生成Web展示动画

**参数**：
- d3plot路径：`D:\Simulations\standard_case\d3plot`
- 视角：等角视图
- 云图变量：应力
- 分辨率：1920x1080
- **输出格式：GIF**
- 起始帧：1
- 结束帧：留空 (自动检测)
- 显示选项：全选

**预期结果**：
- 渲染时间：2-3分钟
- 文件大小：15 MB
- 可直接在浏览器中播放

### 案例2：高质量AVI存档

**场景**：需要高质量动画用于后期编辑和PPT演示

**参数**：
- d3plot路径：`D:\Simulations\high_quality\d3plot`
- 视角：等角视图
- 云图变量：应力
- 分辨率：1920x1080
- **输出格式：AVI**
- 起始帧：1
- 结束帧：留空

**后期处理**：
```bash
# 转换为MP4用于PPT
ffmpeg -i animation.avi -c:v libx264 -crf 23 -preset medium animation.mp4

# 如需4K分辨率
ffmpeg -i animation.avi -vf scale=3840:2160 -c:v libx264 -crf 23 animation_4k.mp4
```

### 案例3：多视角对比研究

**场景**：需要从不同角度分析穿甲过程

**任务创建**（并行执行）：
1. 任务1：等角视图 + 应力 + GIF
2. 任务2：正视图 + 应力 + GIF
3. 任务3：俯视图 + 位移 + GIF

**后期处理 - 拼接三个GIF**:
```bash
# 使用ImageMagick拼接GIF
convert animation_iso.gif animation_front.gif animation_top.gif +append combined.gif

# 或使用FFmpeg拼接为MP4
ffmpeg -i animation_iso.gif -i animation_front.gif -i animation_top.gif \
  -filter_complex "[0:v][1:v][2:v]hstack=inputs=3[v]" \
  -map "[v]" output_combined.mp4
```

---

## 🔄 从旧版本迁移

如果之前使用的是基于LS-PrePost 4.9+的配置：

### 配置文件更新

**旧版 (4.9+)**:
```json
{
  "lsprepost_executable": "C:\\Program Files\\LSTC\\LS-PrePost 4.9\\lsprepost4.9_x64.exe"
}
```

**新版 (4.8)**:
```json
{
  "lsprepost_executable": "E:\\ansys22r2\\ANSYS Inc\\v222\\ansys\\bin\\winx64\\lsprepost48\\lsprepost4.8_x64.exe"
}
```

### 主要变化

1. **输出格式**: MP4 → GIF/AVI/MPEG
2. **默认格式**: GIF (Web友好)
3. **帧率控制**: 移除FPS参数，改用帧范围
4. **新增选项**: 显示部件/图例/坐标轴

---

**版本历史**：
- v2.0 (2025-11-17) - LS-PrePost 4.8兼容更新
  - 移除MP4支持，改用GIF/AVI/MPEG
  - 新增帧范围控制
  - 新增显示选项
  - 更新CFILE生成逻辑
- v1.0 (2025-11-07) - 初始版本

**未来计划**：
- FFmpeg集成 (自动转换为MP4)
- GIF优化 (自动调用gifsicle)
- 批量任务模板
- 进度实时反馈
