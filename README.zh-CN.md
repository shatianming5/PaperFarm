<div align="center">

# 🧑‍🌾 PaperFarm：种下想法，自动实验，收获结果

[**English**](README.md) · [**简体中文**](README.zh-CN.md)

</div>

> CLI 入口命令：`open-researcher`（兼容别名：`PaperFarm`）

## 项目简介

PaperFarm 是一个面向任意 Git 仓库的自动化研究/实验框架。它会在仓库内维护 `.research/` 运行目录，通过 `Scout -> Manager -> Critic -> Experiment` 循环持续提出假设、执行实验、记录证据并回写结论。

## 快速开始

```bash
pip install PaperFarm

cd your-project
open-researcher run
# 或者使用等价别名
PaperFarm run
```

`run` 会自动进入以下流程：

1. `Scout`：分析代码、整理相关工作、定义评估方案
2. `Prepare`：自动解析并执行 install/data/smoke 准备步骤
3. `Review`：在 TUI 中确认研究方向（headless 模式自动确认）
4. `Experiment`：进入 research-v1 循环并持续迭代

如需只查看将要执行的流程：

```bash
open-researcher run --dry-run
open-researcher doctor
```

## 无界面模式（Headless）

```bash
open-researcher run --mode headless --goal "reduce val_loss below 0.3" --max-experiments 20
```

Headless 会输出 JSON Lines，并写入 `.research/events.jsonl`。交互模式与 headless 共享同一条 canonical 事件流。

## 常用命令

```bash
open-researcher init
open-researcher run --agent codex
open-researcher run --workers 4
open-researcher status --sparkline
open-researcher results --chart primary
open-researcher export
open-researcher doctor
```

## 安装与开发

```bash
git clone https://github.com/shatianming5/PaperFarm.git
cd PaperFarm
python -m venv .venv
source .venv/bin/activate
make dev
make ci
```

## 文档导航

- [README.md](README.md)（English）
- [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)
- [docs/README.md](docs/README.md)（English 文档索引）
- [docs/README.zh-CN.md](docs/README.zh-CN.md)（中文文档索引）

## 贡献

欢迎贡献，推荐流程：

1. 先开 Issue 讨论方向
2. 在独立分支开发并补充测试/文档
3. 发起 PR，并说明行为变化与验证方式

详细规范见 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。

## 许可证

本项目使用 [MIT License](LICENSE)。
