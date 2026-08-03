import html
import math
import random
import re
import time
import zlib


class Visualizer:
    BLUE = "#0a84ff"
    PINK = "#ff375f"
    VIOLET = "#bf5af2"
    GREEN = "#30d158"
    ORANGE = "#ff9f0a"

    SONAR_COLORS = [
        "#0a84ff", "#ff375f", "#bf5af2", "#30d158",
        "#ff9f0a", "#5e5ce6", "#64d2ff", "#ff453a",
    ]
    RING_COLORS = {"inner": "#0a84ff", "middle": "#bf5af2", "outer": "#ff375f", "dark": "#8e8e93"}

    _EMOJI_RE = re.compile(
        "["
        "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937\U00010000-\U0010ffff\u2640-\u2642\u2600-\u2B55"
        "\u200d\u23cf\u23e9\u231a\ufe0f\u3030\u20e3\uFE0F]+",
        flags=re.UNICODE,
    )

    CARD_WIDTH = 920
    MAP_SVG = 720
    RADAR_SVG = 420
    _PAGE_PAD = 40
    _CARD_PAD = 28
    _CARD_GAP = 14

    _CSS_TPL = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: "Noto Sans SC", "Source Han Sans SC", sans-serif;
        background: __PAGE__; color: __INK__; -webkit-font-smoothing: antialiased;
        padding: 40px;
    }
    .card {
        background: __CARD__; border-radius: 18px; padding: 28px 30px;
        margin-bottom: 14px;
    }
    .last { margin-bottom: 0; }
    .head { margin-bottom: 4px; }
    .title { font-size: 27px; font-weight: 700; color: __INK__; letter-spacing: -0.4px; }
    .subtitle { font-size: 14px; color: __SUB__; margin-top: 4px; }
    .divider { height: 1px; background: __SEP__; margin: 20px 0; }
    .chips { display: flex; flex-wrap: wrap; gap: 10px; }
    .chip { padding: 8px 14px; border-radius: 9px; font-size: 13px; background: __SOFT__; color: __INK__; }
    .chip b { color: __BLUE__; font-weight: 600; margin-right: 4px; }
    .chip.pink b { color: __PINK__; }
    .chip.violet b { color: __VIOLET__; }
    .chip.green b { color: __GREEN__; }
    .map-wrap { display: flex; justify-content: center; }
    .stage { position: relative; }
    .stage > svg { position: absolute; left: 0; top: 0; }
    .lbl {
        position: absolute; transform: translate(-50%, -50%);
        background: __LBLBG__; padding: 2px 7px; border-radius: 5px;
        font-size: 12px; font-weight: 600; white-space: nowrap;
        border: 1px solid; line-height: 1.4;
    }
    .ring-tag {
        position: absolute; transform: translate(-50%, -50%);
        font-size: 11px; color: __SUB__; background: __LBLBG__; padding: 0 4px;
    }
    .section-label {
        font-size: 12px; font-weight: 600; color: __SUB__;
        letter-spacing: 0.8px; margin: 4px 0 12px; text-transform: uppercase;
    }
    .island-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .island { border-radius: 12px; padding: 14px 16px; background: __SOFT__; border-left: 3px solid var(--c, __BLUE__); }
    .island .name { font-size: 15px; font-weight: 600; color: __INK__; }
    .island .meta { font-size: 12px; color: __SUB__; margin-top: 3px; }
    .island .members { font-size: 12.5px; color: __INK__; margin-top: 6px; line-height: 1.6; opacity: 0.72; }
    .lone { border-radius: 12px; padding: 14px 16px; background: __SOFT__; font-size: 13px; color: __SUB__; line-height: 1.7; }
    .lone b { color: __INK__; }
    .foot { font-size: 12.5px; color: __SUB__; text-align: center; margin-top: 14px; }
    .foot code { color: __BLUE__; background: __SOFT__; padding: 2px 7px; border-radius: 5px; font-family: "Source Code Pro", monospace; }
    .pair-row { display: flex; align-items: center; justify-content: space-between; }
    .pair-names { font-size: 22px; font-weight: 600; color: __INK__; }
    .pair-names .sep { color: var(--dc, __BLUE__); margin: 0 10px; }
    .dist-badge { text-align: center; padding: 8px 18px; border-radius: 12px; background: __SOFT__; border: 1px solid var(--dc, __BLUE__); }
    .dist-badge .v { font-size: 28px; font-weight: 700; color: var(--dc, __BLUE__); }
    .dist-badge .l { font-size: 12px; color: __SUB__; margin-top: 1px; }
    .radar-wrap { display: flex; justify-content: center; }
    .dim-grid { display: flex; flex-direction: column; gap: 14px; }
    .dim { display: flex; align-items: center; gap: 12px; }
    .dim .nm { width: 100px; font-size: 14px; color: __INK__; }
    .bar { flex: 1; height: 8px; border-radius: 5px; background: __SEP__; overflow: hidden; }
    .bar > i { display: block; height: 100%; border-radius: 5px; background: var(--c, __BLUE__); }
    .dim .pct { width: 44px; text-align: right; font-size: 14px; font-weight: 600; color: __INK__; font-variant-numeric: tabular-nums; }
    .kv { display: flex; gap: 10px; flex-wrap: wrap; }
    .pill { padding: 7px 13px; border-radius: 8px; font-size: 13px; background: __SOFT__; color: __INK__; }
    .pill b { color: __BLUE__; font-weight: 600; }
    .tags { display: flex; flex-wrap: wrap; gap: 6px; }
    .tag { padding: 4px 12px; border-radius: 7px; font-size: 13px; color: __BLUE__; background: __SOFTTAG__; }
    .note { font-size: 13px; color: __SUB__; }
    .note b { color: __BLUE__; }
    .empty { font-size: 15px; color: __SUB__; text-align: center; padding: 40px 20px; border-radius: 14px; background: __SOFT__; }
    """

    @classmethod
    def _strip_emoji(cls, text):
        return cls._EMOJI_RE.sub("", text).strip() or text

    @staticmethod
    def _esc(text):
        return html.escape(str(text))

    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Visualizer")
        self.config = config
        self._takumi_inst = None

    @property
    def takumi(self):
        if self._takumi_inst is None:
            inst = None
            try:
                inst = self.sdk.module.get("Takumi")
            except Exception:
                inst = None
            if inst is None:
                inst = getattr(self.sdk, "Takumi", None)
            self._takumi_inst = inst
        return self._takumi_inst

    def _theme(self):
        mode = self.config.get("theme", "auto")
        if mode == "auto":
            offset = self.config.get("utc_offset", 8)
            hour = int((time.time() / 3600 + offset) % 24)
            mode = "dark" if (hour >= 19 or hour < 7) else "light"
        if mode == "dark":
            return {"page": "#000000", "card": "#1c1c1e", "ink": "#f5f5f7", "sub": "#8e8e93",
                    "sep": "#38383a", "soft": "#2c2c2e", "softtag": "rgba(10,132,255,0.18)",
                    "lbl": "#1c1c1e", "dark": True}
        return {"page": "#f5f5f7", "card": "#ffffff", "ink": "#1d1d1f", "sub": "#6e6e73",
                "sep": "#e5e5ea", "soft": "#f5f5f7", "softtag": "#eef4ff",
                "lbl": "#ffffff", "dark": False}

    def _css(self):
        t = self._theme()
        css = (self._CSS_TPL
               .replace("__PAGE__", t["page"]).replace("__CARD__", t["card"])
               .replace("__INK__", t["ink"]).replace("__SUB__", t["sub"])
               .replace("__SEP__", t["sep"]).replace("__SOFT__", t["soft"])
               .replace("__SOFTTAG__", t["softtag"]).replace("__LBLBG__", t["lbl"])
               .replace("__BLUE__", self.BLUE).replace("__PINK__", self.PINK)
               .replace("__VIOLET__", self.VIOLET).replace("__GREEN__", self.GREEN))
        return css, t

    def _render(self, body_html, height):
        takumi = self.takumi
        if takumi is None or not hasattr(takumi, "render_html"):
            self.logger.error("Takumi 模块不可用，无法渲染图片")
            return None
        css, t = self._css()
        try:
            return takumi.render_html(
                body_html, stylesheets=[css],
                width=self.CARD_WIDTH, height=height, lang="zh-CN",
            )
        except Exception as e:
            self.logger.error(f"Takumi 渲染失败: {e}")
            return None

    @staticmethod
    def _dist_color(d):
        if d < 0.3:
            return "#0a84ff"
        if d < 0.6:
            return "#bf5af2"
        if d < 0.8:
            return "#ff375f"
        return "#8e8e93"

    def _head(self, title, subtitle):
        return (f"<div class='head'><div class='title'>{self._esc(title)}</div>"
                f"<div class='subtitle'>{self._esc(subtitle)}</div></div>")

    def _card(self, inner, last=False):
        return f"<div class='card{' last' if last else ''}'>{inner}</div>"

    def _cards_height(self, inner_heights, footer=0):
        n = len(inner_heights)
        return (self._PAGE_PAD * 2 + n * self._CARD_PAD * 2
                + sum(inner_heights) + max(0, n - 1) * self._CARD_GAP + footer + 24)

    @staticmethod
    def _rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    def _place_labels(self, ordered, node_px, label_of, max_labels=22, char_w=9, pad=16):
        placed = []
        out = {}
        offsets = [(26, -16), (26, 16), (-26, -16), (-26, 16),
                   (0, -28), (0, 28), (32, 0), (-32, 0)]
        for uid in ordered:
            if len(out) >= max_labels:
                break
            nx, ny = node_px[uid]
            text = label_of.get(uid)
            if not text:
                continue
            w = min(len(text), 8) * char_w + pad
            h = 20
            for ox, oy in offsets:
                cx, cy = nx + ox, ny + oy
                bx, by = cx - w / 2, cy - h / 2
                ok = True
                for (px, py, pw, ph) in placed:
                    if self._rects_overlap(bx, by, w, h, px, py, pw, ph):
                        ok = False
                        break
                if ok:
                    placed.append((bx, by, w, h))
                    out[uid] = (cx, cy, text)
                    break
        return out

    @staticmethod
    def _label_div(cx, cy, text, color):
        return (f"<div class='lbl' style='left:{cx:.1f}px;top:{cy:.1f}px;"
                f"border-color:{color};color:{color}'>{text}</div>")

    @staticmethod
    def _ring_tag(cx, cy, text):
        return f"<div class='ring-tag' style='left:{cx:.1f}px;top:{cy:.1f}px'>{text}</div>"

    # ------------------------------------------------------------------ layout
    def _force_layout(self, users, matrix):
        n = len(users)
        if n == 0:
            return {}
        if n == 1:
            return {users[0]: (0.0, 0.0)}
        pos = {}
        for i, u in enumerate(users):
            ang = 2 * math.pi * i / n
            pos[u] = [math.cos(ang) * 0.6, math.sin(ang) * 0.6]
        threshold = self.config.get("distance_threshold", 0.6)
        gravity, rep_k, temp = 0.045, 0.17, 0.55
        for _ in range(480):
            disp = {u: [0.0, 0.0] for u in users}
            for u in users:
                disp[u][0] -= pos[u][0] * gravity
                disp[u][1] -= pos[u][1] * gravity
            for i in range(n):
                ui = users[i]
                xi, yi = pos[ui]
                for j in range(i + 1, n):
                    uj = users[j]
                    dx, dy = xi - pos[uj][0], yi - pos[uj][1]
                    d2 = dx * dx + dy * dy
                    if d2 < 1e-6:
                        dx, dy, d2 = 1e-3, 1e-3, 2e-6
                    d = math.sqrt(d2)
                    rep = rep_k / d2
                    fx, fy = dx / d * rep, dy / d * rep
                    disp[ui][0] += fx; disp[ui][1] += fy
                    disp[uj][0] -= fx; disp[uj][1] -= fy
            for i in range(n):
                ui = users[i]
                xi, yi = pos[ui]
                for j in range(i + 1, n):
                    uj = users[j]
                    dist = matrix.get(f"{ui}|{uj}", 1.0)
                    if dist >= threshold:
                        continue
                    dx, dy = xi - pos[uj][0], yi - pos[uj][1]
                    d = math.hypot(dx, dy) or 1e-6
                    rest = 0.32 + (dist / threshold) * 1.05
                    force = (d - rest) * 0.16
                    fx, fy = dx / d * force, dy / d * force
                    disp[ui][0] -= fx; disp[ui][1] -= fy
                    disp[uj][0] += fx; disp[uj][1] += fy
            for u in users:
                dx, dy = disp[u]
                mag = math.hypot(dx, dy)
                if mag > 1e-6:
                    lim = min(mag, temp)
                    pos[u][0] += dx / mag * lim
                    pos[u][1] += dy / mag * lim
            temp = max(temp * 0.985, 0.01)
        xs = [pos[u][0] for u in users]
        ys = [pos[u][1] for u in users]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        return {u: ((pos[u][0] - cx) / span, (pos[u][1] - cy) / span) for u in users}

    def _svg_sonar(self, users, matrix, islands, msg_counts, node_px, t):
        island_map = {}
        for idx, island in enumerate(islands):
            color = self.SONAR_COLORS[idx % len(self.SONAR_COLORS)]
            for uid in island["members"]:
                island_map[uid] = (idx, color)
        default_color = "#8e8e93"
        threshold = self.config.get("distance_threshold", 0.6)
        max_count = max(max(msg_counts.values()) if msg_counts else 1, 1)
        size = self.MAP_SVG
        cxy = size / 2
        radius = size / 2 - 96
        sep = t["sep"]
        node_stroke = t["card"]
        svg = [f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}' xmlns='http://www.w3.org/2000/svg'>"]
        for r_frac in (0.3, 0.6, 0.9):
            svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='{radius * r_frac:.1f}' fill='none' stroke='{sep}' stroke-width='1'/>")
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='3' fill='{sep}'/>")
        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                dist = matrix.get(f"{users[i]}|{users[j]}", 1.0)
                if dist >= threshold:
                    continue
                x1, y1 = node_px[users[i]]
                x2, y2 = node_px[users[j]]
                alpha = max(0.12, min(0.6, (1.0 - dist) * 0.85))
                ic1 = island_map.get(users[i], (0, default_color))[1]
                ic2 = island_map.get(users[j], (0, default_color))[1]
                lc = ic1 if ic1 == ic2 else t["sub"]
                svg.append(f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' stroke='{lc}' stroke-width='1.6' opacity='{alpha:.2f}'/>")
        for uid in users:
            x, y = node_px[uid]
            color = island_map.get(uid, (0, default_color))[1]
            r_node = 8 + (msg_counts.get(uid, 1) / max_count) * 14
            svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r_node:.1f}' fill='{color}' stroke='{node_stroke}' stroke-width='2'/>")
        svg.append("</svg>")
        return "".join(svg), island_map, cxy, radius

    # ------------------------------------------------------------------ sonar
    def render_sonar(self, *, users, matrix, islands, nicknames=None,
                     msg_counts=None, island_names=None, drifters=None,
                     global_total=0, local_total=0, command_prefix="/"):
        if not users or len(users) < 2:
            return None
        nicknames = nicknames or {}
        msg_counts = msg_counts or {}
        island_names = island_names or []
        drifters = drifters or []
        _, t = self._css()
        coords = self._force_layout(users, matrix)
        size = self.MAP_SVG
        cxy = size / 2
        radius = size / 2 - 96
        node_px = {uid: (cxy + coords[uid][0] * radius, cxy + coords[uid][1] * radius) for uid in users}

        svg_shapes, island_map, _, _ = self._svg_sonar(users, matrix, islands, msg_counts, node_px, t)
        default_color = "#8e8e93"
        label_of = {uid: self._strip_emoji(nicknames.get(uid, uid)) for uid in users}
        ordered = sorted(users, key=lambda u: msg_counts.get(u, 0), reverse=True)
        labels = self._place_labels(ordered, node_px, label_of, max_labels=24)
        label_html = "".join(
            self._label_div(cx, cy, self._esc(txt), island_map.get(uid, (0, default_color))[1])
            for uid, (cx, cy, txt) in labels.items())
        ring_tags = (self._ring_tag(cxy + radius * 0.3, cxy, "0.3")
                     + self._ring_tag(cxy + radius * 0.6, cxy, "0.6")
                     + self._ring_tag(cxy + radius * 0.9, cxy, "0.9"))
        stage = f"<div class='stage' style='width:{size}px;height:{size}px'>{svg_shapes}{ring_tags}{label_html}</div>"

        threshold = self.config.get("distance_threshold", 0.6)
        edge_count = sum(1 for i in range(len(users)) for j in range(i + 1, len(users))
                         if matrix.get(f"{users[i]}|{users[j]}", 1.0) < threshold)

        chips = (f"<div class='chips'>"
                 f"<div class='chip'><b>{len(users)}</b>成员</div>"
                 f"<div class='chip violet'><b>{len(islands)}</b>社交圈</div>"
                 f"<div class='chip green'><b>{edge_count}</b>连接</div>"
                 f"<div class='chip pink'><b>{len(drifters)}</b>独立</div></div>")

        real_islands = [(island_names[i] if i < len(island_names) else f"社交圈 {i + 1}", isl)
                        for i, isl in enumerate(islands) if isl.get("size", 0) >= 2]
        lone = list(drifters)
        for isl in islands:
            if isl.get("size", 0) < 2:
                lone.extend(isl["members"])
        island_items = []
        for i, (name, isl) in enumerate(real_islands):
            color = self.SONAR_COLORS[i % len(self.SONAR_COLORS)]
            members_str = self._esc("、".join(self._strip_emoji(nicknames.get(m, m)) for m in isl["members"][:14]))
            island_items.append(
                f"<div class='island' style='--c:{color}'><div class='name'>{self._esc(name)}</div>"
                f"<div class='meta'>{isl['size']} 人 · 平均距离 {isl['avg_distance']}</div>"
                f"<div class='members'>{members_str}</div></div>")
        detail_inner = ""
        if island_items:
            detail_inner += f"<div class='section-label'>社交圈 Social Circles</div><div class='island-grid'>{''.join(island_items)}</div>"
        if lone:
            lone_names = self._esc("、".join(self._strip_emoji(nicknames.get(u, u)) for u in lone[:24]))
            extra = f" 等 {len(lone)} 人" if len(lone) > 24 else ""
            detail_inner += f"<div class='lone' style='margin-top:14px'><b>独立用户</b> · {len(lone)} 人<br>{lone_names}{extra}</div>"

        cards = [
            self._head("群聊社交声呐", "Group Chat Social Sonar Map") + "<div class='divider'></div>" + chips,
            f"<div class='map-wrap'>{stage}</div>",
        ]
        if detail_inner:
            cards.append(detail_inner)
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        body += f"<div class='foot'>用 <code>{command_prefix}亲密度 @某人</code> 查看具体距离 · 本群 {local_total} / 全局 {global_total} 条消息</div>"

        island_rows = max(1, math.ceil(len(real_islands) / 2))
        inner = [64 + 21 + 42, self.MAP_SVG]
        if detail_inner:
            inner.append(30 + island_rows * 96 + (64 if lone else 0))
        return self._render(body, self._cards_height(inner, footer=44))

    # ------------------------------------------------------------------ intimacy
    def render_intimacy(self, *, nickname_a, nickname_b, dist, dist_label, scores,
                        interact=None, cooccur_count=0, rank=None, command_prefix="/"):
        dims = ["timing", "emoji", "vocab", "interaction", "cooccurrence"]
        labels = ["时段重叠", "表情相似", "词汇相似", "直接互动", "共现频率"]
        values = [max(0.0, min(1.0, float(scores.get(d, 0)))) for d in dims]
        dist_color = self._dist_color(dist)
        _, t = self._css()

        size = self.RADAR_SVG
        c = size / 2
        R = 142
        n = 5
        angles = [math.radians(-90 + i * 360 / n) for i in range(n)]
        sep = t["sep"]
        svg = [f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}' xmlns='http://www.w3.org/2000/svg'>"]
        for frac in (0.25, 0.5, 0.75, 1.0):
            pts = " ".join(f"{c + R * frac * math.cos(a):.1f},{c + R * frac * math.sin(a):.1f}" for a in angles)
            svg.append(f"<polygon points='{pts}' fill='none' stroke='{sep}' stroke-width='1'/>")
        for a in angles:
            svg.append(f"<line x1='{c}' y1='{c}' x2='{c + R * math.cos(a):.1f}' y2='{c + R * math.sin(a):.1f}' stroke='{sep}' stroke-width='1'/>")
        data_pts = " ".join(f"{c + R * v * math.cos(a):.1f},{c + R * v * math.sin(a):.1f}" for a, v in zip(angles, values))
        svg.append(f"<polygon points='{data_pts}' fill='{self.BLUE}' fill-opacity='0.16' stroke='{self.BLUE}' stroke-width='2'/>")
        for a, v in zip(angles, values):
            vx, vy = c + R * v * math.cos(a), c + R * v * math.sin(a)
            svg.append(f"<circle cx='{vx:.1f}' cy='{vy:.1f}' r='4.5' fill='{self.BLUE}' stroke='{t['card']}' stroke-width='1.5'/>")
        svg.append("</svg>")
        overlays = ""
        for a, v, lab in zip(angles, values, labels):
            vx, vy = c + R * v * math.cos(a), c + R * v * math.sin(a)
            overlays += self._label_div(vx, vy - 14, f"{int(v * 100)}%", self.BLUE)
            overlays += self._label_div(c + (R + 28) * math.cos(a), c + (R + 28) * math.sin(a), self._esc(lab), t["ink"])
        stage = f"<div class='stage' style='width:{size}px;height:{size}px'>{ ''.join(svg)}{overlays}</div>"

        dim_rows = []
        for label, val in zip(labels, values):
            dim_rows.append(
                f"<div class='dim' style='--c:{self._dist_color(val)}'><div class='nm'>{label}</div>"
                f"<div class='bar'><i style='width:{val*100:.1f}%'></i></div>"
                f"<div class='pct'>{val*100:.0f}%</div></div>")

        pair = (f"<div class='pair-row' style='--dc:{dist_color}'>"
                f"<div class='pair-names'><span>{self._esc(self._strip_emoji(nickname_a))}</span>"
                f"<span class='sep'>&lt;-&gt;</span>"
                f"<span>{self._esc(self._strip_emoji(nickname_b))}</span></div>"
                f"<div class='dist-badge'><div class='v'>{dist:.2f}</div>"
                f"<div class='l'>{self._esc(dist_label)}</div></div></div>")

        dim_extra = ""
        if interact and (interact.get("reply_total", 0) > 0 or cooccur_count > 0):
            pills = []
            if interact.get("a_to_b", 0) or interact.get("b_to_a", 0):
                pills.append(f"<div class='pill'>@互动 <b>{interact['a_to_b'] + interact['b_to_a']}</b> 次</div>")
                pills.append(f"<div class='pill'>回复合计 <b>{interact.get('reply_total', 0)}</b> 次</div>")
            if cooccur_count > 0:
                pills.append(f"<div class='pill'>同时在线 <b>{cooccur_count}</b> 次</div>")
            dim_extra += f"<div class='kv' style='margin-top:14px'>{''.join(pills)}</div>"
        if rank:
            dim_extra += f"<div class='note' style='margin-top:10px'>你们是本群第 <b>{rank}</b> 亲密的组合</div>"

        cards = [
            self._head("亲密度报告", "Intimacy Analysis") + "<div class='divider'></div>" + pair,
            f"<div class='radar-wrap'>{stage}</div>",
            f"<div class='section-label'>五维相似度 Dimensions</div><div class='dim-grid'>{''.join(dim_rows)}</div>{dim_extra}",
        ]
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        return self._render(body, self._cards_height([64 + 21 + 76, self.RADAR_SVG, 30 + 5 * 26 + (60 if dim_extra else 0)], footer=10))

    # ------------------------------------------------------------------ personal radar
    def render_personal_radar(self, *, user_id, distances, nicknames=None,
                              global_count=0, presence=0, command_prefix="/"):
        if not distances:
            return None
        nicknames = nicknames or {}
        others = [uid for uid, _ in sorted(distances.items(), key=lambda x: x[1]["distance"])]
        if not others:
            return None
        _, t = self._css()
        size = self.MAP_SVG
        cxy = size / 2
        radius = size / 2 - 104
        dist_scale = self.config.get("radar_distance_scale", 1.2)
        max_radius = self.config.get("radar_max_radius", 1.1)
        n = len(others)
        my_name = self._strip_emoji(nicknames.get(user_id, user_id))
        sep = t["sep"]
        node_px = {}
        svg = [f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}' xmlns='http://www.w3.org/2000/svg'>"]
        for r_frac in (0.3, 0.6, 0.9):
            svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='{radius * r_frac:.1f}' fill='none' stroke='{sep}' stroke-width='1'/>")
        for i, uid in enumerate(others):
            dist = distances[uid]["distance"]
            ang = 2 * math.pi * i / n
            r = min(dist * dist_scale, max_radius) * radius
            x, y = cxy + r * math.cos(ang), cxy + r * math.sin(ang)
            node_px[uid] = (x, y)
            color = self._dist_color(dist)
            node_r = 6 + max(0.0, (1.0 - dist)) * 11
            svg.append(f"<line x1='{cxy}' y1='{cxy}' x2='{x:.1f}' y2='{y:.1f}' stroke='{color}' stroke-width='0.8' opacity='0.22'/>")
            svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{node_r:.1f}' fill='{color}' stroke='{t['card']}' stroke-width='1.6'/>")
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='10' fill='{self.BLUE}' stroke='{t['card']}' stroke-width='2.5'/>")
        svg.append("</svg>")
        label_of = {uid: f"{self._strip_emoji(nicknames.get(uid, uid))} {distances[uid]['distance']:.2f}" for uid in others}
        labels = self._place_labels(others, node_px, label_of, max_labels=24, char_w=8)
        label_html = "".join(
            self._label_div(cx, cy, self._esc(txt), self._dist_color(distances[uid]["distance"]))
            for uid, (cx, cy, txt) in labels.items())
        ring_tags = "".join(self._ring_tag(cxy + radius * f, cxy, lab)
                            for f, lab in [(0.3, "内圈"), (0.6, "中圈"), (0.9, "外圈")])
        me_tag = self._label_div(cxy, cxy + 24, self._esc(my_name[:10]), self.BLUE)
        stage = f"<div class='stage' style='width:{size}px;height:{size}px'>{ ''.join(svg)}{ring_tags}{label_html}{me_tag}</div>"

        rings = {"inner": [], "middle": [], "outer": [], "dark": []}
        for uid, info in distances.items():
            d = info["distance"]
            name = self._strip_emoji(nicknames.get(uid, uid))
            rings["inner" if d < 0.3 else "middle" if d < 0.6 else "outer" if d < 0.8 else "dark"].append((name, d))
        ring_items = []
        for key, lab, rng in [("inner", "内圈", "<0.3"), ("middle", "中圈", "0.3~0.6"),
                              ("outer", "外圈", "0.6~0.8"), ("dark", "暗区", ">0.8")]:
            items = rings[key]
            if not items:
                continue
            color = self.RING_COLORS[key]
            names = self._esc("  ".join(f"{nm}({dd:.2f})" for nm, dd in items[:16]))
            ring_items.append(
                f"<div class='island' style='--c:{color}'><div class='name'>{lab} "
                f"<span style='color:{t['sub']};font-size:12px;font-weight:400'> {rng} · {len(items)}人</span></div>"
                f"<div class='members'>{names}</div></div>")

        chips = (f"<div class='chips'><div class='chip'><b>{global_count}</b>全局消息</div>"
                 f"<div class='chip violet'><b>{presence}</b>本群消息</div>"
                 f"<div class='chip pink'><b>{len(others)}</b>联系人</div></div>")

        cards = [
            self._head(f"{my_name} 的社交雷达", "Personal Social Radar") + "<div class='divider'></div>" + chips,
            f"<div class='map-wrap'>{stage}</div>",
        ]
        if ring_items:
            cards.append(f"<div class='section-label'>距离分布 Distance Rings</div><div class='island-grid'>{''.join(ring_items)}</div>")
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        inner = [64 + 21 + 42, self.MAP_SVG]
        if ring_items:
            inner.append(30 + len(ring_items) * 96)
        return self._render(body, self._cards_height(inner, footer=8))

    # ------------------------------------------------------------------ profile
    def render_profile(self, *, nickname, global_count, groups=None, tags="",
                       peak_period="", top_emoji=None):
        groups = groups or []
        top_emoji = top_emoji or []
        chips = (f"<div class='chips'><div class='chip'><b>{global_count}</b>消息</div>"
                 f"<div class='chip violet'><b>{len(groups)}</b>活跃群</div></div>")
        blocks = self._head(f"{self._strip_emoji(nickname)} 的全局档案", "Global Profile") + "<div class='divider'></div>" + chips
        if tags:
            blocks += f"<div class='tags' style='margin-top:16px'>{ ''.join(self._tag(x) for x in tags.split('/') if x.strip())}</div>"
        kv = ""
        if peak_period:
            kv += f"<div class='pill'>活跃时段 <b>{self._esc(peak_period)}</b></div>"
        if top_emoji:
            kv += f"<div class='pill'>常用表情 <b>{' '.join(self._esc(e) for e, _ in top_emoji[:5])}</b></div>"
        if kv:
            blocks += f"<div class='kv' style='margin-top:14px'>{kv}</div>"
        if groups:
            items = "".join(f"<div class='pill'>[{self._esc(p)}] {self._esc(g)}: <b>{c}</b>条</div>" for p, g, c in groups)
            blocks += (f"<div class='section-label' style='margin-top:18px'>群聊分布 Groups</div>"
                       f"<div class='kv'>{items}</div>")
        body = self._card(blocks, last=True)
        h = 64 + 21 + 42 + (44 if tags else 0) + (48 if kv else 0) + (30 + max(1, math.ceil(len(groups) / 4)) * 44 if groups else 0)
        return self._render(body, self._cards_height([h], footer=8))

    def _tag(self, x):
        return f"<span class='tag'>{self._esc(x.strip())}</span>"

    # ------------------------------------------------------------------ parallel
    def render_parallel(self, *, my_name, local=None, cross=None, command_prefix="/"):
        local = local or None
        cross = cross or []
        _, t = self._css()
        cards = [self._head("正在寻找另一个你...", "Parallel Self")]
        inner_h = [64]
        if local:
            tname = self._strip_emoji(local.get("nickname", local["user_id"]))
            sim = int(local["similarity"] * 100)
            checks = ""
            for dim, label in [("timing", "活跃时段"), ("vocab", "消息风格"), ("emoji", "表情偏好")]:
                val = local.get("scores", {}).get(dim, 0)
                checks += (f"<div class='dim' style='--c:{self.BLUE}'><div class='nm'>{label}</div>"
                           f"<div class='bar'><i style='width:{val*100:.1f}%'></i></div>"
                           f"<div class='pct'>{val*100:.0f}%</div></div>")
            cards.append(
                f"<div class='section-label'>本群匹配 Local Match</div>"
                f"<div class='pair-row' style='--dc:{self.BLUE};margin-bottom:14px'>"
                f"<div class='pair-names' style='font-size:20px'><span>{self._esc(my_name)}</span>"
                f"<span class='sep'>&lt;-&gt;</span><span>{self._esc(tname)}</span></div>"
                f"<div class='dist-badge' style='--dc:{self.BLUE}'><div class='v'>{sim}%</div>"
                f"<div class='l'>相似度</div></div></div><div class='dim-grid'>{checks}</div>")
            inner_h.append(30 + 70 + 3 * 26)
        if cross:
            items = ""
            for item in cross:
                sp = item.get("scope", "").split(":")
                platform_name = sp[1] if len(sp) > 1 else "未知"
                sim = int(item["similarity"] * 100)
                label = self._strip_emoji(item.get("nickname", item["user_id"]))
                details = [f"{lb}{int(item.get('scores', {}).get(d, 0) * 100)}%"
                           for d, lb in [("timing", "时段"), ("emoji", "表情"), ("vocab", "词汇")]
                           if item.get("scores", {}).get(d, 0) > 0.6]
                det = f"<div class='meta'>匹配项: {self._esc(', '.join(details))}</div>" if details else ""
                items += (f"<div class='island' style='--c:{self.VIOLET}'><div class='name'>"
                          f"[{self._esc(platform_name)}] {self._esc(label)} "
                          f"<span style='color:{self.BLUE}'>· {sim}%</span></div>{det}</div>")
            cards.append(f"<div class='section-label'>跨群匹配 Cross-Scope ({len(cross)})</div>"
                         f"<div class='island-grid'>{''.join(items)}</div>")
            inner_h.append(30 + max(1, math.ceil(len(cross) / 2)) * 96)
        if len(cards) == 1:
            cards.append("<div class='empty'>没有找到另一个你<br>（可能你和所有人都互动过了）</div>")
            inner_h.append(120)
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        body += f"<div class='foot'>用 <code>{command_prefix}亲密度 @某人</code> 查看具体距离</div>"
        return self._render(body, self._cards_height(inner_h, footer=44))
