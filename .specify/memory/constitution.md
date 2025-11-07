<!--
Sync Impact Report
==================
Version: 0.0.0 → 1.0.0 (INITIAL)
Rationale: Initial constitution establishment for Bullet Penetration Simulation project

Principles Established:
- I. Good Taste (消除特殊情况优先)
- II. Performance First (性能为王)
- III. Simplicity Obsession (简洁执念)
- IV. Backward Compatibility (向后兼容铁律)
- V. Critical Review (批判性审查)

Additional Sections:
- Code Quality Standards (NEW)
- Performance Standards (NEW)

Templates Impact:
✅ plan-template.md - Constitution Check section updated
✅ spec-template.md - Performance requirements alignment verified
✅ tasks-template.md - Quality gates alignment verified

Follow-up TODOs:
- None (all placeholders filled)
-->

# Bullet Penetration Simulation Constitution

## Core Principles

### I. Good Taste（优雅设计优先）

**代码必须消除特殊情况，而不是增加条件分支。**

- 优先重新设计数据结构来消除 if/else 分支，而非添加更多判断
- 边界条件应该融入正常流程，不应该成为"特殊处理"
- 如果代码需要超过3层缩进，必须重新设计
- 函数必须短小精悍，只做一件事并做好

**理由**：好的设计是看不见的。当你需要为边界情况写特殊代码时，说明数据结构设计错了。

### II. Performance First（性能为王）

**物理模拟的性能直接决定用户体验，性能优化是工程决策的第一优先级。**

- 所有算法必须明确标注时间和空间复杂度
- 关键路径代码（弹道计算、碰撞检测）必须进行性能测试和 profiling
- 拒绝"过早优化"的借口——对于实时物理模拟，性能从第一行代码就是必须考虑的
- 内存分配必须可控：避免不必要的拷贝、临时对象、动态分配

**理由**：理论和实践有时会冲突。实践永远获胜。用户不会因为你的代码"理论上更优雅"而接受卡顿的模拟。

### III. Simplicity Obsession（简洁执念）

**复杂性是万恶之源。能用3行解决的问题绝不写10行。**

- 遵循 KISS 原则：Keep It Simple, Stupid
- 遵循 YAGNI 原则：You Aren't Gonna Need It——拒绝假想威胁的过度设计
- 遵循 DRY 原则：Don't Repeat Yourself——但不要为了 DRY 而创建无意义的抽象
- 命名必须清晰直接：`bullet_velocity` 而非 `bv` 或 `bulletVelocityInMetersPerSecond`

**理由**：代码是写给人看的，其次才是给机器执行的。简洁的代码更容易理解、调试、维护。

### IV. Backward Compatibility（向后兼容铁律）

**Never break userspace. 绝不破坏现有功能。**

- 任何导致现有模拟结果改变的代码修改都必须视为 breaking change
- API 变更必须保持向后兼容，或提供清晰的迁移路径
- 配置文件格式变更必须支持旧版本自动转换
- 数据文件格式必须版本化，并支持向前兼容读取

**理由**：用户的工作基于你的代码。破坏他们的工作流是不可接受的，无论你的新设计有多"理论正确"。

### V. Critical Review（批判性审查）

**每次代码审查必须犀利指出潜在问题，提供框架外的替代方案。**

- 审查者必须质疑设计决策的必要性：这是真问题还是臆想出来的？
- 审查者必须寻找更简单的方法：有没有更直接的解决方案？
- 审查者必须评估破坏性：这会影响什么现有功能？
- 批评针对技术问题，不针对个人——但绝不为了"友善"而模糊技术判断
- 如果代码质量不达标，直接拒绝，并说明为什么是垃圾

**理由**："好程序员担心代码。优秀程序员担心数据结构。"审查必须深入本质，而不是表面的代码风格。

## Code Quality Standards

### Mandatory Gates

**所有代码提交前必须通过：**

1. **数据结构分析**
   - 核心数据是什么？它们的关系如何？
   - 有没有不必要的数据复制或转换？
   - 能否通过更好的数据结构消除复杂性？

2. **复杂度审查**
   - 函数嵌套不超过3层
   - 单个函数不超过50行（物理计算除外，但必须注释）
   - 消除所有可以消除的特殊情况

3. **性能验证**
   - 关键路径必须有性能测试
   - 算法复杂度必须在代码注释中声明
   - 内存分配模式必须经过审查

### Code Style

- **编码**：UTF-8（支持中文注释）
- **换行**：CRLF（Windows 环境）
- **语言**：代码用英文，注释和文档可用中文
- **配置优先**：所有可配置项使用配置文件，禁止硬编码

## Performance Standards

### Target Metrics

**必须达到的性能指标：**

- 弹道计算：单次迭代 < 1ms（标准工况）
- 碰撞检测：< 100μs per check（简单几何体）
- 帧率目标：≥60 FPS（实时可视化模式）
- 内存占用：< 500MB（标准场景）

### Profiling Requirements

- 每个性能敏感模块必须有 benchmark 测试
- 每次优化必须附带 profiling 数据对比
- 性能退化（>10%）必须在 code review 中明确说明理由

## Documentation Standards

### Mandatory Documentation

**文档必须与代码同步，不允许滞后。**

- 所有模块必须有清晰的 API 文档
- 复杂算法必须有数学推导或参考文献
- 配置选项必须有详细说明和默认值
- 文档位于 `docs/` 目录下

### Documentation Structure

```
docs/
├── design/          # 详细设计文档（架构、算法）
├── api/             # API 参考文档
├── guides/          # 用户指南和教程
└── performance/     # 性能分析和优化记录
```

## Governance

### Amendment Process

1. **提案**：任何人可以提出宪章修订建议
2. **讨论**：技术团队评估影响和必要性
3. **投票**：核心维护者 2/3 多数通过
4. **迁移**：更新所有依赖文档和模板
5. **版本**：按语义化版本递增

### Versioning Policy

- **MAJOR**：移除或重新定义核心原则（破坏性变更）
- **MINOR**：新增原则或实质性扩展
- **PATCH**：澄清、措辞、错别字修复

### Compliance Review

- 所有 Pull Request 必须验证宪章合规性
- 违反核心原则的代码必须提供充分理由或重新设计
- 代码审查者有权基于宪章原则拒绝 PR

### Runtime Development Guidance

日常开发遵循本宪章精神。对于工具使用、工作流程等运行时指导，参考项目根目录的 `README.md` 和 `.claude/CLAUDE.md`。

---

**Version**: 1.0.0 | **Ratified**: 2025-10-14 | **Last Amended**: 2025-10-14
