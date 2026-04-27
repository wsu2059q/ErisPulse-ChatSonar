<div align="center">

# ChatSonar · 消息声呐

**可视化群聊社交距离与岛屿群落**

Visualize Group Chat Social Distance & Island Communities

[![Python](https://img.shields.io/badge/Python-≥3.10-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![ErisPulse](https://img.shields.io/badge/ErisPulse-Module-purple.svg)](https://github.com/ErisPulse)

</div>

---

## 功能特性 / Features

| 功能 | 说明 |
|------|------|
| 群地图 / Sonar Map | 基于多维距离矩阵，通过 MDS 降维生成 2D 社交声呐图，含密度热力场与岛屿连线 |
| 亲密度 / Intimacy | 五维雷达图分析两人关系：时段重叠、表情相似、词汇相似、直接互动、共现频率 |
| 小圈子 / Islands | Union-Find 自动检测群内社交岛屿群落，标注内部距离与成员列表 |
| 另一个我 / Parallel Self | 跨群寻找与你行为最相似但从未互动过的「平行宇宙」用户 |
| 我的位置 / Radar | 个人社交雷达图，按内圈 / 中圈 / 外圈 / 暗区分层展示与所有人的距离 |
| 隐私保护 / Privacy | 用户可随时退出数据采集并一键删除所有个人特征数据 |

## 图表预览 / Preview

| 声呐图 | 亲密度雷达 |
|--------|-----------|
| 群社交距离全局视图，岛屿连线 + 密度热力场 | 两人五维相似度雷达分析 |
| 节点大小 = 消息量，颜色 = 岛屿归属 | 每个维度独立打分 + 百分比标注 |

| 个人雷达 | 岛屿群落 |
|---------|---------|
| 以自己为中心的社交距离分布 | 自动检测亲密小圈子 |

## 安装 / Installation

```bash
# 通过 ErisPulse 包管理器安装
epsdk install ChatSonar

# 或通过 pip
pip install ErisPulse-ChatSonar
```

### 依赖 / Dependencies

- **matplotlib** — 图表渲染
- **numpy**  — 矩阵运算与 MDS 降维
- **emoji**  — 更精确的 Emoji 提取

## 使用 / Usage

模块加载后自动监听群消息，无需额外配置。用户通过斜杠命令交互：

### 命令列表 / Commands

| 命令 | 说明 |
|------|------|
| `/群地图` | 生成全群社交关系声呐图 |
| `/亲密度 @某人` | 查看你与某人的五维亲密度分析 |
| `/小圈子` | 查看群里的社交岛屿分布 |
| `/另一个我` | 找到和你最像但从未互动过的人 |
| `/我的位置` | 查看你在群社交圈中的位置 |
| `/别盯着我` | 停止收集数据并删除已有记录 |
| `/可以盯我了` | 重新加入声呐监测 |

### HTTP API

模块注册以下 HTTP 端点：

| 端点 | 说明 |
|------|------|
| `GET /ChatSonar/` | 模块信息页 |
| `GET /ChatSonar/scopes` | 所有监测范围列表 |
| `GET /ChatSonar/data?scope=<scope>` | JSON 距离矩阵 |
| `GET /ChatSonar/islands?scope=<scope>` | 岛屿群落数据 |

## 配置 / Configuration

首次加载自动生成默认配置，可在 ErisPulse 配置中修改 `ChatSonar` 节：

### TOML 配置示例

```toml
[ChatSonar]
min_messages = 10
update_interval = 3600
distance_threshold = 0.6
cooccur_window = 300
utc_offset = 8
density_bandwidth = 0.15
radar_distance_scale = 1.2
radar_max_radius = 1.1

[ChatSonar.weights]
timing = 0.20
emoji = 0.15
vocab = 0.20
interaction = 0.30
cooccurrence = 0.15
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_messages` | `10` | 用户最低消息数门槛（低于此数不参与计算） |
| `update_interval` | `3600` | 距离矩阵缓存刷新间隔（秒） |
| `distance_threshold` | `0.6` | 岛屿检测距离阈值（越小越严格） |
| `cooccur_window` | `300` | 共现判定时间窗口（秒） |
| `utc_offset` | `8` | UTC 偏移量（时区） |
| `density_bandwidth` | `0.15` | 声呐图密度热力场带宽 |
| `radar_distance_scale` | `1.2` | 个人雷达距离缩放因子 |
| `radar_max_radius` | `1.1` | 个人雷达最大半径 |
| `weights.*` | 见上表 | 五维距离权重（自动归一化） |

## 架构 / Architecture

```
ChatSonar/
├── Core.py          模块入口，注册事件处理器与路由
├── Collector.py     消息采集器，提取时段/表情/词汇/互动/共现特征
├── Analyzer.py      分析引擎，计算距离矩阵、岛屿检测、平行匹配
├── Visualizer.py    可视化引擎，生成声呐图/雷达图/热力图
├── Commands.py      斜杠命令注册与响应处理
└── fonts/           内嵌思源黑体，确保中文渲染
```

### 分析维度 / Analysis Dimensions

| 维度 | 权重 | 说明 |
|------|------|------|
| **Timing** 时段 | 20% | 24 小时活跃时段余弦相似度 |
| **Emoji** 表情 | 15% | 表情使用频率余弦相似度 |
| **Vocab** 词汇 | 20% | 中文 bigram + 英文词频余弦相似度 |
| **Interaction** 互动 | 30% | @ 回复 / 引用的双向互动强度 |
| **Co-occurrence** 共现 | 15% | 同一时间窗口内同时在线频率 |

距离公式：`distance = Σ(normalized_weight × (1 - score))`，值越小表示越亲密。

## 许可证 / License

- 代码部分：[Apache License 2.0](LICENSE)
- 内嵌字体 [思源黑体 / Source Han Sans SC]：[SIL Open Font License 1.1](LICENSE)（字体版权归 Adobe 所有）

---

## 字体版权声明 / Font License Notice

本项目内嵌的 `ChatSonar/fonts/SourceHanSansSC-Regular.otf` 为 **思源黑体（Source Han Sans SC）**，其版权归 **Adobe Inc.** 所有，并按照 **SIL Open Font License 1.1** 授权。

- 字体独立于本项目的代码许可证（Apache-2.0）之外
- 字体的使用与分发需遵守 OFL 1.1 条款
- 完整的字体许可证内容见仓库根目录 `LICENSE` 文件（该文件同时包含 Apache-2.0 代码许可证与 OFL 1.1 字体许可证的副本）

We respect font copyrights. `Source Han Sans SC` is licensed under the SIL Open Font License 1.1 by Adobe Inc.

