<div align="center">

<img src=".github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-ChatSonar" />

# ErisPulse-ChatSonar

**消息声呐 · Visualize group-chat social distance & island communities**

<p>
  <a href="https://pypi.org/project/ErisPulse-ChatSonar/"><img src="https://img.shields.io/pypi/v/ErisPulse-ChatSonar?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-ChatSonar/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-blue?style=for-the-badge" alt="License"></a>
  <a href="https://github.com/wsu2059q/ErisPulse-ChatSonar"><img src="https://img.shields.io/github/stars/wsu2059q/ErisPulse-ChatSonar?style=for-the-badge&logo=github&color=brightgreen" alt="Stars"></a>
  <a href="https://pepy.tech/project/ErisPulse-ChatSonar"><img src="https://img.shields.io/pepy/dt/ErisPulse-ChatSonar?style=for-the-badge&color=blue" alt="Downloads"></a>
  <a href="https://github.com/ErisPulse/ErisPulse"><img src="https://img.shields.io/badge/Powered_by-ErisPulse-FF6B9D?style=for-the-badge&logo=bookstack&logoColor=white" alt="ErisPulse"></a>
</p>

[English](#english) | [简体中文](#简体中文)

</div>

---

<a id="english"></a>

## English

A social-graph visualization module for [ErisPulse](https://github.com/ErisPulse/ErisPulse). It silently collects per-user behavioral features (active hours, emoji, vocabulary, @/reply interactions, co-occurrence), computes a multi-dimensional social distance matrix, and renders **modern card images** powered by [ErisPulse-Takumi](https://pypi.org/project/ErisPulse-Takumi/).

From v2.0 the visualization layer is rendered by Takumi (HTML + SVG), so **matplotlib / numpy are dropped** and CJK fonts work out of the box — no bundled font files, no font setup.

### Features

| Feature | Description |
|---------|-------------|
| Sonar Map | Force-directed 2D social sonar map with island coloring & member connections |
| Intimacy | 5-dimension similarity report between two users (timing / emoji / vocab / interaction / co-occurrence) |
| Islands | Union-Find detection of social circles inside a group |
| Parallel Self | Find the most similar user you have **never** interacted with, across groups |
| Personal Radar | Your social radar, layered by inner / middle / outer / dark rings |
| Privacy | Opt out of data collection anytime and wipe your profile |

### Install

```bash
epsdk install ChatSonar
# or
pip install ErisPulse-ChatSonar
```

> Requires [ErisPulse-Takumi](https://pypi.org/project/ErisPulse-Takumi/) as the render backend — declared as a dependency and pulled automatically. Verify with `epsdk install Takumi`.

### Commands

| Command | Description |
|---------|-------------|
| `/群地图` | Generate the group social sonar map |
| `/亲密度 @someone` | 5-dim intimacy report with someone |
| `/小圈子` | Show social-circle distribution |
| `/另一个我` | Find your closest non-interacting twin |
| `/我的位置` | Your position in the social graph (group) or global profile (private) |
| `/别盯着我` | Stop collecting & delete your data |
| `/可以盯我了` | Rejoin the sonar |

### HTTP API

| Endpoint | Description |
|----------|-------------|
| `GET /ChatSonar/` | Module info page |
| `GET /ChatSonar/scopes` | All monitored scopes |
| `GET /ChatSonar/data?scope=<scope>` | JSON distance matrix |
| `GET /ChatSonar/islands?scope=<scope>` | Island communities |

### Config

```toml
[ChatSonar]
min_messages = 10
update_interval = 3600
distance_threshold = 0.6
cooccur_window = 300
utc_offset = 8
radar_distance_scale = 1.2
radar_max_radius = 1.1

[ChatSonar.weights]
timing = 0.20
emoji = 0.15
vocab = 0.20
interaction = 0.30
cooccurrence = 0.15
```

| Key | Default | Description |
|-----|---------|-------------|
| `min_messages` | `10` | Min messages to participate |
| `update_interval` | `3600` | Matrix cache TTL (seconds) |
| `distance_threshold` | `0.6` | Island detection threshold (smaller = stricter) |
| `cooccur_window` | `300` | Co-occurrence time window (seconds) |
| `utc_offset` | `8` | UTC offset (timezone) |
| `radar_distance_scale` | `1.2` | Personal radar distance scale |
| `radar_max_radius` | `1.1` | Personal radar max radius |
| `weights.*` | see above | 5-dim weights (auto-normalized) |

### Analysis dimensions

| Dim | Weight | Description |
|-----|--------|-------------|
| Timing | 20% | Cosine similarity of 24h active-hour vectors |
| Emoji | 15% | Cosine similarity of emoji frequency |
| Vocab | 20% | Cosine similarity of CN-bigram + EN-word frequency |
| Interaction | 30% | Bidirectional @/reply strength |
| Co-occurrence | 15% | Same-window simultaneous-online frequency |

Distance: `distance = Σ(normalized_weight × (1 − score))` — smaller means closer.

---

<a id="简体中文"></a>

## 简体中文

[ErisPulse](https://github.com/ErisPulse/ErisPulse) 的社交关系可视化模块。后台静默采集每位用户的行为特征（活跃时段、表情、词汇、@/回复互动、共现），计算多维社交距离矩阵，并由 [ErisPulse-Takumi](https://pypi.org/project/ErisPulse-Takumi/) 渲染出**现代化卡片图片**。

从 v2.0 起可视化层交由 Takumi 渲染（HTML + SVG），**移除 matplotlib / numpy**，中英文字体开箱即用 —— 不再内嵌字体文件，无需配置。

### 功能特性

| 功能 | 说明 |
|------|------|
| 群地图 / Sonar Map | 力导向布局生成 2D 社交声呐图，岛屿着色 + 成员连线 |
| 亲密度 / Intimacy | 五维相似度分析两人关系：时段 / 表情 / 词汇 / 直接互动 / 共现 |
| 小圈子 / Islands | Union-Find 自动检测群内社交圈 |
| 另一个我 / Parallel Self | 跨群寻找与你最像但**从未互动过**的人 |
| 我的位置 / Radar | 个人社交雷达图，按内圈 / 中圈 / 外圈 / 暗区分层 |
| 隐私保护 / Privacy | 随时退出数据采集并一键删除个人特征数据 |

### 安装

```bash
epsdk install ChatSonar
# 或
pip install ErisPulse-ChatSonar
```

> 需要安装 [ErisPulse-Takumi](https://pypi.org/project/ErisPulse-Takumi/) 作为渲染后端 —— 已在依赖中声明，安装时会自动拉取。可用 `epsdk install Takumi` 单独确认。

### 使用

模块加载后自动监听群消息，无需额外配置。通过斜杠命令交互：

### 命令列表

| 命令 | 说明 |
|------|------|
| `/群地图` | 生成全群社交关系声呐图 |
| `/亲密度 @某人` | 查看你与某人的五维亲密度分析 |
| `/小圈子` | 查看群里的社交圈分布 |
| `/另一个我` | 找到和你最像但从未互动过的人 |
| `/我的位置` | 查看你在群社交圈中的位置（私聊返回全局档案） |
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

### 配置

首次加载自动生成默认配置，可在 ErisPulse 配置中修改 `ChatSonar` 节：

```toml
[ChatSonar]
min_messages = 10
update_interval = 3600
distance_threshold = 0.6
cooccur_window = 300
utc_offset = 8
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
| `radar_distance_scale` | `1.2` | 个人雷达距离缩放因子 |
| `radar_max_radius` | `1.1` | 个人雷达最大半径 |
| `weights.*` | 见上表 | 五维距离权重（自动归一化） |

### 架构

```
ChatSonar/
├── Core.py          模块入口，注册事件处理器与路由
├── Collector.py     消息采集器，提取时段/表情/词汇/互动/共现特征
├── Analyzer.py      分析引擎，计算距离矩阵、岛屿检测、平行匹配
├── Visualizer.py    可视化引擎，纯 Python 力导向布局 + Takumi 渲染现代化卡片
├── Commands.py      斜杠命令注册与响应处理
└── Templates.py     纯文本 / Markdown / Html 降级模板（不支持图片的平台使用）
```

> 从 v2.0 起可视化层由 [Takumi](https://pypi.org/project/ErisPulse-Takumi/) 渲染，不再依赖 matplotlib / numpy，也不再内嵌字体；中英文字体由 Takumi 内置提供。

### 分析维度

| 维度 | 权重 | 说明 |
|------|------|------|
| **Timing** 时段 | 20% | 24 小时活跃时段余弦相似度 |
| **Emoji** 表情 | 15% | 表情使用频率余弦相似度 |
| **Vocab** 词汇 | 20% | 中文 bigram + 英文词频余弦相似度 |
| **Interaction** 互动 | 30% | @ 回复 / 引用的双向互动强度 |
| **Co-occurrence** 共现 | 15% | 同一时间窗口内同时在线频率 |

距离公式：`distance = Σ(normalized_weight × (1 - score))`，值越小表示越亲密。

## License

- Code: [Apache License 2.0](LICENSE)
- Rendering fonts are provided by [ErisPulse-Takumi](https://pypi.org/project/ErisPulse-Takumi/) (Noto Sans SC etc.), © their respective owners, licensed under SIL OFL 1.1

---

<div align="center">

**Related** · [ErisPulse](https://github.com/ErisPulse/ErisPulse) · [ErisPulse-Takumi](https://github.com/ccd2s/ErisPulse-Takumi) · [Documentation](https://www.erisdev.com) · [Issues](https://github.com/wsu2059q/ErisPulse-ChatSonar/issues)

</div>
