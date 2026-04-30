import io
import math
import os
import re
import warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap

warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")


class Visualizer:
    SONAR_COLORS = [
        "#00ff88", "#00bbff", "#ffaa00", "#ff4466",
        "#aa66ff", "#00ffcc", "#ff8844", "#88ff44",
    ]

    _EMOJI_RE = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937"
        "\U00010000-\U0010ffff"
        "\u2640-\u2642"
        "\u2600-\u2B55"
        "\u200d"
        "\u23cf"
        "\u23e9"
        "\u231a"
        "\ufe0f"
        "\u3030"
        "\u20e3"
        "\uFE0F"
        "]+",
        flags=re.UNICODE,
    )

    _font_initialized = False

    @classmethod
    def _strip_emoji(cls, text):
        return cls._EMOJI_RE.sub("", text).strip() or text

    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Visualizer")
        self.config = config
        self._font_prop = None
        if not Visualizer._font_initialized:
            Visualizer._font_initialized = True
            self._setup_fonts()

    @classmethod
    def _setup_fonts(cls):
        font_dir = os.path.join(os.path.dirname(__file__), "fonts")
        bundled = os.path.join(font_dir, "SourceHanSansSC-Regular.otf")
        if os.path.exists(bundled):
            try:
                fm.fontManager.addfont(bundled)
                prop = fm.FontProperties(fname=bundled)
                plt.rcParams["font.sans-serif"] = [prop.get_name()] + plt.rcParams.get("font.sans-serif", [])
            except Exception as e:
                warnings.warn(f"Failed to load bundled font: {e}")

        candidates = [
            "Microsoft YaHei", "SimHei", "PingFang SC",
            "WenQuanYi Micro Hei", "Noto Sans CJK SC",
            "STHeiti", "Arial Unicode MS",
        ]
        available = {f.name for f in fm.fontManager.ttflist}
        for name in candidates:
            if name in available:
                plt.rcParams["font.sans-serif"] = [name]
                break
        plt.rcParams["axes.unicode_minus"] = False

    def _mds_2d(self, users, matrix):
        n = len(users)
        if n < 2:
            return {users[0]: (0.0, 0.0)} if n == 1 else {}

        dist_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                key = f"{users[i]}|{users[j]}"
                dist_matrix[i][j] = matrix.get(key, 1.0)

        n_components = min(2, n - 1)
        H = np.eye(n) - np.ones((n, n)) / n
        B = -0.5 * H @ (dist_matrix ** 2) @ H

        try:
            eigenvalues, eigenvectors = np.linalg.eigh(B)
            idx = np.argsort(eigenvalues)[::-1]
            eigenvalues = eigenvalues[idx]
            eigenvectors = eigenvectors[:, idx]

            positive = eigenvalues > 0
            eigenvalues_pos = eigenvalues[positive][:n_components]
            eigenvectors_pos = eigenvectors[:, positive][:, :n_components]

            coords = eigenvectors_pos * np.sqrt(eigenvalues_pos)
        except Exception:
            self.logger.warning("MDS failed, using random layout")
            coords = np.random.RandomState(42).rand(n, n_components) * 2 - 1

        if n_components == 1:
            coords = np.column_stack([coords, np.zeros(n)])

        max_range = max(coords[:, 0].max() - coords[:, 0].min(),
                        coords[:, 1].max() - coords[:, 1].min(), 0.01)
        coords = (coords - coords.mean(axis=0)) / max_range

        result = {}
        for i, uid in enumerate(users):
            result[uid] = (float(coords[i, 0]), float(coords[i, 1]))
        return result

    def generate_sonar(self, users, matrix, islands, nicknames=None, msg_counts=None):
        if not users or len(users) < 2:
            return None

        if nicknames is None:
            nicknames = {}
        if msg_counts is None:
            msg_counts = {}

        coords = self._mds_2d(users, matrix)

        fig, ax = plt.subplots(figsize=(12, 12), facecolor="#0a0a1a", dpi=200)
        ax.set_facecolor("#0a0a1a")

        # 添加主标题（中英双语）
        fig.suptitle("群聊社交声呐图 / Group Chat Social Sonar Map", 
                     fontsize=16, color="#00ff88", fontweight="bold", y=0.98)
        
        # 添加说明文本框
        info_text = (
            "图表说明 / Info:\n"
            "• 每个点代表一个群成员 / Each dot = one member\n"
            "• 距离越近表示关系越亲密 / Closer = closer relationship\n"
            "• 相同颜色属于同一社交圈 / Same color = same social circle\n"
            "• 连线表示有直接互动 / Lines = direct interaction"
        )
        ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                fontsize=9, color="#aaaacc", verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.8', facecolor='#1a1a2e', 
                         edgecolor='#00ff88', alpha=0.8))

        # 绘制同心圆网格（距离参考）
        for r in [0.3, 0.6, 0.9, 1.2]:
            circle = plt.Circle((0, 0), r, fill=False, color="#1a3a4a",
                                linewidth=1.0, linestyle="--", alpha=0.4)
            ax.add_patch(circle)
        
        # 添加距离标签
        for r, label in [(0.3, "0.3"), (0.6, "0.6"), (0.9, "0.9")]:
            ax.text(r, 0.02, label, fontsize=7, color="#556666", ha='center')

        # 绘制径向线
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            ax.plot([0, 1.3 * math.cos(rad)], [0, 1.3 * math.sin(rad)],
                    color="#1a3a4a", linewidth=0.6, alpha=0.3)

        # 密度热力场（数据驱动，纯numpy高斯叠加）
        bandwidth = self.config.get("density_bandwidth", 0.15)
        grid_res = 200
        xg = np.linspace(-1.5, 1.5, grid_res)
        yg = np.linspace(-1.5, 1.5, grid_res)
        X, Y = np.meshgrid(xg, yg)
        density = np.zeros_like(X)

        for uid in users:
            ux, uy = coords[uid]
            density += np.exp(-((X - ux) ** 2 + (Y - uy) ** 2) / (2 * bandwidth ** 2))

        density /= max(density.max(), 1e-10)

        sonar_heat_cmap = LinearSegmentedColormap.from_list("sonar_heat", [
            (0, 0, 0, 0),
            (0, 0.4, 0.27, 0.15),
            (0, 1, 0.53, 0.35),
        ])
        ax.imshow(density, extent=[-1.5, 1.5, -1.5, 1.5], origin="lower",
                  cmap=sonar_heat_cmap, aspect="auto", zorder=1)

        # 岛屿映射
        island_map = {}
        for idx, island in enumerate(islands):
            color = self.SONAR_COLORS[idx % len(self.SONAR_COLORS)]
            for uid in island["members"]:
                island_map[uid] = (idx, color)

        default_color = "#446666"
        threshold = self.config.get("distance_threshold", 0.6)

        # 绘制连线（在底层）
        drawn_pairs = set()
        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                key = f"{users[i]}|{users[j]}"
                dist = matrix.get(key, 1.0)
                if dist < threshold:
                    x1, y1 = coords[users[i]]
                    x2, y2 = coords[users[j]]
                    alpha = max(0.15, min(0.7, (1.0 - dist) * 0.9))
                    c1 = island_map.get(users[i], (0, default_color))[1]
                    c2 = island_map.get(users[j], (0, default_color))[1]
                    line_color = c1 if c1 == c2 else "#335555"
                    ax.plot([x1, x2], [y1, y2], color=line_color,
                            linewidth=2.0, alpha=alpha, zorder=3)

        # 绘制节点和标签（在上层）
        for uid in users:
            x, y = coords[uid]
            info = island_map.get(uid)
            color = info[1] if info else default_color
            
            # 获取消息数量用于调整节点大小 (这里保持默认或根据实际数据扩展)
            msg_count = msg_counts.get(uid, 10)

            # 节点光晕效果（增强可见性）
            for glow_size in [0.08, 0.05, 0.03]:
                glow = plt.Circle((x, y), glow_size, color=color, alpha=0.15)
                ax.add_patch(glow)

            # 主节点
            ax.scatter(x, y, s=120 + msg_count * 3, c=color,
                       alpha=0.95, edgecolors="white", linewidths=1.0, zorder=5)

            # 智能标签位置（根据象限调整偏移方向）
            offset_x = 12 if x >= 0 else -12
            offset_y = 12 if y >= 0 else -12
            
            # 标签背景框（避免与线条重叠）
            label = self._strip_emoji(nicknames.get(uid, uid))
            bbox_props = dict(boxstyle='round,pad=0.4', facecolor='#0a0a1a', 
                             edgecolor=color, alpha=0.7, linewidth=0.8)
            ax.annotate(label, (x, y), textcoords="offset points",
                        xytext=(offset_x, offset_y), fontsize=10, 
                        color=color, alpha=0.95, fontweight="bold",
                        bbox=bbox_props, zorder=6)

        # 添加图例
        legend_elements = []
        unique_colors = set()
        for uid in users:
            info = island_map.get(uid)
            if info:
                color = info[1]
                if color not in unique_colors:
                    unique_colors.add(color)
                    island_idx = info[0]
                    legend_elements.append(
                        plt.Line2D([0], [0], marker='o', color='w', 
                                  markerfacecolor=color, markersize=10,
                                  label=f'岛屿 {island_idx + 1} / Island {island_idx + 1}',
                                  alpha=0.9))
        
        if len(unique_colors) > 0:
            legend = ax.legend(handles=legend_elements, loc='lower right',
                              fontsize=9, facecolor='#0a0a1a',
                              edgecolor='#1a3a4a', labelcolor='#aaaacc',
                              framealpha=0.9, title="社交圈 / Social Circles")
            legend.get_title().set_fontsize(10)
            legend.get_title().set_color('#00ff88')

        # 底部统计信息
        total_users = len(users)
        total_islands = len(islands)
        stats_text = f"总人数: {total_users} | 岛屿数: {total_islands} | Total: {total_users} members, {total_islands} islands"
        ax.text(0.5, 0.02, stats_text, transform=ax.transAxes,
                fontsize=10, color="#00ff88", ha='center',
                bbox=dict(boxstyle='round,pad=0.6', facecolor='#1a1a2e', 
                         edgecolor='#00ff88', alpha=0.8))

        ax.set_xlim(-1.6, 1.6)
        ax.set_ylim(-1.6, 1.6)
        ax.set_aspect("equal")
        ax.axis("off")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                    facecolor="#0a0a1a", edgecolor="none", pad_inches=0.3)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def generate_radar_chart(self, scores):
        dims = ["timing", "emoji", "vocab", "interaction", "cooccurrence"]
        labels_zh = ["时段重叠", "表情相似", "词汇相似", "直接互动", "共现频率"]
        labels_en = ["Timing", "Emoji", "Vocab", "Interaction", "Co-occur"]
        # 中英双语标签
        labels = [f"{zh}\n{en}" for zh, en in zip(labels_zh, labels_en)]
        values = [scores.get(d, 0) for d in dims]

        angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
        values_plot = values + [values[0]]
        angles_plot = angles + [angles[0]]

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True),
                                facecolor="#0a0a1a", dpi=200)
        ax.set_facecolor("#0a0a1a")

        # 添加标题
        ax.set_title("亲密度分析 / Intimacy Analysis", 
                     fontsize=14, color="#00ff88", fontweight="bold", pad=25)

        # 多层填充效果
        ax.fill(angles_plot, values_plot, color="#00ff88", alpha=0.25, zorder=2)
        ax.plot(angles_plot, values_plot, color="#00ff88", linewidth=2.5, zorder=3)

        # 在每个维度上显示百分比
        for angle, val, label in zip(angles, values, labels):
            # 数值标签
            ax.annotate(f"{int(val * 100)}%", xy=(angle, val),
                        textcoords="offset points", xytext=(12, 8),
                        fontsize=11, color="#00ff88", fontweight="bold",
                        bbox=dict(boxstyle='round,pad=0.4', facecolor='#0a0a1a', 
                                 edgecolor='#00ff88', alpha=0.8))

        ax.set_xticks(angles)
        ax.set_xticklabels(labels, fontsize=9, color="#aaaacc")
        ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(["20%", "40%", "60%", "80%", "100%"],
                            fontsize=8, color="#556666")
        ax.set_ylim(0, 1)
        ax.spines["polar"].set_color("#1a3a4a")
        ax.grid(color="#1a3a4a", alpha=0.5, linestyle="--")

        # 添加说明文本
        info_text = (
            "数值越高表示相似度越高\n"
            "Higher value = more similar"
        )
        ax.text(0.5, 0.02, info_text, transform=ax.transAxes,
                fontsize=8, color="#aaaacc", ha='center',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#1a1a2e', 
                         edgecolor='#00bbff', alpha=0.7))

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                    facecolor="#0a0a1a", edgecolor="none", pad_inches=0.3)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def generate_personal_radar(self, user_id, distances, nicknames=None):
        if not distances:
            return None
        if nicknames is None:
            nicknames = {}

        sorted_dists = sorted(distances.items(), key=lambda x: x[1]["distance"])
        others = [uid for uid, _ in sorted_dists]

        if not others:
            return None

        n = len(others)
        fig, ax = plt.subplots(figsize=(10, 10), facecolor="#0a0a1a", dpi=200)
        ax.set_facecolor("#0a0a1a")

        # 添加标题
        my_name = nicknames.get(user_id, user_id)
        fig.suptitle(f"{my_name} 的社交雷达 / Social Radar", 
                     fontsize=15, color="#00ff88", fontweight="bold", y=0.97)

        # 绘制同心圆（距离参考）
        for r in [0.3, 0.6, 0.9]:
            circle = plt.Circle((0, 0), r, fill=False, color="#1a3a4a",
                                linewidth=1.0, linestyle="--", alpha=0.5)
            ax.add_patch(circle)
        
        # 距离标签
        for r, label_zh, label_en in [(0.3, "内圈", "Inner"), 
                                       (0.6, "中圈", "Middle"), 
                                       (0.9, "外圈", "Outer")]:
            ax.text(r, 0.03, f"{label_zh}/{label_en}", fontsize=7, 
                   color="#556666", ha='center')

        ring_colors = {0: "#00ff88", 1: "#00bbff", 2: "#ffaa00", 3: "#ff4466"}
        ring_labels = {
            0: ("内圈 <0.3", "Inner <0.3"),
            1: ("中圈 <0.6", "Middle <0.6"),
            2: ("外圈 <0.8", "Outer <0.8"),
            3: ("暗区 >0.8", "Dark >0.8")
        }

        # 绘制用户节点
        for i, uid in enumerate(others):
            dist = distances[uid]["distance"]
            angle = 2 * math.pi * i / n
            dist_scale = self.config.get("radar_distance_scale", 1.2)
            max_radius = self.config.get("radar_max_radius", 1.1)
            radius = min(dist * dist_scale, max_radius)
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)

            if dist < 0.3:
                color = ring_colors[0]
            elif dist < 0.6:
                color = ring_colors[1]
            elif dist < 0.8:
                color = ring_colors[2]
            else:
                color = ring_colors[3]

            # 光晕效果
            for glow_size in [0.06, 0.04]:
                glow = plt.Circle((x, y), glow_size, color=color, alpha=0.2)
                ax.add_patch(glow)

            # 主节点
            node_size = max(60, 200 * (1.0 - dist))
            ax.scatter(x, y, s=node_size, c=color, alpha=0.95,
                       edgecolors="white", linewidths=1.0, zorder=5)

            # 智能标签位置
            offset_x = 12 if x >= 0 else -12
            offset_y = 12 if y >= 0 else -12
            
            label = self._strip_emoji(nicknames.get(uid, uid))
            dist_text = f"{label}\n{dist:.2f}"
            bbox_props = dict(boxstyle='round,pad=0.4', facecolor='#0a0a1a', 
                             edgecolor=color, alpha=0.75, linewidth=0.8)
            ax.annotate(dist_text, (x, y), textcoords="offset points",
                        xytext=(offset_x, offset_y), fontsize=9, 
                        color=color, alpha=0.95, fontweight="bold",
                        bbox=bbox_props, zorder=6)

        # 中心用户（自己）
        ax.scatter(0, 0, s=250, c="#00ff88", marker="*", zorder=10,
                   edgecolors="white", linewidths=1.5)
        label_me = self._strip_emoji(nicknames.get(user_id, user_id))
        ax.annotate(label_me, (0, 0), textcoords="offset points",
                    xytext=(12, -18), fontsize=11, color="#00ff88",
                    fontweight="bold",
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='#0a0a1a', 
                             edgecolor='#00ff88', alpha=0.8))

        # 图例
        legend_elements = []
        for ring_idx, (label_zh, label_en) in ring_labels.items():
            color = ring_colors[ring_idx]
            legend_elements.append(
                plt.Line2D([0], [0], marker='o', color='w', 
                          markerfacecolor=color, markersize=10,
                          label=f"{label_zh} / {label_en}",
                          alpha=0.9))
        
        legend = ax.legend(handles=legend_elements, loc='upper right',
                          fontsize=9, facecolor='#0a0a1a',
                          edgecolor='#1a3a4a', labelcolor='#aaaacc',
                          framealpha=0.9, title="距离环 / Distance Rings")
        legend.get_title().set_fontsize(10)
        legend.get_title().set_color('#00ff88')

        # 底部统计
        inner_count = sum(1 for d in distances.values() if d["distance"] < 0.3)
        middle_count = sum(1 for d in distances.values() if 0.3 <= d["distance"] < 0.6)
        outer_count = sum(1 for d in distances.values() if 0.6 <= d["distance"] < 0.8)
        dark_count = sum(1 for d in distances.values() if d["distance"] >= 0.8)
        
        stats_text = (
            f"内圈: {inner_count}人 | 中圈: {middle_count}人 | "
            f"外圈: {outer_count}人 | 暗区: {dark_count}人"
        )
        ax.text(0.5, 0.02, stats_text, transform=ax.transAxes,
                fontsize=9, color="#00ff88", ha='center',
                bbox=dict(boxstyle='round,pad=0.6', facecolor='#1a1a2e', 
                         edgecolor='#00ff88', alpha=0.8))

        ax.set_xlim(-1.5, 1.5)
        ax.set_ylim(-1.5, 1.5)
        ax.set_aspect("equal")
        ax.axis("off")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                    facecolor="#0a0a1a", edgecolor="none", pad_inches=0.3)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def generate_heatmap(self, users, matrix, nicknames=None):
        if not users or len(users) < 2:
            return None
        if nicknames is None:
            nicknames = {}

        n = len(users)
        dist_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                key = f"{users[i]}|{users[j]}"
                dist_matrix[i][j] = matrix.get(key, 1.0)

        fig, ax = plt.subplots(figsize=(max(8, n * 0.8), max(6, n * 0.6)),
                                facecolor="#0a0a1a")
        ax.set_facecolor("#0a0a1a")

        labels = [nicknames.get(u, u) for u in users]
        im = ax.imshow(dist_matrix, cmap="RdYlGn_r", vmin=0, vmax=1, aspect="auto")

        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8, color="#aaaacc")
        ax.set_yticklabels(labels, fontsize=8, color="#aaaacc")

        for i in range(n):
            for j in range(n):
                val = dist_matrix[i][j]
                color = "white" if val > 0.5 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=7, color=color)

        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(colors="#aaaacc")
        cbar.set_label("\u8ddd\u79bb", color="#aaaacc")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor="#0a0a1a", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
