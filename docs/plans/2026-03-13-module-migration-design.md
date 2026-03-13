# 旧模块迁移到新插件架构 — 设计文档

**目标**：将 8 个旧扁平模块（共 5,277 行）的业务逻辑完整迁移到新微内核插件架构中，统一到 SQLite + 事件总线，然后删除旧模块。

**策略**：重写优化 — 趁机重构，统一到新架构。按依赖层次分 3 批、8 步执行。

**等价性要求**：迁移后全量测试（544/545）通过，不改变外部 API 行为。

---

## 分批策略

### 第 1 批：基础设施层（被其他所有模块依赖）

#### Step 1: storage.py (77行) → plugins/storage/file_ops.py

- 搬入 5 个文件 I/O 工具函数：`atomic_write_text`, `atomic_write_json`, `locked_read_json`, `locked_update_json`, `locked_append_text`
- 旧 `storage.py` 改为 re-export 兼容层
- 12 个消费者无需立即修改

#### Step 2: research_events.py (554行) → kernel/events.py

- 搬入 34 个事件 dataclass + `ResearchEvent` TypeAlias + `EventHandler` 类型
- 搬入 `PhaseName`, `LogLevel` 字面量类型
- 搬入 `event_name()`, `event_phase()`, `event_level()`, `event_payload()` 工具函数
- 旧 `research_events.py` 改为 re-export 兼容层
- 9 个消费者无需立即修改
- 与内核 `Event` 通用事件并存，由 `event_adapter.py` 桥接

### 第 2 批：数据/资源层（被业务逻辑依赖）

#### Step 3: research_graph.py (1329行) → plugins/graph/

- 将 `ResearchGraphStore` 完整搬入 `plugins/graph/legacy_store.py`
- 9 组常量搬入 `plugins/graph/constants.py`
- `_default_graph()` 工厂函数一并迁移
- 现有 SQLite-backed `GraphStore` 保留（未来替代方案）
- 6 个消费者通过兼容层过渡

#### Step 4: gpu_manager.py (541行) → plugins/execution/gpu.py

- 将完整 `GPUManager` 类搬入（预留/释放/内存打包/远程支持）
- 现有 `GPUAllocator` 保留作为简化接口
- `parse_visible_cuda_devices()` 一并迁移
- 6 个消费者通过兼容层过渡

#### Step 5: worktree.py (402行) → plugins/execution/worktree.py

- 搬入全部功能：overlay 同步、研究目录符号链接、git exclude 模式、artifact 清理、manifest 生成
- 新增 `WorktreeError`, `worktrees_root()`
- 现有简化接口保留
- 2 个消费者通过兼容层过渡

#### Step 6: parallel_runtime.py (236行) → plugins/execution/parallel.py

- 搬入全部 6 个函数 + `ParallelRuntimeProfile`
- 现有 `ParallelBatchConfig`/`BatchResult` 保留
- 4 个消费者通过兼容层过渡

### 第 3 批：业务逻辑层（最顶层）

#### Step 7: bootstrap.py (953行) → plugins/bootstrap/

- `detection.py` 扩展：合入 `detect_repo_profile()`, `resolve_python_environment()`, conda 检测
- `prepare.py` 扩展：合入 `resolve_bootstrap_plan()`, `run_bootstrap_prepare()`, prepare step 执行
- 新增 `state.py`：bootstrap 状态管理
- 新增 `formatting.py`：`format_bootstrap_dry_run()`, `command_env_for_python()`
- 7 个消费者通过兼容层过渡

#### Step 8: research_loop.py (1185行) → plugins/orchestrator/loop.py

- `ResearchLoop` 类完整搬入 `plugins/orchestrator/loop.py`
- 辅助函数搬入 `plugins/orchestrator/helpers.py`
- 内部导入更新指向新的插件位置
- 3 个消费者通过兼容层过渡

---

## 通用迁移模式（每个 Step 遵循）

1. 将代码搬入新插件目录（保持 API 不变）
2. 旧文件改为 re-export 兼容层：`from open_researcher.plugins.xxx import *`
3. 运行全量测试确保 544/545 通过
4. 逐步更新所有消费者的 import 路径指向新位置
5. 删除旧的兼容层文件
6. 再次运行全量测试

---

## 风险控制

- 每步迁移后运行全量测试
- re-export 兼容层确保向后兼容
- 旧代码删除前必须确认所有 import 已更新
- research_loop.py 和 bootstrap.py 是最复杂的，放在最后处理
