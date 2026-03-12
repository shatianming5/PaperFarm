# 贡献指南（PaperFarm）

[English](CONTRIBUTING.md) · [简体中文](CONTRIBUTING.zh-CN.md)

感谢你参与 PaperFarm 的建设。

## 开始之前

- 对于非小改动，建议 **先 Issue、后 PR**。
- 每个 PR 保持单一目标，避免把无关重构混进来。
- 只要行为有变化，请同时更新测试与文档。

## 开发环境

```bash
git clone https://github.com/shatianming5/PaperFarm.git
cd PaperFarm
python -m venv .venv
source .venv/bin/activate
make dev
```

## 本地校验

```bash
make lint
make test
make test-cov
make package-check
make ci
```

提交 PR 前至少应通过 `make ci`。

## PR 自检清单

- 标题与描述清晰（改了什么、为什么）
- 非小改动关联对应 Issue
- 行为变化有测试覆盖
- UX/CLI/配置/契约变化同步更新文档
- 同一 PR 不混入无关重构

## 文档策略

核心对外文档应保持中英双语：

- `README.md` / `README.zh-CN.md`
- `CONTRIBUTING.md` / `CONTRIBUTING.zh-CN.md`
- `docs/README.md` / `docs/README.zh-CN.md`

`docs/plans/` 下文档属于历史归档，不作为当前对外契约。

## 代码风格

项目使用 [ruff](https://github.com/astral-sh/ruff) 做 lint/format。

```bash
make lint
make format
```

## 新增 Agent 适配器

1. 新建 `src/open_researcher/agents/<agent>.py`
2. 实现 `AgentAdapter`（见 `src/open_researcher/agents/base.py`）
3. 使用 `@register` 注册
4. 在 `tests/test_agents.py` 增加测试
5. 同步更新 `README.md` 与 `README.zh-CN.md` 中的 agent 说明
