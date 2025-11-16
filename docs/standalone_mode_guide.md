# 独立运行模式配置指南

**版本**: 1.0
**日期**: 2025-11-16
**适用系统**: LS-DYNA K文件参数化系统

---

## 什么是独立运行模式？

独立运行模式是指系统**完全脱离平台A**运行，所有功能都在本地执行，不会尝试连接或同步任务到外部平台。

### 适用场景

- ✅ 纯本地使用，不需要平台A集成
- ✅ 开发和测试环境
- ✅ 离线环境（无外网连接）
- ✅ 避免网络请求开销，提高响应速度

---

## 配置方法

### 方式1: 完全禁用平台A集成（推荐）

编辑 `backend/config.json`:

```json
{
  "platform_a": {
    "enabled": false  // ← 修改此处
  }
}
```

**效果**:
- 调度器不会启动
- 不会尝试HTTP请求到平台A
- 减少启动时间和内存占用

---

### 方式2: 设置独立模式

```json
{
  "platform_a": {
    "enabled": true,
    "mode": "standalone"  // ← 修改此处
  }
}
```

**区别**:
- 调度器仍会启动，但不同步任务
- 保留了将来切换到平台A的能力

---

## 运行模式对比

| 特性 | enabled=false | mode="standalone" | mode="hybrid" | mode="platform_a_only" |
|------|---------------|-------------------|---------------|------------------------|
| 调度器启动 | ❌ | ✅ | ✅ | ✅ |
| 独立任务 | ✅ | ✅ | ✅ | ❌ |
| 平台A任务 | ✅* | ✅* | ✅ | ✅ |
| 任务同步 | ❌ | ❌ | ✅ | ✅ |
| 启动时间 | 快 | 中 | 中 | 中 |

*虽然可以创建平台A任务，但不会被同步

---

## 验证独立模式

### 1. 检查配置文件

```bash
# Windows
type backend\config.json | findstr "enabled"
type backend\config.json | findstr "mode"

# Linux/Mac
grep "enabled" backend/config.json
grep "mode" backend/config.json
```

应该看到:
```json
"enabled": false,
"mode": "standalone",
```

---

### 2. 启动服务器并观察日志

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

**独立模式的日志特征**:
```
INFO:task_sync_scheduler:平台A集成已禁用，config.platform_a.enabled=false
INFO:task_sync_scheduler:平台A集成未启用，跳过调度器启动
```

**对比 - 平台A模式的日志**:
```
INFO:apscheduler.scheduler:Scheduler started
INFO:task_sync_scheduler:后台同步调度器已启动，同步间隔: 5秒
```

---

### 3. 运行独立模式测试

```bash
python test_standalone_mode.py
```

测试会验证：
- ✅ 独立任务创建成功
- ✅ K文件正常生成
- ✅ 调度器未启动（无同步尝试）

---

## 独立模式下的可用功能

### ✅ 正常工作的功能

1. **前端页面**:
   - `index.html` - 主页面（推荐使用）
   - `input.html` - 输入页面
   - `output.html` - 输出页面

2. **API接口**:
   - `POST /api/generate` - 生成K文件
   - `GET /api/files` - 列出生成的文件
   - `GET /api/task/{task_id}` - 查询任务详情
   - `POST /api/task/submit` - 提交任务（但不同步）

3. **数据库功能**:
   - 任务记录保存
   - 任务状态查询
   - 历史记录查看

4. **动画生成**:
   - LS-PrePost动画生成
   - 动画配置管理

### ❌ 不可用的功能

- 任务同步到平台A
- 平台A的task-insert/task-update接口调用
- 后台调度器（如果enabled=false）

---

## 常见问题

### Q1: 切换模式后需要重启服务器吗？

**A**: 是的。修改 `config.json` 后必须重启FastAPI服务器才能生效。

---

### Q2: 独立模式下创建的任务会被同步吗？

**A**: 不会。有两层保护：
1. `enabled=false` 时调度器不启动
2. 即使调度器启动，也只同步 `source='platform_a'` 的任务

---

### Q3: 如何从独立模式切换回平台A模式？

修改 `backend/config.json`:
```json
{
  "platform_a": {
    "enabled": true,
    "mode": "hybrid"  // 或 "platform_a_only"
  }
}
```

然后重启服务器。

---

### Q4: 独立模式会影响性能吗？

**A**: 独立模式性能更好：
- ✅ 减少HTTP请求开销
- ✅ 减少调度器线程占用
- ✅ 减少数据库查询（无同步扫描）

---

### Q5: 独立模式下的任务ID格式是什么？

独立任务的task_id格式：
```
standalone_{timestamp}_{uuid}
例如: standalone_20251116_193401_9414c158
```

平台A任务的task_id格式：
```
由平台A提供，通常是字母数字组合
例如: platform_a_task_001
```

---

## 最佳实践

### 1. 开发环境推荐配置

```json
{
  "platform_a": {
    "enabled": false,  // 完全禁用，减少干扰
    "mode": "standalone"
  }
}
```

### 2. 生产环境推荐配置

```json
{
  "platform_a": {
    "enabled": true,
    "mode": "hybrid"  // 灵活支持两种模式
  }
}
```

### 3. 测试环境推荐配置

```json
{
  "platform_a": {
    "enabled": true,
    "mode": "standalone"  // 可以测试调度器，但不实际同步
  }
}
```

---

## 故障排查

### 问题: 修改配置后仍然看到调度器启动

**原因**: 服务器未重启或读取了缓存的配置

**解决**:
1. 完全停止服务器（Ctrl+C）
2. 确认 `config.json` 已保存
3. 重新启动服务器

---

### 问题: 独立任务没有生成K文件

**原因**: 与平台A配置无关，可能是模板文件或参数问题

**检查**:
1. 模板文件是否存在: `templates/1.k`
2. 参数是否合法（范围验证）
3. 查看错误日志

---

## 监控和日志

### 确认独立模式的日志关键词

**启动时应该看到**:
```
[INFO] 应用启动中...
平台A集成已禁用，config.platform_a.enabled=false
平台A集成未启用，跳过调度器启动
[INFO] 应用启动完成
```

**不应该看到**:
```
Scheduler started  ← 调度器启动（说明未正确禁用）
后台同步调度器已启动 ← 同步功能启动
```

---

## 总结

### 独立模式的优势

1. ✅ **简单**: 无需配置外部平台地址
2. ✅ **快速**: 无网络请求延迟
3. ✅ **稳定**: 不受外部平台影响
4. ✅ **安全**: 不会泄露任务数据到外部

### 独立模式的限制

1. ❌ 无法与平台A集成
2. ❌ 无法使用平台A的工作流
3. ❌ 需要手动管理任务

---

**当前配置**: 独立模式（`enabled: false, mode: standalone`）
**文档版本**: 1.0
**最后更新**: 2025-11-16
