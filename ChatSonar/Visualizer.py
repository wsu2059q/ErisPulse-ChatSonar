import asyncio
import html
import math
import re
import time

INDIGO = "#6366f1"
VIOLET = "#8b5cf6"
BLOSSOM = "#ec4899"
MINT = "#10b981"
AMBER = "#f59e0b"
SLATE = "#94a3b8"
INK = "#1f2937"
MUTED = "#64748b"

SONAR_COLORS = [
    INDIGO, VIOLET, BLOSSOM, MINT, AMBER,
    "#38bdf8", "#fb7185", "#a78bfa",
]
RING_COLORS = {"inner": INDIGO, "middle": VIOLET, "outer": BLOSSOM, "dark": SLATE}

_MASCOT_APIS = [
    "https://www.loliapi.com/acg/",
    "https://api.paugram.com/wallpaper/",
    "https://www.dmoe.cc/random.php",
]
_MASCOT_TTL = 600.0  # 萌图缓存时长（秒）


class Visualizer:
    """声呐可视化渲染器（Takumi HTML -> 图片）。

    萌图整页铺底（多源拉取）+ 透白卡片；无萌图时使用渐变光斑背景。
    关系图以 SVG 绘制：圈子凸包、弧形连接线、扫描光楔、雷达填充。
    """

    CARD_WIDTH = 920
    MAP_SVG = 560
    RADAR_SVG = 420
    _PAGE_PAD = 36

    # emoji 与符号区段（不含 CJK 汉字区）
    _EMOJI_RE = re.compile(
        "["
        "\U0001F000-\U0001FAFF"
        "\u2300-\u23FF"
        "\u24C2-\u24FF"
        "\u25A0-\u27BF"
        "\u2B00-\u2BFF"
        "\u2934-\u2935"
        "\u3030\u303D\u3297\u3299"
        "\uFE0F\u20E3\u200D\u2122\u2139"
        "]+",
        flags=re.UNICODE,
    )

    _FONT_SANS = (
        '"DM Sans", "Inter", "Noto Sans SC", "Source Han Sans SC", '
        '"PingFang SC", "Microsoft YaHei", sans-serif'
    )
    _FONT_MONO = '"JetBrains Mono", "Source Code Pro", Consolas, monospace'

    _CSS_TPL = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: __FONTSANS__; color: __INK__; -webkit-font-smoothing: antialiased; }
    .page { position: relative; background: __PAGE__; padding: __PAGEPAD__px; overflow: hidden; }
    /* ---- 萌图背景层（有图时注入）---- */
    .bg-media { position: absolute; left: 0; top: 0; right: 0; bottom: 0; border-radius: 28px; overflow: hidden; }
    .bg-media img { position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: cover; object-position: center top; }
    .bg-wash { position: absolute; left: 0; top: 0; right: 0; bottom: 0; background: __WASH__; }
    /* ---- 渐变光斑背景（无图时注入）---- */
    .glow { position: absolute; border-radius: 999px; }
    .glow-a { width: 460px; height: 460px; top: -140px; right: -100px;
        background: radial-gradient(closest-side, rgba(99,102,241,0.18), transparent); }
    .glow-b { width: 520px; height: 520px; bottom: -180px; left: -140px;
        background: radial-gradient(closest-side, rgba(236,72,153,0.12), transparent); }
    .glow-c { width: 380px; height: 380px; top: 34%; left: 30%;
        background: radial-gradient(closest-side, rgba(16,185,129,0.08), transparent); }
    .page-content { position: relative; }
    /* ---- 玻璃卡片 ---- */
    .card {
        background: __CARD__; border-radius: 24px; padding: 26px 30px;
        margin-bottom: 20px; box-shadow: __CARDSHADOW__;
    }
    .last { margin-bottom: 0; }
    .head-row { display: flex; align-items: center; gap: 16px; }
    .logo-chip {
        flex: 0 0 auto; width: 56px; height: 56px; border-radius: 999px;
        background: rgba(99,102,241,0.12); display: flex; align-items: center; justify-content: center;
    }
    .head-text { min-width: 0; }
    .title { font-size: 27px; font-weight: 700; color: __INK__; letter-spacing: -0.5px; }
    .subtitle { font-size: 14px; color: __MUTED__; margin-top: 3px; }
    .divider { height: 2px; margin: 18px 0;
        background: linear-gradient(90deg, transparent, __SEP__, transparent); }
    /* ---- 玻璃胶囊 chips ---- */
    .chips { display: flex; flex-wrap: wrap; gap: 10px; }
    .chip {
        padding: 8px 18px; border-radius: 999px; font-size: 13px;
        background: __SOFT__; color: __INK__;
    }
    .chip b { font-weight: 700; margin-right: 5px; color: __INDIGO__; font-variant-numeric: tabular-nums; }
    .chip.violet b { color: __VIOLET__; }
    .chip.pink b { color: __BLOSSOM__; }
    .chip.green b { color: __MINT__; }
    /* ---- 区块标签：小波浪 SVG 点缀，无竖条 ---- */
    .section-label {
        display: flex; align-items: center; gap: 9px;
        font-size: 12.5px; font-weight: 600; color: __MUTED__;
        letter-spacing: 0.8px; margin: 4px 0 14px;
    }
    .section-label svg { flex: 0 0 auto; }
    /* ---- 社交圈卡：低透明度色底 + 玻璃块 ---- */
    .island-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .island { border-radius: 20px; padding: 16px 18px; }
    .island .name { font-size: 15px; font-weight: 600; color: __INK__; }
    .island .meta { font-size: 12px; color: __MUTED__; margin-top: 5px; }
    .island .members { font-size: 12.5px; color: __INK__; margin-top: 7px; line-height: 1.7; opacity: 0.75; }
    .lone { border-radius: 20px; padding: 16px 18px; background: __SOFT__; font-size: 13px; color: __MUTED__; line-height: 1.8; }
    .lone b { color: __INK__; }
    .foot { font-size: 12.5px; color: __MUTED__; text-align: center; margin-top: 16px; line-height: 1.7; }
    .foot code { color: __INDIGO__; background: __SOFT__; padding: 3px 10px; border-radius: 999px; font-family: __FONTMONO__; }
    /* ---- 亲密度：头像对 + 距离徽章 ---- */
    .pair-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
    .pair-names { display: flex; align-items: center; gap: 10px; font-size: 21px; font-weight: 600; color: __INK__; min-width: 0; flex-wrap: wrap; }
    .dist-badge { flex: 0 0 auto; text-align: center; padding: 10px 20px; border-radius: 18px; }
    .dist-badge .v { font-size: 27px; font-weight: 700; color: var(--dc, __INDIGO__); font-variant-numeric: tabular-nums; }
    .dist-badge .l { font-size: 12px; color: __MUTED__; margin-top: 2px; }
    .radar-wrap { display: flex; justify-content: center; }
    /* ---- 五维条 ---- */
    .dim-grid { display: flex; flex-direction: column; gap: 14px; }
    .dim { display: flex; align-items: center; gap: 12px; }
    .dim .nm { width: 100px; font-size: 13.5px; color: __INK__; }
    .bar { flex: 1; height: 10px; border-radius: 999px; background: __SEP__; overflow: hidden; }
    .bar > i { display: block; height: 100%; border-radius: 999px;
        background: linear-gradient(90deg, var(--c, __INDIGO__), rgba(255,255,255,0.40)); }
    .dim .pct { width: 46px; text-align: right; font-size: 13.5px; font-weight: 600; color: __INK__; font-variant-numeric: tabular-nums; }
    /* ---- 信息 pill 与标签 ---- */
    .kv { display: flex; gap: 10px; flex-wrap: wrap; }
    .pill { padding: 8px 15px; border-radius: 999px; font-size: 13px; background: __SOFT__; color: __INK__; }
    .pill b { color: __INDIGO__; font-weight: 600; }
    .tags { display: flex; flex-wrap: wrap; gap: 8px; }
    .tag { padding: 5px 14px; border-radius: 999px; font-size: 13px; color: __BLOSSOM__; background: rgba(236,72,153,0.10); }
    .note { font-size: 13px; color: __MUTED__; }
    .note b { color: __INDIGO__; }
    .empty { font-size: 15px; color: __MUTED__; text-align: center; padding: 44px 20px; border-radius: 20px; background: __SOFT__; }
    /* ---- 地图标签（玻璃小药丸）---- */
    .stage { position: relative; }
    .stage > svg { position: absolute; left: 0; top: 0; }
    .map-wrap { display: flex; justify-content: center; }
    .map-row { display: flex; gap: 16px; align-items: flex-start; }
    .rail { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
    .rail .island { padding: 13px 15px; }
    .rail .section-label { margin: 0 0 2px; }
    .lbl {
        position: absolute; transform: translate(-50%, -50%);
        background: __LBLBG__; padding: 3px 11px; border-radius: 999px;
        font-size: 12px; font-weight: 600; white-space: nowrap;
        color: var(--lc, __INDIGO__); box-shadow: __LBLSHADOW__; line-height: 1.4;
    }
    .ring-tag {
        position: absolute; transform: translate(-50%, -50%);
        font-size: 11px; color: __MUTED__; background: __LBLBG__;
        padding: 1px 8px; border-radius: 999px;
    }
    /* ---- 头像 chip 与镜像对 ---- */
    .avatar-chip {
        flex: 0 0 auto; width: 64px; height: 64px; border-radius: 999px;
        background: rgba(99,102,241,0.10); border: 2px dashed rgba(99,102,241,0.30);
        display: flex; align-items: center; justify-content: center;
        font-size: 24px; font-weight: 700; color: var(--ac, #6366f1);
    }
    .mirror { display: flex; align-items: center; gap: 14px; padding: 10px 2px 20px; }
    .m-line { flex: 1; border-top: 2px dashed rgba(148,163,184,0.45); }
    /* ---- 跨群匹配行 ---- */
    .cross-row { border-radius: 18px; padding: 14px 16px; background: __SOFT__; }
    .cross-row .name-row { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
    .cross-row .plat { font-size: 11.5px; font-weight: 600; color: __VIOLET__;
        background: rgba(139,92,246,0.10); padding: 3px 10px; border-radius: 999px; }
    .cross-row .name { font-size: 14px; font-weight: 600; color: __INK__; }
    .cross-row .sim { font-size: 14px; font-weight: 700; color: __INDIGO__; font-variant-numeric: tabular-nums; }
    .cross-row .meta { font-size: 11.5px; color: __MUTED__; margin-top: 5px; }
    """

    @classmethod
    def _strip_emoji(cls, text):
        return cls._EMOJI_RE.sub("", text).strip() or text

    @staticmethod
    def _esc(text):
        return html.escape(str(text))

    @staticmethod
    def _rgba(color, alpha):
        """hex 颜色转 rgba 字符串。"""
        c = color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Visualizer")
        self.config = config
        self._takumi_inst = None
        self._mascot_data = None  # 萌图字节（经 images 参数注入渲染）
        self._mascot_size = None  # (w, h)
        self._last_fetch = 0.0
        self._refreshing = False

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

    # ------------------------------------------------------------------ 萌图背景
    def _moe_enabled(self):
        return bool(self.config.get("moe_background", True))

    async def _ensure_mascot(self):
        """拉取萌图，TTL 内复用缓存。"""
        if not self._moe_enabled():
            return
        if self._refreshing:
            return
        if self._mascot_data is not None and time.time() - self._last_fetch < _MASCOT_TTL:
            return
        await self._refresh_mascot()

    async def _refresh_mascot(self):
        client = getattr(self.sdk, "client", None)
        if client is None:
            return
        self._refreshing = True
        try:
            for url in _MASCOT_APIS:
                try:
                    resp = await client.get(url, timeout=8)
                    if resp.status != 200:
                        continue
                    data = await resp.read()
                    if not data or len(data) > 6 * 1024 * 1024:
                        continue
                    self._mascot_size = self._img_dims(data)
                    self._mascot_data = data
                    self._last_fetch = time.time()
                    return
                except Exception as e:
                    self.logger.debug(e)
                    continue
        finally:
            self._refreshing = False

    def _schedule_refresh(self):
        """缓存过期时创建异步刷新任务。"""
        if self._refreshing or not self._moe_enabled() or getattr(self.sdk, "client", None) is None:
            return
        if self._mascot_data is not None and time.time() - self._last_fetch < _MASCOT_TTL:
            return
        self._refreshing = True

        async def _job():
            try:
                await self._refresh_mascot()
            finally:
                self._refreshing = False

        try:
            asyncio.create_task(_job())
        except RuntimeError:
            self._refreshing = False

    @staticmethod
    def _img_dims(data: bytes):
        """解析 PNG / JPEG / WebP 像素尺寸，失败返回 None。"""
        try:
            if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
                w = int.from_bytes(data[16:20], "big")
                h = int.from_bytes(data[20:24], "big")
                return (w, h) if w and h else None
            if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                chunk = data[12:16]
                if chunk == b"VP8 ":
                    w = int.from_bytes(data[26:28], "little") & 0x3FFF
                    h = int.from_bytes(data[28:30], "little") & 0x3FFF
                    return (w, h) if w and h else None
                if chunk == b"VP8L":
                    bits = int.from_bytes(data[21:25], "little")
                    w = (bits & 0x3FFF) + 1
                    h = ((bits >> 14) & 0x3FFF) + 1
                    return (w, h)
                if chunk == b"VP8X":
                    w = int.from_bytes(data[24:27], "little") + 1
                    h = int.from_bytes(data[27:30], "little") + 1
                    return (w, h)
            if data[:2] == b"\xff\xd8":  # JPEG: 扫描 SOF 段
                i, n = 2, len(data)
                sof = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
                while i + 9 < n:
                    if data[i] != 0xFF:
                        i += 1
                        continue
                    marker = data[i + 1]
                    if marker in sof:
                        h = int.from_bytes(data[i + 5:i + 7], "big")
                        w = int.from_bytes(data[i + 7:i + 9], "big")
                        return (w, h) if w and h else None
                    if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                        i += 2
                        continue
                    seg_len = int.from_bytes(data[i + 2:i + 4], "big")
                    if seg_len < 2:
                        return None
                    i += 2 + seg_len
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ 主题与渲染
    def _theme(self):
        mode = self.config.get("theme", "auto")
        if mode == "auto":
            offset = self.config.get("utc_offset", 8)
            hour = int((time.time() / 3600 + offset) % 24)
            mode = "dark" if (hour >= 19 or hour < 7) else "light"
        if mode == "dark":
            return {
                "mode": "dark",
                "page": "#14161d", "card": "rgba(32,36,46,0.80)",
                "wash": "rgba(15,17,23,0.72)",
                "ink": "#eef2f7", "muted": "#9aa5b5",
                "sep": "rgba(148,163,184,0.18)", "soft": "rgba(148,163,184,0.10)",
                "cardshadow": "0 12px 32px rgba(0,0,0,0.35)",
                "lblbg": "rgba(32,36,46,0.92)", "lblshadow": "0 4px 14px rgba(0,0,0,0.35)",
            }
        return {
            "mode": "light",
            "page": "#f1f5f9", "card": "rgba(255,255,255,0.84)",
            "wash": "rgba(255,255,255,0.72)",
            "ink": INK, "muted": MUTED,
            "sep": "rgba(148,163,184,0.25)", "soft": "rgba(99,102,241,0.07)",
            "cardshadow": "0 12px 32px rgba(148,163,184,0.28)",
            "lblbg": "rgba(255,255,255,0.90)", "lblshadow": "0 4px 14px rgba(148,163,184,0.35)",
        }

    def _css(self):
        t = self._theme()
        css = (self._CSS_TPL
               .replace("__FONTSANS__", self._FONT_SANS)
               .replace("__FONTMONO__", self._FONT_MONO)
               .replace("__PAGEPAD__", str(self._PAGE_PAD))
               .replace("__PAGE__", t["page"]).replace("__CARD__", t["card"])
               .replace("__WASH__", t["wash"])
               .replace("__INK__", t["ink"]).replace("__MUTED__", t["muted"])
               .replace("__SEP__", t["sep"]).replace("__SOFT__", t["soft"])
               .replace("__CARDSHADOW__", t["cardshadow"])
               .replace("__LBLBG__", t["lblbg"]).replace("__LBLSHADOW__", t["lblshadow"])
               .replace("__INDIGO__", INDIGO).replace("__VIOLET__", VIOLET)
               .replace("__BLOSSOM__", BLOSSOM).replace("__MINT__", MINT))
        return css, t

    async def _render(self, body_html):
        takumi = self.takumi
        if takumi is None or not hasattr(takumi, "render_html"):
            self.logger.error("Takumi 模块不可用，无法渲染图片")
            return None
        await self._ensure_mascot()
        css, t = self._css()

        layers = ""
        if self._moe_enabled() and self._mascot_data is not None:
            # 萌图背景层与纱罩层
            layers = ("<div class='bg-media'><img src='memory://mascot'/>"
                      "<div class='bg-wash'></div></div>")
        else:
            # 无萌图时使用渐变光斑层
            layers = "<div class='glow glow-a'></div><div class='glow glow-b'></div><div class='glow glow-c'></div>"
        body_html = f"<div class='page'>{layers}<div class='page-content'>{body_html}</div></div>"

        self._schedule_refresh()
        try:
            kwargs = {}
            if self._moe_enabled() and self._mascot_data is not None:
                kwargs["images"] = [("memory://mascot", self._mascot_data)]
            return takumi.render_html(
                body_html, stylesheets=[css],
                width=self.CARD_WIDTH, height=None, lang="zh-CN",
                **kwargs,
            )
        except Exception as e:
            self.logger.error(f"Takumi 渲染失败: {e}")
            return None

    # ------------------------------------------------------------------ 通用部件
    @staticmethod
    def _dist_color(d):
        if d < 0.3:
            return INDIGO
        if d < 0.6:
            return VIOLET
        if d < 0.8:
            return BLOSSOM
        return SLATE

    def _head(self, title, subtitle):
        icon = (
            f"<svg width='30' height='30' viewBox='0 0 30 30' xmlns='http://www.w3.org/2000/svg'>"
            f"<circle cx='15' cy='15' r='3.2' fill='{INDIGO}'/>"
            f"<circle cx='15' cy='15' r='8.5' fill='none' stroke='{INDIGO}' stroke-opacity='0.5' "
            f"stroke-width='2' stroke-dasharray='3.5 4.5' stroke-linecap='round'/>"
            f"<circle cx='15' cy='15' r='13.5' fill='none' stroke='{BLOSSOM}' stroke-opacity='0.55' "
            f"stroke-width='2' stroke-dasharray='2 5.5' stroke-linecap='round'/>"
            f"<circle cx='15' cy='15' r='2' fill='{BLOSSOM}' fill-opacity='0.7' "
            f"transform='translate(9.5,-9.5)'/>"
            f"</svg>"
        )
        return (f"<div class='head-row'><div class='logo-chip'>{icon}</div>"
                f"<div class='head-text'><div class='title'>{self._esc(title)}</div>"
                f"<div class='subtitle'>{self._esc(subtitle)}</div></div></div>")

    @staticmethod
    def _section_label(text):
        wave = (
            "<svg width='34' height='10' viewBox='0 0 34 10' xmlns='http://www.w3.org/2000/svg'>"
            f"<path d='M1 5 Q 5 1, 9 5 T 17 5 T 25 5 T 33 5' fill='none' stroke='{INDIGO}' "
            "stroke-opacity='0.45' stroke-width='2' stroke-linecap='round'/>"
            "</svg>"
        )
        return f"<div class='section-label'>{wave}<span>{text}</span></div>"

    def _card(self, inner, last=False):
        return f"<div class='card{' last' if last else ''}'>{inner}</div>"

    @staticmethod
    def _rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    def _place_labels(self, ordered, node_px, label_of, max_labels=22, char_w=9, pad=18):
        placed = []
        out = {}
        offsets = [(28, -18), (28, 18), (-28, -18), (-28, 18),
                   (0, -30), (0, 30), (34, 0), (-34, 0)]
        for uid in ordered:
            if len(out) >= max_labels:
                break
            nx, ny = node_px[uid]
            text = label_of.get(uid)
            if not text:
                continue
            w = min(len(text), 8) * char_w + pad
            h = 22
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
                f"--lc:{color};color:{color}'>{text}</div>")

    @staticmethod
    def _ring_tag(cx, cy, text):
        return f"<div class='ring-tag' style='left:{cx:.1f}px;top:{cy:.1f}px'>{text}</div>"

    # ------------------------------------------------------------------ SVG 几何
    @staticmethod
    def _convex_hull(points):
        """Andrew 单调链凸包，返回按逆时针序的顶点。"""
        pts = sorted(set(points))
        if len(pts) <= 2:
            return pts

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        lower = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        return lower[:-1] + upper[:-1]

    @staticmethod
    def _expand_hull(hull, pad):
        """将凸包顶点自质心向外扩 pad 像素。"""
        if not hull:
            return hull
        cx = sum(p[0] for p in hull) / len(hull)
        cy = sum(p[1] for p in hull) / len(hull)
        out = []
        for x, y in hull:
            dx, dy = x - cx, y - cy
            d = math.hypot(dx, dy) or 1e-6
            out.append((cx + dx / d * (d + pad), cy + dy / d * (d + pad)))
        return out

    def _edge_path(self, x1, y1, x2, y2, curve):
        """两节点间的弧线（二次贝塞尔），curve 为垂直偏移量。"""
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1e-6
        nx, ny = -dy / length, dx / length
        cx, cy = mx + nx * curve, my + ny * curve
        return f"M{x1:.1f} {y1:.1f} Q{cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}"

    @staticmethod
    def _defs_sonar(t):
        """声呐图共享的渐变与光楔定义。"""
        return (
            "<defs>"
            f"<radialGradient id='sonarGlow' cx='50%' cy='50%' r='50%'>"
            f"<stop offset='0%' stop-color='{INDIGO}' stop-opacity='0.10'/>"
            f"<stop offset='70%' stop-color='{INDIGO}' stop-opacity='0.03'/>"
            f"<stop offset='100%' stop-color='{INDIGO}' stop-opacity='0'/>"
            "</radialGradient>"
            f"<linearGradient id='sweep' x1='0%' y1='0%' x2='100%' y2='0%'>"
            f"<stop offset='0%' stop-color='{INDIGO}' stop-opacity='0.20'/>"
            f"<stop offset='100%' stop-color='{INDIGO}' stop-opacity='0'/>"
            "</linearGradient>"
            f"<linearGradient id='pairFill' x1='0%' y1='0%' x2='100%' y2='100%'>"
            f"<stop offset='0%' stop-color='{INDIGO}' stop-opacity='0.40'/>"
            f"<stop offset='100%' stop-color='{BLOSSOM}' stop-opacity='0.22'/>"
            "</linearGradient>"
            "</defs>"
        )

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

    # ------------------------------------------------------------------ sonar svg
    def _svg_sonar(self, users, matrix, islands, msg_counts, node_px, t):
        """关系图 SVG：软光底 + 扫描光楔 + 圈子凸包软色块 + 弧形连接 + 光晕节点。"""
        island_map = {}
        for idx, island in enumerate(islands):
            color = SONAR_COLORS[idx % len(SONAR_COLORS)]
            for uid in island["members"]:
                island_map[uid] = (idx, color)
        default_color = SLATE
        threshold = self.config.get("distance_threshold", 0.6)
        max_count = max(max(msg_counts.values()) if msg_counts else 1, 1)
        size = self.MAP_SVG
        cxy = size / 2
        radius = size / 2 - 64
        sep = t["sep"]
        node_stroke = "#ffffff" if t["mode"] == "light" else "#20242e"
        edge_index = 0

        svg = [f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}' xmlns='http://www.w3.org/2000/svg'>"]
        svg.append(self._defs_sonar(t))
        # 底光与扫描光楔
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='{radius + 70}' fill='url(#sonarGlow)'/>")
        a0, a1 = math.radians(-150), math.radians(-70)
        r_sweep = radius * 0.92
        p0 = (cxy + r_sweep * math.cos(a0), cxy + r_sweep * math.sin(a0))
        p1 = (cxy + r_sweep * math.cos(a1), cxy + r_sweep * math.sin(a1))
        svg.append(f"<path d='M{cxy} {cxy} L{p0[0]:.1f} {p0[1]:.1f} "
                   f"A{r_sweep:.1f} {r_sweep:.1f} 0 0 1 {p1[0]:.1f} {p1[1]:.1f} Z' "
                   f"fill='url(#sweep)'/>")
        # 距离环（虚线）
        for r_frac, op in ((0.3, 0.9), (0.6, 0.65), (0.9, 0.4)):
            svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='{radius * r_frac:.1f}' fill='none' "
                       f"stroke='{sep}' stroke-opacity='{op}' stroke-width='1.4' stroke-dasharray='5 7'/>")
        # 中心十字准星
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='4' fill='{INDIGO}'/>")
        for dx_a, dy_a in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            svg.append(f"<line x1='{cxy + 8 * dx_a:.1f}' y1='{cxy + 8 * dy_a:.1f}' "
                       f"x2='{cxy + 15 * dx_a:.1f}' y2='{cxy + 15 * dy_a:.1f}' "
                       f"stroke='{INDIGO}' stroke-opacity='0.45' stroke-width='1.6' stroke-linecap='round'/>")

        # 社交圈软色凸包（>=3 人）或双人气囊（=2 人）
        for idx, island in enumerate(islands):
            members = [m for m in island["members"] if m in node_px]
            if len(members) < 2:
                continue
            color = SONAR_COLORS[idx % len(SONAR_COLORS)]
            if len(members) >= 3:
                hull = self._expand_hull(self._convex_hull([node_px[m] for m in members]), 30)
                pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in hull)
                svg.append(f"<polygon points='{pts}' fill='{color}' fill-opacity='0.08' "
                           f"stroke='{color}' stroke-opacity='0.32' stroke-width='1.6' "
                           f"stroke-dasharray='7 7' stroke-linejoin='round'/>")
            else:
                (x1, y1), (x2, y2) = node_px[members[0]], node_px[members[1]]
                svg.append(f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
                           f"stroke='{color}' stroke-opacity='0.10' stroke-width='58' stroke-linecap='round'/>")

        # 弧形连接线：同圈用圈色，跨圈用灰色
        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                dist = matrix.get(f"{users[i]}|{users[j]}", 1.0)
                if dist >= threshold:
                    continue
                x1, y1 = node_px[users[i]]
                x2, y2 = node_px[users[j]]
                alpha = max(0.16, min(0.65, (1.0 - dist) * 0.85))
                ic1 = island_map.get(users[i], (0, default_color))[1]
                ic2 = island_map.get(users[j], (0, default_color))[1]
                lc = ic1 if ic1 == ic2 else SLATE
                edge_index += 1
                curve = min(26, math.hypot(x2 - x1, y2 - y1) * 0.12) * (1 if edge_index % 2 else -1)
                path = self._edge_path(x1, y1, x2, y2, curve)
                if dist < 0.3:  # dist < 0.3 时加宽描边衬底
                    svg.append(f"<path d='{path}' fill='none' stroke='{lc}' stroke-opacity='0.14' stroke-width='7' stroke-linecap='round'/>")
                svg.append(f"<path d='{path}' fill='none' stroke='{lc}' stroke-opacity='{alpha:.2f}' "
                           f"stroke-width='1.8' stroke-linecap='round'/>")

        # 节点：光晕、主体、高光点
        for uid in users:
            x, y = node_px[uid]
            color = island_map.get(uid, (0, default_color))[1]
            r_node = 8 + (msg_counts.get(uid, 1) / max_count) * 14
            svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r_node + 9:.1f}' fill='{color}' fill-opacity='0.18'/>")
            svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r_node:.1f}' fill='{color}' "
                       f"stroke='{node_stroke}' stroke-width='2.5'/>")
            svg.append(f"<circle cx='{x - r_node * 0.3:.1f}' cy='{y - r_node * 0.3:.1f}' "
                       f"r='{max(1.6, r_node * 0.24):.1f}' fill='#ffffff' fill-opacity='0.75'/>")
        svg.append("</svg>")
        return "".join(svg), island_map, cxy, radius

    # ------------------------------------------------------------------ sonar
    async def render_sonar(self, *, users, matrix, islands, nicknames=None,
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
        radius = size / 2 - 64
        node_px = {uid: (cxy + coords[uid][0] * radius, cxy + coords[uid][1] * radius) for uid in users}

        svg_shapes, island_map, _, _ = self._svg_sonar(users, matrix, islands, msg_counts, node_px, t)
        default_color = SLATE
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

        # 右侧栏：圈子与独立用户（卡片按圈色着色）
        rail_items = []
        island_items = []
        for i, (name, isl) in enumerate(real_islands):
            color = SONAR_COLORS[i % len(SONAR_COLORS)]
            members_str = self._esc("、".join(self._strip_emoji(nicknames.get(m, m)) for m in isl["members"][:14]))
            island_items.append(
                f"<div class='island' style='background:{self._rgba(color, 0.08)}'>"
                f"<div class='name'>{self._esc(name)}</div>"
                f"<div class='meta'>{isl['size']} 人 · 平均距离 {isl['avg_distance']}</div>"
                f"<div class='members'>{members_str}</div></div>")
        if island_items:
            rail_items.append(self._section_label("社交圈 Social Circles"))
            rail_items.extend(island_items)
        if lone:
            lone_names = self._esc("、".join(self._strip_emoji(nicknames.get(u, u)) for u in lone[:24]))
            extra = f" 等 {len(lone)} 人" if len(lone) > 24 else ""
            rail_items.append(f"<div class='lone'><b>独立用户</b> · {len(lone)} 人"
                              f"<br>{lone_names}{extra}</div>")

        if rail_items:
            map_card = (f"<div class='map-row'><div class='map-col'>{stage}</div>"
                        f"<div class='rail'>{''.join(rail_items)}</div></div>")
        else:
            map_card = f"<div class='map-wrap'>{stage}</div>"

        cards = [
            self._head("群聊社交声呐", "Group Chat Social Sonar Map") + "<div class='divider'></div>" + chips,
            map_card,
        ]
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        body += (f"<div class='foot'>用 <code>{self._esc(command_prefix)}亲密度 @某人</code> 查看具体距离"
                 f" · 本群 {local_total} / 全局 {global_total} 条消息</div>")
        return await self._render(body)

    # ------------------------------------------------------------------ intimacy
    async def render_intimacy(self, *, nickname_a, nickname_b, dist, dist_label, scores,
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
        svg.append(self._defs_sonar(t))
        # 网格：最外圈淡靛蓝填充 + 虚线环
        for idx, frac in enumerate((0.25, 0.5, 0.75, 1.0)):
            pts = " ".join(f"{c + R * frac * math.cos(a):.1f},{c + R * frac * math.sin(a):.1f}" for a in angles)
            fill = f" fill='{INDIGO}' fill-opacity='0.03'" if idx == 3 else ""
            dash = "" if idx == 3 else " stroke-dasharray='4 6'"
            svg.append(f"<polygon points='{pts}' fill='none' stroke='{sep}' stroke-width='1.2'{dash}{fill}/>"
                       if not fill else
                       f"<polygon points='{pts}'{fill} stroke='{sep}' stroke-width='1.2'/>")
        for a in angles:
            svg.append(f"<line x1='{c}' y1='{c}' x2='{c + R * math.cos(a):.1f}' y2='{c + R * math.sin(a):.1f}' "
                       f"stroke='{sep}' stroke-width='1' stroke-dasharray='4 6'/>")
        # 数据多边形：靛蓝→樱花渐变填充，顶点光晕
        data_pts = " ".join(f"{c + R * v * math.cos(a):.1f},{c + R * v * math.sin(a):.1f}" for a, v in zip(angles, values))
        svg.append(f"<polygon points='{data_pts}' fill='url(#pairFill)' stroke='{INDIGO}' stroke-width='2.2' stroke-linejoin='round'/>")
        for a, v in zip(angles, values):
            vx, vy = c + R * v * math.cos(a), c + R * v * math.sin(a)
            svg.append(f"<circle cx='{vx:.1f}' cy='{vy:.1f}' r='10' fill='{INDIGO}' fill-opacity='0.18'/>")
            svg.append(f"<circle cx='{vx:.1f}' cy='{vy:.1f}' r='4.5' fill='{INDIGO}' stroke='#ffffff' stroke-width='1.8'/>")
        svg.append("</svg>")
        overlays = ""
        for a, v, lab in zip(angles, values, labels):
            vx, vy = c + R * v * math.cos(a), c + R * v * math.sin(a)
            overlays += self._label_div(vx, vy - 16, f"{int(v * 100)}%", INDIGO)
            overlays += self._label_div(c + (R + 30) * math.cos(a), c + (R + 30) * math.sin(a), self._esc(lab), t["ink"])
        stage = f"<div class='stage' style='width:{size}px;height:{size}px'>{ ''.join(svg)}{overlays}</div>"

        dim_rows = []
        for label, val in zip(labels, values):
            dc = self._dist_color(val)
            dim_rows.append(
                f"<div class='dim' style='--c:{dc}'><div class='nm'>{label}</div>"
                f"<div class='bar'><i style='width:{val*100:.1f}%'></i></div>"
                f"<div class='pct'>{val*100:.0f}%</div></div>")

        # 头像对 + 心形连接（颜色随距离）
        heart = (
            f"<svg width='26' height='24' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>"
            f"<path d='M12 21s-7.5-4.6-10-9.3C.6 8.9 2.3 5 6 5c2.2 0 3.7 1.2 4.6 2.5L12 9l1.4-1.5C14.3 6.2 15.8 5 18 5"
            f"c3.7 0 5.4 3.9 4 6.7C19.5 16.4 12 21 12 21z' fill='{dist_color}' fill-opacity='0.9'/>"
            f"<circle cx='5' cy='7' r='1.4' fill='{dist_color}' fill-opacity='0.4'/>"
            f"<circle cx='19.5' cy='6.2' r='1' fill='{dist_color}' fill-opacity='0.35'/></svg>"
        )
        pair = (f"<div class='pair-row' style='--dc:{dist_color}'>"
                f"<div class='pair-names'><span class='n'>{self._esc(self._strip_emoji(nickname_a))}</span>"
                f"{heart}"
                f"<span class='n'>{self._esc(self._strip_emoji(nickname_b))}</span></div>"
                f"<div class='dist-badge' style='background:{self._rgba(dist_color, 0.10)}'>"
                f"<div class='v'>{dist:.2f}</div>"
                f"<div class='l'>{self._esc(dist_label)}</div></div></div>")

        dim_extra = ""
        if interact and (interact.get("reply_total", 0) > 0 or cooccur_count > 0):
            pills = []
            if interact.get("a_to_b", 0) or interact.get("b_to_a", 0):
                pills.append(f"<div class='pill'>@互动 <b>{interact['a_to_b'] + interact['b_to_a']}</b> 次</div>")
                pills.append(f"<div class='pill'>回复合计 <b>{interact.get('reply_total', 0)}</b> 次</div>")
            if cooccur_count > 0:
                pills.append(f"<div class='pill'>同时在线 <b>{cooccur_count}</b> 次</div>")
            dim_extra += f"<div class='kv' style='margin-top:16px'>{''.join(pills)}</div>"
        if rank:
            dim_extra += f"<div class='note' style='margin-top:12px'>你们是本群第 <b>{rank}</b> 亲密的组合</div>"

        cards = [
            self._head("亲密度报告", "Intimacy Analysis") + "<div class='divider'></div>" + pair,
            f"<div class='radar-wrap'>{stage}</div>",
            self._section_label("五维相似度 Dimensions") + f"<div class='dim-grid'>{''.join(dim_rows)}</div>{dim_extra}",
        ]
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        return await self._render(body)

    # ------------------------------------------------------------------ personal radar
    async def render_personal_radar(self, *, user_id, distances, nicknames=None,
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
        radius = size / 2 - 64
        dist_scale = self.config.get("radar_distance_scale", 1.2)
        max_radius = self.config.get("radar_max_radius", 1.1)
        n = len(others)
        my_name = self._strip_emoji(nicknames.get(user_id, user_id))
        sep = t["sep"]
        node_px = {}
        svg = [f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}' xmlns='http://www.w3.org/2000/svg'>"]
        svg.append(self._defs_sonar(t))
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='{radius + 60}' fill='url(#sonarGlow)'/>")
        for r_frac, op in ((0.3, 0.9), (0.6, 0.65), (0.9, 0.4)):
            svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='{radius * r_frac:.1f}' fill='none' "
                       f"stroke='{sep}' stroke-opacity='{op}' stroke-width='1.4' stroke-dasharray='5 7'/>")
        for i, uid in enumerate(others):
            dist = distances[uid]["distance"]
            ang = 2 * math.pi * i / n
            r = min(dist * dist_scale, max_radius) * radius
            x, y = cxy + r * math.cos(ang), cxy + r * math.sin(ang)
            node_px[uid] = (x, y)
            color = self._dist_color(dist)
            node_r = 6 + max(0.0, (1.0 - dist)) * 11
            svg.append(f"<line x1='{cxy}' y1='{cxy}' x2='{x:.1f}' y2='{y:.1f}' "
                       f"stroke='{color}' stroke-opacity='0.30' stroke-width='1.2' stroke-dasharray='3 5'/>")
            svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{node_r + 7:.1f}' fill='{color}' fill-opacity='0.16'/>")
            svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{node_r:.1f}' fill='{color}' "
                       f"stroke='#ffffff' stroke-width='2'/>")
        # 中心「我」：三层光环
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='26' fill='{INDIGO}' fill-opacity='0.08'/>")
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='17' fill='{INDIGO}' fill-opacity='0.16'/>")
        svg.append(f"<circle cx='{cxy}' cy='{cxy}' r='10' fill='{INDIGO}' stroke='#ffffff' stroke-width='2.5'/>")
        svg.append("</svg>")
        label_of = {uid: f"{self._strip_emoji(nicknames.get(uid, uid))} {distances[uid]['distance']:.2f}" for uid in others}
        labels = self._place_labels(others, node_px, label_of, max_labels=24, char_w=8)
        label_html = "".join(
            self._label_div(cx, cy, self._esc(txt), self._dist_color(distances[uid]["distance"]))
            for uid, (cx, cy, txt) in labels.items())
        ring_tags = "".join(self._ring_tag(cxy + radius * f, cxy, lab)
                            for f, lab in [(0.3, "内圈"), (0.6, "中圈"), (0.9, "外圈")])
        me_tag = self._label_div(cxy, cxy + 30, self._esc(my_name[:10]), INDIGO)
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
            color = RING_COLORS[key]
            names = self._esc("  ".join(f"{nm}({dd:.2f})" for nm, dd in items[:16]))
            ring_items.append(
                f"<div class='island' style='background:{self._rgba(color, 0.08)}'>"
                f"<div class='name'>{lab} "
                f"<span style='color:{t['muted']};font-size:12px;font-weight:400'> {rng} · {len(items)}人</span></div>"
                f"<div class='members'>{names}</div></div>")

        chips = (f"<div class='chips'><div class='chip'><b>{global_count}</b>全局消息</div>"
                 f"<div class='chip violet'><b>{presence}</b>本群消息</div>"
                 f"<div class='chip pink'><b>{len(others)}</b>联系人</div></div>")

        if ring_items:
            map_card = (f"<div class='map-row'><div class='map-col'>{stage}</div>"
                        f"<div class='rail'>{self._section_label('距离分布 Distance Rings')}"
                        f"{''.join(ring_items)}</div></div>")
        else:
            map_card = f"<div class='map-wrap'>{stage}</div>"

        cards = [
            self._head(f"{my_name} 的社交雷达", "Personal Social Radar") + "<div class='divider'></div>" + chips,
            map_card,
        ]
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        return await self._render(body)

    # ------------------------------------------------------------------ profile
    async def render_profile(self, *, nickname, global_count, groups=None, tags="",
                             peak_period="", top_emoji=None):
        groups = groups or []
        top_emoji = top_emoji or []
        name = self._strip_emoji(nickname)
        chips = (f"<div class='chips'><div class='chip'><b>{global_count}</b>消息</div>"
                 f"<div class='chip violet'><b>{len(groups)}</b>活跃群</div></div>")

        # 头像 chip（昵称首字）+ 标题
        initial = self._esc(name[:1]) if name else "?"
        avatar = f"<div class='avatar-chip' style='--ac:{INDIGO}'>{initial}</div>"
        head = (f"<div class='head-row'>{avatar}"
                f"<div class='head-text'><div class='title'>{self._esc(name)} 的全局档案</div>"
                f"<div class='subtitle'>Global Profile</div></div></div>"
                f"<div class='divider'></div>{chips}")

        blocks = head
        if tags:
            blocks += (f"<div class='tags' style='margin-top:18px'>"
                       f"{''.join(self._tag(x) for x in tags.split('/') if x.strip())}</div>")
        kv = ""
        if peak_period:
            kv += f"<div class='pill'>活跃时段 <b>{self._esc(peak_period)}</b></div>"
        if top_emoji:
            kv += f"<div class='pill'>常用表情 <b>{' '.join(self._esc(e) for e, _ in top_emoji[:5])}</b></div>"
        if kv:
            blocks += f"<div class='kv' style='margin-top:16px'>{kv}</div>"
        if groups:
            items = "".join(f"<div class='pill'>[{self._esc(p)}] {self._esc(g)}: <b>{c}</b>条</div>" for p, g, c in groups)
            blocks += (self._section_label("群聊分布 Groups") + f"<div class='kv'>{items}</div>")
        body = self._card(blocks, last=True)
        return await self._render(body)

    def _tag(self, x):
        return f"<span class='tag'>{self._esc(x.strip())}</span>"

    # ------------------------------------------------------------------ parallel
    async def render_parallel(self, *, my_name, local=None, cross=None, command_prefix="/"):
        local = local or None
        cross = cross or []
        cards = [self._head("正在寻找另一个你...", "Parallel Self")]
        if local:
            tname = self._strip_emoji(local.get("nickname", local["user_id"]))
            sim = int(local["similarity"] * 100)
            checks = ""
            for dim, label in [("timing", "活跃时段"), ("vocab", "消息风格"), ("emoji", "表情偏好")]:
                val = local.get("scores", {}).get(dim, 0)
                checks += (f"<div class='dim' style='--c:{INDIGO}'><div class='nm'>{label}</div>"
                           f"<div class='bar'><i style='width:{val*100:.1f}%'></i></div>"
                           f"<div class='pct'>{val*100:.0f}%</div></div>")
            # 镜像对：两枚头像 chip 由虚线连起，中点放相似度徽章
            badge_bg = f"linear-gradient(90deg, {INDIGO}, {BLOSSOM})"
            mirror = (
                f"<div class='mirror'>"
                f"<div class='avatar-chip' style='--ac:{INDIGO}'>{self._esc(self._strip_emoji(my_name)[:1])}</div>"
                f"<div class='m-line'></div>"
                f"<div style='flex:0 0 auto;padding:8px 20px;border-radius:999px;background:{badge_bg};"
                f"color:#ffffff;font-weight:700;font-size:16px;"
                f"box-shadow:0 8px 20px rgba(99,102,241,0.25)'>{sim}%</div>"
                f"<div class='m-line'></div>"
                f"<div class='avatar-chip' style='--ac:{BLOSSOM};"
                f"background:{self._rgba(BLOSSOM, 0.10)};border-color:{self._rgba(BLOSSOM, 0.30)};"
                f"color:{BLOSSOM}'>{self._esc(tname[:1])}</div>"
                f"</div>"
            )
            cards.append(
                f"{mirror}"
                f"<div style='text-align:center;font-size:14px;color:{MUTED};margin-bottom:18px'>"
                f"{self._esc(self._strip_emoji(my_name))} ↔ {self._esc(tname)} · 本群匹配</div>"
                f"<div class='dim-grid'>{checks}</div>"
                f"<div class='note' style='margin-top:12px'>试试 <b>{self._esc(command_prefix)}亲密度 @{self._esc(tname)}</b> 看看详细距离</div>")
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
                items += (f"<div class='cross-row'><div class='name-row'>"
                          f"<span class='plat'>{self._esc(platform_name)}</span>"
                          f"<span class='name'>{self._esc(label)}</span>"
                          f"<span class='sim'>· {sim}%</span></div>{det}</div>")
            cards.append(f"<div style='margin-top:4px'>"
                         + self._section_label(f"跨群匹配 Cross-Scope ({len(cross)})")
                         + f"<div style='display:flex;flex-direction:column;gap:12px'>{items}</div></div>")
        if len(cards) == 1:
            cards.append("<div class='empty'>没有找到另一个你<br>（可能你和所有人都互动过了）</div>")
        body = "".join(self._card(c, last=(i == len(cards) - 1)) for i, c in enumerate(cards))
        body += f"<div class='foot'>用 <code>{self._esc(command_prefix)}亲密度 @某人</code> 查看具体距离</div>"
        return await self._render(body)
