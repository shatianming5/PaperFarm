# Open Researcher 微内核架构重构设计

> 日期：2026-03-13
> 状态：已批准
> 范围：全面重构，允许破坏性变更

## 1. 动机与目标

### 当前痛点
- **模块过大**：worker.py (1370行), research_graph.py (1329行), research_loop.py (1185行) 等职责过多
- **扁平结构**：55+ .py 文件平铺在同一目录，导航困难
- **耦合度高**：research_events 被 19 个模块导入，改一处影响全局
- **扩展性不足**：添加新 Agent、新协议、新调度策略时修改点过多
- **状态分散**：.research/ 下 10+ 种 JSON/TSV/YAML 文件，无统一管理

### 目标
1. 清晰分层，每个模块职责单一
2. 插件化架构，新功能零改动核心代码
3. 统一事件系统，降低模块间耦合
4. SQLite 统一状态存储
5. 支持未来多研究协议扩展
6. 提升可维护性为首要目标

---

## 2. 架构概览

### 微内核 + 事件溯源

```
┌──────────────────────────────────────────────────────────┐
│                        Kernel                             │
│   ┌────────────┐  ┌────────────┐  ┌───────────────────┐  │
│   │  EventBus  │  │  Registry  │  │  EventStore       │  │
│   │  (async)   │  │  (plugins) │  │  (SQLite-backed)  │  │
│   └────────────┘  └────────────┘  └───────────────────┘  │
└──────────────────────────────────────────────────────────┘
         ↕                ↕                   ↕
┌─────────────────────────────────────────────────────────┐
│                      Plugins                             │
│  orchestrator | agents | execution | graph | scheduler   │
│  storage | bootstrap | tui | cli                         │
└─────────────────────────────────────────────────────────┘
```

**核心原则：**
- 内核尽可能小（~500 行），只做事件路由 + 插件生命周期 + 持久化
- 所有业务逻辑在插件中实现
- 插件间只通过事件总线通信
- 插件可通过 `kernel.get_plugin()` 获取其他插件的公开 API

---

## 3. 事件模型

### 通用事件

```python
@dataclass(frozen=True, slots=True)
class Event:
    type: str                    # 命名空间化: "experiment.started", "scout.completed"
    payload: dict[str, Any]      # 自由结构
    ts: float                    # 时间戳
    source: str = ""             # 发出事件的插件名
    correlation_id: str = ""     # 因果链追踪
```

设计决策：
- 不使用 35+ 个类型化事件类，改为单一 Event + type 字符串
- 用 `.` 分隔的命名空间约定（如 `experiment.*`, `scout.*`）
- 支持通配符订阅（如 `on("experiment.*", handler)`）
- payload 类型安全由各插件内部用 TypedDict 或 dataclass 保证

### 事件总线（异步）

```python
class EventBus:
    async def emit(self, event: Event) -> None:
        """持久化到 EventStore → 异步分发给所有匹配的 handler"""
        await self._store.append(event)
        asyncio.create_task(self._dispatch(event))

    def on(self, event_type: str, handler: Callable) -> None:
        """注册监听器，支持通配符 'experiment.*'"""

    def off(self, event_type: str, handler: Callable) -> None:
        """移除监听器"""
```

### 事件存储（SQLite）

```sql
CREATE TABLE events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    type      TEXT NOT NULL,
    payload   TEXT NOT NULL,  -- JSON
    ts        REAL NOT NULL,
    source    TEXT,
    corr_id   TEXT,
    created   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_events_type ON events(type);
CREATE INDEX idx_events_ts ON events(ts);
```

---

## 4. 插件协议

```python
class Plugin(Protocol):
    name: str
    dependencies: list[str]

    async def start(self, kernel: Kernel) -> None:
        """初始化：注册事件监听器、申请资源"""

    async def stop(self) -> None:
        """清理：释放资源、取消注册"""
```

### 插件发现

通过 pyproject.toml entry_points 自动发现：

```toml
[project.entry-points."open_researcher.plugins"]
orchestrator = "open_researcher.plugins.orchestrator:OrchestratorPlugin"
agents       = "open_researcher.plugins.agents:AgentsPlugin"
execution    = "open_researcher.plugins.execution:ExecutionPlugin"
graph        = "open_researcher.plugins.graph:GraphPlugin"
scheduler    = "open_researcher.plugins.scheduler:SchedulerPlugin"
storage      = "open_researcher.plugins.storage:StoragePlugin"
bootstrap    = "open_researcher.plugins.bootstrap:BootstrapPlugin"
tui          = "open_researcher.plugins.tui:TuiPlugin"
cli          = "open_researcher.plugins.cli:CliPlugin"
```

### 依赖顺序

启动顺序按 `dependencies` 拓扑排序：
```
storage → graph → scheduler → execution → agents → orchestrator → bootstrap → cli/tui
```

---

## 5. 目录结构

```
src/open_researcher/
├── kernel/                    # 微内核 (~500 行)
│   ├── __init__.py           # 导出 Kernel, Event, EventBus
│   ├── bus.py                # EventBus 实现
│   ├── store.py              # EventStore (SQLite)
│   ├── plugin.py             # Plugin protocol + Registry
│   └── config.py             # 最小化配置加载
│
├── plugins/                   # 所有业务逻辑
│   ├── orchestrator/          # 核心研究循环 (~600 行)
│   │   ├── __init__.py       # OrchestratorPlugin
│   │   ├── loop.py           # Scout→Manager→Critic→Experiment
│   │   ├── phases.py         # 各阶段独立逻辑
│   │   └── safety.py         # crash counter, git safety
│   │
│   ├── agents/                # Agent 适配器 (~500 行)
│   │   ├── __init__.py       # AgentsPlugin + AgentAdapter protocol
│   │   ├── base.py           # 公共基类
│   │   ├── claude_code.py
│   │   ├── codex.py
│   │   ├── aider.py
│   │   ├── opencode.py
│   │   ├── kimi.py
│   │   └── gemini.py
│   │
│   ├── execution/             # 并行执行 (~800 行)
│   │   ├── __init__.py       # ExecutionPlugin
│   │   ├── worker.py         # Worker 生命周期
│   │   ├── parallel.py       # 批处理运行器
│   │   ├── worktree.py       # Git worktree 隔离
│   │   └── gpu.py            # GPU 管理 (合并 gpu_manager + worker_plugins GPU 部分)
│   │
│   ├── graph/                 # 研究图 (~500 行)
│   │   ├── __init__.py       # GraphPlugin
│   │   ├── store.py          # 图存储 (SQLite 表)
│   │   ├── queries.py        # 图查询：家族检索、前沿排序
│   │   └── context.py        # 上下文过滤与 token 限制
│   │
│   ├── scheduler/             # 调度与记忆 (~500 行)
│   │   ├── __init__.py       # SchedulerPlugin
│   │   ├── resource.py       # 资源调度
│   │   ├── memory.py         # 研究记忆
│   │   ├── memory_policy.py  # 记忆策略
│   │   └── idea_pool.py      # 想法池
│   │
│   ├── storage/               # 持久化 (~300 行)
│   │   ├── __init__.py       # StoragePlugin
│   │   ├── db.py             # SQLite 连接管理
│   │   ├── migrations.py     # Schema 版本迁移
│   │   └── models.py         # 表定义
│   │
│   ├── bootstrap/             # 项目引导 (~500 行)
│   │   ├── __init__.py       # BootstrapPlugin
│   │   ├── detection.py      # 仓库类型检测
│   │   ├── prepare.py        # 准备命令执行
│   │   └── templates/        # Jinja2 模板
│   │
│   ├── tui/                   # TUI 展示 (~800 行)
│   │   ├── __init__.py       # TuiPlugin
│   │   ├── app.py            # Textual 主应用
│   │   ├── view_model.py     # 事件→UI 状态投影
│   │   ├── panels.py         # 信息面板
│   │   ├── tables.py         # 表格组件
│   │   └── modals.py         # 模态框
│   │
│   └── cli/                   # CLI 入口 (~400 行)
│       ├── __init__.py       # CliPlugin
│       ├── main.py           # Typer app 定义
│       ├── run.py            # run/start 命令
│       ├── status.py         # status 命令
│       ├── results.py        # results 命令
│       ├── doctor.py         # doctor 命令
│       └── export.py         # export 命令
│
├── __init__.py
└── __main__.py               # python -m open_researcher
```

**预计总行数：** ~5000 行 (内核 500 + 插件 ~4500)，从 36,776 行大幅精简
（注：精简来自去除重复代码、合并相似逻辑、简化事件系统）

---

## 6. SQLite 状态模型

### 数据库位置

`.research/state.db` — 单文件，便于备份和迁移

### 核心表

```sql
-- 实验结果 (原 results.tsv)
CREATE TABLE experiments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL,  -- pending/running/success/failed
    hypothesis  TEXT,
    metrics     TEXT,           -- JSON
    started_at  REAL,
    finished_at REAL,
    worker_id   TEXT,
    metadata    TEXT            -- JSON
);

-- 假设 (原 research_graph.json 的 hypotheses 部分)
CREATE TABLE hypotheses (
    id          TEXT PRIMARY KEY,
    claim       TEXT NOT NULL,
    status      TEXT NOT NULL,  -- proposed/testing/supported/refuted
    parent_id   TEXT,
    created_at  REAL,
    metadata    TEXT
);

-- 证据 (原 research_graph.json 的 evidence 部分)
CREATE TABLE evidence (
    id            TEXT PRIMARY KEY,
    hypothesis_id TEXT REFERENCES hypotheses(id),
    experiment_id INTEGER REFERENCES experiments(id),
    direction     TEXT,  -- supports/refutes/neutral
    summary       TEXT,
    created_at    REAL
);

-- 想法池 (原 idea_pool.json)
CREATE TABLE ideas (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,  -- pending/claimed/done/skipped
    priority    REAL DEFAULT 0,
    claimed_by  TEXT,
    created_at  REAL,
    metadata    TEXT
);

-- 研究记忆 (原 research_memory.json)
CREATE TABLE memory (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,  -- JSON
    updated_at  REAL
);

-- 配置快照 (原 config.yaml)
CREATE TABLE config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL  -- JSON
);

-- 控制指令 (原 control.json)
CREATE TABLE control_commands (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    command  TEXT NOT NULL,
    source   TEXT,
    reason   TEXT,
    ts       REAL
);

-- GPU 快照 (原 gpu_status.json)
CREATE TABLE gpu_snapshots (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    data     TEXT NOT NULL,  -- JSON
    ts       REAL
);

-- Bootstrap 状态 (原 bootstrap_state.json)
CREATE TABLE bootstrap_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    ts    REAL
);
```

### 迁移策略

`storage/migrations.py` 维护递增版本号，每次启动自动检查 `PRAGMA user_version` 并执行增量 DDL。

---

## 7. 数据流

```
用户 CLI 命令
    ↓
[CLI Plugin] → emit("run.requested", {goal, agent, ...})
    ↓
[Bootstrap Plugin] ← on("run.requested")
    检测仓库 → emit("bootstrap.completed") 或 emit("bootstrap.failed")
    ↓
[Orchestrator Plugin] ← on("bootstrap.completed")
    ↓
    Scout → emit("scout.completed", {ideas})
    ↓
    Manager → emit("manager.cycle", {experiments})
    ↓
    [Execution Plugin] ← on("experiment.dispatch")
        GPU 分配 → Worker 创建 → emit("experiment.started")
        Worker 完成 → emit("experiment.completed", {metrics})
    ↓
    Critic → emit("critic.reviewed", {verdicts})
    ↓
    循环或 emit("research.finished")
    ↓
[TUI Plugin] ← on("*")  监听所有事件更新 UI
[Storage Plugin] ← on("*")  事件自动持久化
```

---

## 8. 错误处理

### 异常层级

```python
class OpenResearcherError(Exception): ...
class PluginError(OpenResearcherError): ...
class StorageError(OpenResearcherError): ...
class AgentError(OpenResearcherError): ...
class BootstrapError(OpenResearcherError): ...
```

### 规则

1. 插件内部捕获异常，转化为 `error.*` 事件
2. EventBus 分发时兜底 try/except，单个 handler 失败不中断其他 handler
3. 致命错误（存储不可用、内核启动失败）直接 raise，由顶层 CLI 捕获并退出

---

## 9. 测试策略

```
tests/
├── unit/                     # 每个插件独立测试
│   ├── test_kernel/
│   ├── test_orchestrator/
│   ├── test_execution/
│   ├── test_graph/
│   ├── test_scheduler/
│   ├── test_storage/
│   ├── test_bootstrap/
│   ├── test_agents/
│   ├── test_cli/
│   └── test_tui/
├── integration/              # 多插件协作
│   ├── test_full_loop.py
│   └── test_headless.py
└── conftest.py               # 共享 fixtures: kernel(:memory:), fake_agent
```

### 原则

- 每个插件可独立实例化测试，不依赖其他插件
- 集成测试通过事件断言（验证 emit 了什么事件）
- 现有 52 个测试文件逐步迁移，保持覆盖率
- SQLite 使用 `:memory:` 避免文件 I/O

---

## 10. 事件类型约定

### 命名空间

| 前缀 | 插件 | 示例 |
|------|------|------|
| `run.*` | cli | `run.requested`, `run.finished` |
| `bootstrap.*` | bootstrap | `bootstrap.started`, `bootstrap.completed`, `bootstrap.failed` |
| `scout.*` | orchestrator | `scout.started`, `scout.completed`, `scout.failed` |
| `manager.*` | orchestrator | `manager.cycle.started`, `manager.cycle.completed` |
| `critic.*` | orchestrator | `critic.started`, `critic.reviewed` |
| `experiment.*` | execution | `experiment.dispatch`, `experiment.started`, `experiment.completed` |
| `hypothesis.*` | graph | `hypothesis.proposed`, `hypothesis.updated` |
| `evidence.*` | graph | `evidence.recorded` |
| `idea.*` | scheduler | `idea.added`, `idea.claimed`, `idea.completed` |
| `gpu.*` | execution | `gpu.allocated`, `gpu.released`, `gpu.snapshot` |
| `worker.*` | execution | `worker.started`, `worker.stopped`, `worker.crashed` |
| `memory.*` | scheduler | `memory.updated` |
| `token.*` | orchestrator | `token.updated`, `token.budget.warning`, `token.budget.exceeded` |
| `control.*` | orchestrator | `control.pause`, `control.resume`, `control.skip` |
| `error.*` | any | `error.unhandled`, `error.agent`, `error.storage` |

---

## 11. 迁移路径

### 阶段划分

1. **Phase 0**：搭建内核骨架（kernel/ 目录）
2. **Phase 1**：实现 storage 插件 + SQLite schema
3. **Phase 2**：迁移 orchestrator 插件（核心循环）
4. **Phase 3**：迁移 execution 插件（worker + GPU）
5. **Phase 4**：迁移 graph + scheduler 插件
6. **Phase 5**：迁移 agents 插件
7. **Phase 6**：迁移 bootstrap 插件
8. **Phase 7**：迁移 CLI + TUI 插件
9. **Phase 8**：删除旧代码，更新测试，清理

### 风险控制

- 每个 Phase 独立可测试
- Phase 之间通过事件接口解耦，可并行开发
- 旧代码在所有 Phase 完成前不删除
