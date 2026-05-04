from typing import Dict, List, Optional


class SonarTemplates:
    PRIMARY_COLOR = "#00ff88"
    ACCENT_COLOR = "#00bbff"
    WARNING_COLOR = "#ffaa00"
    ERROR_COLOR = "#ff4466"
    SECONDARY_COLOR = "#8888aa"
    DARK_BG = "rgba(10, 10, 26, 0.95)"
    CARD_BG = "rgba(20, 20, 40, 0.8)"

    RING_COLORS = {
        "inner": "#00ff88",
        "middle": "#00bbff",
        "outer": "#ffaa00",
        "dark": "#ff4466",
    }

    RING_LABELS = {
        "inner": ("内圈", "< 0.3"),
        "middle": ("中圈", "0.3 ~ 0.6"),
        "outer": ("外圈", "0.6 ~ 0.8"),
        "dark": ("暗区", "> 0.8"),
    }

    DIM_NAMES = {
        "timing": "时段重叠",
        "emoji": "表情相似",
        "vocab": "词汇相似",
        "interaction": "直接互动",
        "cooccurrence": "共现频率",
    }

    @classmethod
    def _bar_html(cls, value: float, color: str, width: int = 120) -> str:
        pct = int(value * 100)
        return (
            f'<div style="display:inline-block;width:{width}px;height:8px;'
            f'background:rgba(255,255,255,0.08);border-radius:4px;vertical-align:middle;">'
            f'<div style="width:{pct}%;height:100%;background:{color};border-radius:4px;"></div>'
            f'</div>'
        )

    @classmethod
    def _ring_details_html(cls, ring_key: str, items: list) -> str:
        if not items:
            return ""
        color = cls.RING_COLORS[ring_key]
        label, range_desc = cls.RING_LABELS[ring_key]
        count = len(items)
        names_html = "  ".join(
            f'<span style="margin-right:10px;font-size:12px;">{n} <span style="color:{cls.SECONDARY_COLOR};">({d:.2f})</span></span>'
            for n, d in items
        )
        return (
            f'<details style="margin-bottom:6px;">'
            f'<summary style="cursor:pointer;font-size:13px;padding:4px 8px;'
            f'background:rgba(255,255,255,0.03);border-radius:4px;'
            f'border-left:3px solid {color};">'
            f'<span style="color:{color};font-weight:bold;">{label}</span>'
            f' <span style="color:{cls.SECONDARY_COLOR};font-size:11px;">{range_desc}</span>'
            f' <span style="font-size:12px;">({count}人)</span>'
            f'</summary>'
            f'<div style="padding:6px 8px 6px 12px;display:flex;flex-wrap:wrap;gap:4px 0;">'
            f'{names_html}'
            f'</div></details>'
        )

    @classmethod
    def build_radar_group(cls, global_count: int, presence: int,
                          rings: Dict[str, list], tags: str = "") -> Dict[str, str]:
        html = cls._build_radar_group_html(global_count, presence, rings, tags)
        markdown = cls._build_radar_group_markdown(global_count, presence, rings, tags)
        text = cls._build_radar_group_text(global_count, presence, rings, tags)
        return {"html": html, "markdown": markdown, "text": text}

    @classmethod
    def _build_radar_group_html(cls, global_count, presence, rings, tags) -> str:
        stats_html = (
            f'<div style="padding:6px 10px;background:rgba(0,255,136,0.06);'
            f'border-radius:6px;margin-bottom:10px;font-size:12px;">'
            f'全局消息: <b>{global_count}</b> 条 | 本群消息: <b>{presence}</b> 条'
            f'</div>'
        )

        rings_html = ""
        for key in ("inner", "middle", "outer", "dark"):
            rings_html += cls._ring_details_html(key, rings.get(key, []))

        tags_html = ""
        if tags:
            tags_html = (
                f'<div style="margin-top:8px;font-size:12px;">'
                f'<span style="color:{cls.ACCENT_COLOR};">社交标签:</span> {tags}'
                f'</div>'
            )

        return (
            f'<div style="padding:12px;border-radius:8px;background:{cls.DARK_BG};'
            f'color:#ccd;">'
            f'<div style="color:{cls.PRIMARY_COLOR};font-size:15px;font-weight:bold;margin-bottom:10px;">'
            f'你的社交雷达</div>'
            f'{stats_html}'
            f'{rings_html}'
            f'{tags_html}'
            f'</div>'
        )

    @classmethod
    def _build_radar_group_markdown(cls, global_count, presence, rings, tags) -> str:
        lines = [
            "**你的社交雷达**",
            "",
            f"全局消息: **{global_count}** 条 | 本群消息: **{presence}** 条",
            "",
        ]
        for key in ("inner", "middle", "outer", "dark"):
            items = rings.get(key, [])
            if not items:
                continue
            label, range_desc = cls.RING_LABELS[key]
            lines.append(f"**{label}** ({range_desc}, {len(items)}人)")
            for name, d in items:
                lines.append(f"  - {name} ({d:.2f})")
            lines.append("")
        if tags:
            lines.append(f"社交标签: {tags}")
        return "\n".join(lines)

    @classmethod
    def _build_radar_group_text(cls, global_count, presence, rings, tags) -> str:
        lines = [
            "你的社交雷达",
            "----------",
            f"全局消息: {global_count} 条 | 本群消息: {presence} 条",
            "",
        ]
        for key in ("inner", "middle", "outer", "dark"):
            items = rings.get(key, [])
            if not items:
                continue
            label, range_desc = cls.RING_LABELS[key]
            lines.append(f"{label} ({range_desc})")
            for name, d in items:
                lines.append(f"  {name} ({d:.2f})")
            lines.append("")
        if tags:
            lines.append(f"社交标签: {tags}")
        return "\n".join(lines)

    @classmethod
    def _split_islands(cls, islands, island_names, drifters, nicknames):
        real_islands = []
        lone_users = list(drifters)
        for idx, island in enumerate(islands):
            if island["size"] >= 2:
                name = island_names[idx] if idx < len(island_names) else f"岛屿{idx + 1}"
                real_islands.append((name, island))
            else:
                lone_users.extend(island["members"])
        return real_islands, lone_users

    @classmethod
    def build_sonar(cls, global_total: int, local_total: int, user_count: int,
                    island_count: int, islands: list, island_names: list,
                    drifters: list, nicknames: dict, prefix: str = "/") -> Dict[str, str]:
        real_islands, lone_users = cls._split_islands(islands, island_names, drifters, nicknames)
        real_count = len(real_islands)

        html = cls._build_sonar_html(global_total, local_total, user_count,
                                     real_count, real_islands, lone_users, nicknames, prefix)
        markdown = cls._build_sonar_markdown(global_total, local_total, user_count,
                                             real_count, real_islands, lone_users, nicknames, prefix)
        text = cls._build_sonar_text(global_total, local_total, user_count,
                                     real_count, real_islands, lone_users, nicknames, prefix)
        return {"html": html, "markdown": markdown, "text": text}

    @classmethod
    def _build_sonar_html(cls, global_total, local_total, user_count,
                          real_count, real_islands, lone_users, nicknames, prefix) -> str:
        lone_count = len(lone_users)
        stats = (
            f'覆盖 <b>{user_count}</b> 位用户，'
            f'检测到 <b>{real_count}</b> 个社交圈'
        )
        if lone_count > 0:
            stats += f'，<b>{lone_count}</b> 位独立用户'

        islands_html = ""
        for name, island in real_islands:
            members_str = "、".join(nicknames.get(m, m) for m in island["members"])
            islands_html += (
                f'<details style="margin-bottom:6px;">'
                f'<summary style="cursor:pointer;font-size:13px;padding:4px 8px;'
                f'background:rgba(255,255,255,0.03);border-radius:4px;'
                f'border-left:3px solid {cls.PRIMARY_COLOR};">'
                f'<b>{name}</b> · {island["size"]}人 · 距离 {island["avg_distance"]}'
                f'</summary>'
                f'<div style="padding:6px 8px 6px 12px;font-size:12px;color:{cls.SECONDARY_COLOR};">'
                f'{members_str}'
                f'</div></details>'
            )

        lone_html = ""
        if lone_users:
            lone_names = "、".join(nicknames.get(u, u) for u in lone_users)
            lone_html = (
                f'<details style="margin-bottom:6px;">'
                f'<summary style="cursor:pointer;font-size:13px;padding:4px 8px;'
                f'background:rgba(255,255,255,0.03);border-radius:4px;'
                f'border-left:3px solid {cls.SECONDARY_COLOR};">'
                f'独立用户 · {lone_count}人'
                f'</summary>'
                f'<div style="padding:6px 8px 6px 12px;font-size:12px;color:{cls.SECONDARY_COLOR};">'
                f'{lone_names}'
                f'</div></details>'
            )

        return (
            f'<div style="padding:12px;border-radius:8px;background:{cls.DARK_BG};color:#ccd;">'
            f'<div style="color:{cls.PRIMARY_COLOR};font-size:15px;font-weight:bold;margin-bottom:10px;">'
            f'声呐扫描完成</div>'
            f'<div style="padding:6px 10px;background:rgba(0,255,136,0.06);'
            f'border-radius:6px;margin-bottom:10px;font-size:12px;">{stats}</div>'
            f'{islands_html}{lone_html}'
            f'<div style="margin-top:8px;font-size:11px;color:{cls.SECONDARY_COLOR};">'
            f'用 {prefix}亲密度 @某人 查看具体距离</div>'
            f'</div>'
        )

    @classmethod
    def _build_sonar_markdown(cls, global_total, local_total, user_count,
                              real_count, real_islands, lone_users, nicknames, prefix) -> str:
        lines = [
            "**声呐扫描完成**",
            "",
            f"覆盖 **{user_count}** 位用户，检测到 **{real_count}** 个社交圈",
            "",
        ]
        for name, island in real_islands:
            members_str = "、".join(nicknames.get(m, m) for m in island["members"])
            lines.append(f"**{name}** ({island['size']}人) 距离: {island['avg_distance']}")
            lines.append(f"  {members_str}")
            lines.append("")
        if lone_users:
            lone_names = "、".join(nicknames.get(u, u) for u in lone_users)
            lines.append(f"**独立用户** ({len(lone_users)}人)")
            lines.append(f"  {lone_names}")
            lines.append("")
        lines.append(f"用 `{prefix}亲密度 @某人` 查看具体距离")
        return "\n".join(lines)

    @classmethod
    def _build_sonar_text(cls, global_total, local_total, user_count,
                          real_count, real_islands, lone_users, nicknames, prefix) -> str:
        lines = [
            "声呐扫描完成",
            "----------",
            f"覆盖 {user_count} 位用户，检测到 {real_count} 个社交圈",
            "",
        ]
        for name, island in real_islands:
            members_str = "、".join(nicknames.get(m, m) for m in island["members"])
            lines.append(f"{name}({island['size']}人)")
            lines.append(f"  {members_str}")
            lines.append(f"  距离: {island['avg_distance']}")
            lines.append("")
        if lone_users:
            lone_names = "、".join(nicknames.get(u, u) for u in lone_users)
            lines.append(f"独立用户({len(lone_users)}人)")
            lines.append(f"  {lone_names}")
            lines.append("")
        lines.append(f"用 {prefix}亲密度 @某人 查看具体距离")
        return "\n".join(lines)

    @classmethod
    def build_ping(cls, nickname_a: str, nickname_b: str, dist: float, dist_label: str,
                   scores: dict, interact: Optional[dict] = None,
                   cooccur_count: int = 0, rank: Optional[int] = None,
                   prefix: str = "/") -> Dict[str, str]:
        html = cls._build_ping_html(nickname_a, nickname_b, dist, dist_label,
                                    scores, interact, cooccur_count, rank, prefix)
        markdown = cls._build_ping_markdown(nickname_a, nickname_b, dist, dist_label,
                                            scores, interact, cooccur_count, rank, prefix)
        text = cls._build_ping_text(nickname_a, nickname_b, dist, dist_label,
                                    scores, interact, cooccur_count, rank, prefix)
        return {"html": html, "markdown": markdown, "text": text}

    @classmethod
    def _build_ping_html(cls, nickname_a, nickname_b, dist, dist_label,
                         scores, interact, cooccur_count, rank, prefix) -> str:
        dist_color = cls.RING_COLORS["inner"] if dist < 0.3 else \
                     cls.RING_COLORS["middle"] if dist < 0.6 else \
                     cls.RING_COLORS["outer"] if dist < 0.8 else cls.RING_COLORS["dark"]

        dims_html = ""
        for dim, label in cls.DIM_NAMES.items():
            val = scores.get(dim, 0)
            pct = int(val * 100)
            filled = int(val * 10)
            bar = "█" * filled + "░" * (10 - filled)
            dims_html += (
                f'<div style="margin-bottom:4px;font-size:12px;">'
                f'{label}  {bar} {pct}%'
                f'</div>'
            )

        interact_html = ""
        has_interact = interact and (interact.get("reply_total", 0) > 0 or cooccur_count > 0)
        if has_interact:
            items = []
            if interact["a_to_b"] > 0 or interact["b_to_a"] > 0:
                items.append(f'你 @了TA {interact["a_to_b"]} 次')
                items.append(f'TA @了你 {interact["b_to_a"]} 次')
                items.append(f'互相回复 {interact["reply_total"]} 次')
            if interact.get("shared_hours"):
                hours_str = ", ".join(f"{h}:00" for h in interact["shared_hours"][:4])
                items.append(f'共同活跃时段: {hours_str}')
            if cooccur_count > 0:
                items.append(f'共现次数: {cooccur_count}')
            interact_items = "<br>".join(items)
            interact_html = (
                f'<details style="margin-top:8px;">'
                f'<summary style="cursor:pointer;font-size:12px;color:{cls.SECONDARY_COLOR};">'
                f'互动记录</summary>'
                f'<div style="padding:6px 8px;font-size:12px;">{interact_items}</div>'
                f'</details>'
            )

        rank_html = ""
        if rank:
            rank_html = (
                f'<div style="margin-top:8px;font-size:12px;">'
                f'你们是本群第 <b style="color:{cls.PRIMARY_COLOR};">{rank}</b> 亲密的组合'
                f'</div>'
            )

        return (
            f'<div style="padding:12px;border-radius:8px;background:{cls.DARK_BG};color:#ccd;">'
            f'<div style="color:{cls.PRIMARY_COLOR};font-size:15px;font-weight:bold;margin-bottom:10px;">'
            f'亲密度报告</div>'
            f'<div style="font-size:13px;margin-bottom:8px;">'
            f'<b>{nickname_a}</b> <span style="color:{dist_color};">&lt;-&gt;</span> <b>{nickname_b}</b>'
            f'</div>'
            f'<div style="font-size:13px;margin-bottom:10px;">'
            f'综合距离: <b style="color:{dist_color};">{dist:.2f}</b> ({dist_label})</div>'
            f'{dims_html}'
            f'{interact_html}{rank_html}'
            f'</div>'
        )

    @classmethod
    def _build_ping_markdown(cls, nickname_a, nickname_b, dist, dist_label,
                             scores, interact, cooccur_count, rank, prefix) -> str:
        lines = [
            "**亲密度报告**",
            "",
            f"**{nickname_a}** <-> **{nickname_b}**",
            f"综合距离: **{dist:.2f}** ({dist_label})",
            "",
        ]
        for dim, label in cls.DIM_NAMES.items():
            val = scores.get(dim, 0)
            pct = int(val * 100)
            filled = int(val * 10)
            bar = "█" * filled + "░" * (10 - filled)
            lines.append(f"{label}  {bar} {pct}%")
        has_interact = interact and (interact.get("reply_total", 0) > 0 or cooccur_count > 0)
        if has_interact:
            lines.append("")
            lines.append("**互动记录:**")
            if interact["a_to_b"] > 0 or interact["b_to_a"] > 0:
                lines.append(f"- 你 @了TA {interact['a_to_b']} 次")
                lines.append(f"- TA @了你 {interact['b_to_a']} 次")
                lines.append(f"- 互相回复 {interact['reply_total']} 次")
            if interact.get("shared_hours"):
                hours_str = ", ".join(f"{h}:00" for h in interact["shared_hours"][:4])
                lines.append(f"- 共同活跃时段: {hours_str}")
            if cooccur_count > 0:
                lines.append(f"- 共现次数: {cooccur_count}")
        if rank:
            lines.append(f"\n你们是本群第 **{rank}** 亲密的组合")
        return "\n".join(lines)

    @classmethod
    def _build_ping_text(cls, nickname_a, nickname_b, dist, dist_label,
                         scores, interact, cooccur_count, rank, prefix) -> str:
        lines = [
            "亲密度报告",
            "----------",
            f"{nickname_a} <-> {nickname_b}",
            f"综合距离: {dist:.2f} ({dist_label})",
            "",
        ]
        for dim, label in cls.DIM_NAMES.items():
            val = scores.get(dim, 0)
            pct = int(val * 100)
            filled = int(val * 10)
            bar = "█" * filled + "░" * (10 - filled)
            lines.append(f"{label}  {bar} {pct}%")
        has_interact = interact and (interact.get("reply_total", 0) > 0 or cooccur_count > 0)
        if has_interact:
            lines.append("")
            lines.append("互动记录:")
            if interact["a_to_b"] > 0 or interact["b_to_a"] > 0:
                lines.append(f"- 你 @了TA {interact['a_to_b']} 次")
                lines.append(f"- TA @了你 {interact['b_to_a']} 次")
                lines.append(f"- 互相回复 {interact['reply_total']} 次")
            if interact.get("shared_hours"):
                hours_str = ", ".join(f"{h}:00" for h in interact["shared_hours"][:4])
                lines.append(f"- 共同活跃时段: {hours_str}")
            if cooccur_count > 0:
                lines.append(f"- 共现次数: {cooccur_count}")
        if rank:
            lines.append(f"\n你们是本群第 {rank} 亲密的组合")
        return "\n".join(lines)

    @classmethod
    def build_parallel(cls, my_name: str, local: Optional[dict] = None,
                       cross: Optional[list] = None,
                       get_nickname=None, prefix: str = "/") -> Dict[str, str]:
        html = cls._build_parallel_html(my_name, local, cross, get_nickname, prefix)
        markdown = cls._build_parallel_markdown(my_name, local, cross, get_nickname, prefix)
        text = cls._build_parallel_text(my_name, local, cross, get_nickname, prefix)
        return {"html": html, "markdown": markdown, "text": text}

    @classmethod
    def _build_parallel_html(cls, my_name, local, cross, get_nickname, prefix) -> str:
        sections = ""

        if local:
            tname = local.get("nickname", local["user_id"])
            sim = int(local["similarity"] * 100)
            scores = local.get("scores", {})
            checks = []
            for dim, label in [("timing", "活跃时段"), ("vocab", "消息风格"), ("emoji", "表情偏好")]:
                val = scores.get(dim, 0)
                pct = int(val * 100)
                mark = "+" if val >= 0.6 else "-"
                checks.append(f'<span style="color:{"#00ff88" if val >= 0.6 else "#ff4466"};">{mark}</span> {label} {pct}%')
            checks_html = "<br>".join(checks)
            sections += (
                f'<div style="margin-bottom:10px;">'
                f'<div style="font-size:12px;color:{cls.ACCENT_COLOR};margin-bottom:4px;">本群匹配</div>'
                f'<div style="font-size:13px;"><b>{my_name}</b> &lt;-&gt; <b>{tname}</b></div>'
                f'<div style="font-size:13px;margin:4px 0;">相似度: <b style="color:{cls.PRIMARY_COLOR};">{sim}%</b></div>'
                f'<div style="font-size:12px;">{checks_html}</div>'
                f'<div style="font-size:11px;color:{cls.SECONDARY_COLOR};margin-top:4px;">'
                f'试试 {prefix}亲密度 @{tname} 看看详细距离</div>'
                f'</div>'
            )

        if cross:
            items_html = ""
            for item in cross:
                other_scope = item.get("scope", "")
                scope_parts = other_scope.split(":")
                platform_name = scope_parts[1] if len(scope_parts) > 1 else "未知"
                sim = int(item["similarity"] * 100)
                uid = item["user_id"]
                label = item.get("nickname", uid)
                scores = item.get("scores", {})
                details = []
                for dim, dim_label in [("timing", "时段"), ("emoji", "表情"), ("vocab", "词汇")]:
                    if scores.get(dim, 0) > 0.6:
                        details.append(f"{dim_label}{int(scores[dim] * 100)}%")
                details_line = ""
                if details:
                    details_line = f'<div style="font-size:11px;color:{cls.SECONDARY_COLOR};">匹配项: {", ".join(details)}</div>'
                items_html += (
                    f'<div style="margin-bottom:6px;padding:6px 8px;background:rgba(255,255,255,0.03);border-radius:4px;">'
                    f'<div style="font-size:12px;">[{platform_name}] <b>{label}</b> '
                    f'<span style="color:{cls.PRIMARY_COLOR};">{sim}%</span></div>'
                    f'{details_line}'
                    f'</div>'
                )
            sections += (
                f'<details style="margin-top:6px;">'
                f'<summary style="cursor:pointer;font-size:12px;color:{cls.ACCENT_COLOR};">'
                f'跨群匹配 ({len(cross)}个)</summary>'
                f'<div style="padding:6px 0;">{items_html}</div>'
                f'</details>'
            )

        if not local and not cross:
            return (
                f'<div style="padding:12px;border-radius:8px;background:{cls.DARK_BG};color:#ccd;">'
                f'<div style="color:{cls.PRIMARY_COLOR};font-size:15px;font-weight:bold;margin-bottom:8px;">'
                f'正在寻找另一个你...</div>'
                f'<div style="font-size:13px;">没有找到另一个你（可能你和所有人都互动过了）</div>'
                f'</div>'
            )

        return (
            f'<div style="padding:12px;border-radius:8px;background:{cls.DARK_BG};color:#ccd;">'
            f'<div style="color:{cls.PRIMARY_COLOR};font-size:15px;font-weight:bold;margin-bottom:10px;">'
            f'正在寻找另一个你...</div>'
            f'{sections}'
            f'</div>'
        )

    @classmethod
    def _build_parallel_markdown(cls, my_name, local, cross, get_nickname, prefix) -> str:
        lines = ["**正在寻找另一个你...**", ""]
        if not local and not cross:
            lines.append("没有找到另一个你（可能你和所有人都互动过了）")
            return "\n".join(lines)

        if local:
            tname = local.get("nickname", local["user_id"])
            sim = int(local["similarity"] * 100)
            scores = local.get("scores", {})
            lines.append(f"**本群匹配:**")
            lines.append(f"  {my_name} <-> **{tname}**")
            lines.append(f"  相似度: **{sim}%**")
            for dim, label in [("timing", "活跃时段匹配度"), ("vocab", "消息风格相似"), ("emoji", "表情使用偏好")]:
                val = scores.get(dim, 0)
                mark = "+" if val >= 0.6 else "-"
                lines.append(f"  {mark} {label} {int(val * 100)}%")
            lines.append(f"  试试 `{prefix}亲密度 @{tname}` 看看详细距离")
            lines.append("")

        if cross:
            lines.append(f"**跨群匹配** (找到 {len(cross)} 个):")
            for item in cross:
                other_scope = item.get("scope", "")
                scope_parts = other_scope.split(":")
                platform_name = scope_parts[1] if len(scope_parts) > 1 else "未知"
                sim = int(item["similarity"] * 100)
                uid = item["user_id"]
                label = item.get("nickname", uid)
                scores = item.get("scores", {})
                details = []
                for dim, dim_label in [("timing", "时段"), ("emoji", "表情"), ("vocab", "词汇")]:
                    if scores.get(dim, 0) > 0.6:
                        details.append(f"{dim_label}{int(scores[dim] * 100)}%")
                lines.append(f"  [{platform_name}] **{label}** (相似度 {sim}%)")
                if details:
                    lines.append(f"    匹配项: {', '.join(details)}")
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def _build_parallel_text(cls, my_name, local, cross, get_nickname, prefix) -> str:
        lines = ["正在寻找另一个你...", "----------", ""]
        if not local and not cross:
            lines.append("没有找到另一个你（可能你和所有人都互动过了）")
            return "\n".join(lines)

        if local:
            tname = local.get("nickname", local["user_id"])
            sim = int(local["similarity"] * 100)
            scores = local.get("scores", {})
            lines.append("本群匹配:")
            lines.append(f"  {my_name} <-> {tname}")
            lines.append(f"  相似度: {sim}%")
            for dim, label in [("timing", "活跃时段匹配度"), ("vocab", "消息风格相似"), ("emoji", "表情使用偏好")]:
                val = scores.get(dim, 0)
                mark = "+" if val >= 0.6 else "-"
                lines.append(f"  {mark} {label} {int(val * 100)}%")
            lines.append(f"  试试 {prefix}亲密度 @{tname} 看看详细距离")
            lines.append("")

        if cross:
            lines.append(f"跨群匹配 (找到 {len(cross)} 个):")
            for item in cross:
                other_scope = item.get("scope", "")
                scope_parts = other_scope.split(":")
                platform_name = scope_parts[1] if len(scope_parts) > 1 else "未知"
                sim = int(item["similarity"] * 100)
                uid = item["user_id"]
                label = item.get("nickname", uid)
                scores = item.get("scores", {})
                details = []
                for dim, dim_label in [("timing", "时段"), ("emoji", "表情"), ("vocab", "词汇")]:
                    if scores.get(dim, 0) > 0.6:
                        details.append(f"{dim_label}{int(scores[dim] * 100)}%")
                lines.append(f"  [{platform_name}] {label} (相似度 {sim}%)")
                if details:
                    lines.append(f"    匹配项: {', '.join(details)}")
        return "\n".join(lines)

    @classmethod
    def build_radar_private(cls, nickname: str, global_count: int,
                            groups: list, tags: str = "",
                            peak_period: str = "", top_emoji: list = None) -> Dict[str, str]:
        html = cls._build_radar_private_html(nickname, global_count, groups, tags, peak_period, top_emoji)
        markdown = cls._build_radar_private_markdown(nickname, global_count, groups, tags, peak_period, top_emoji)
        text = cls._build_radar_private_text(nickname, global_count, groups, tags, peak_period, top_emoji)
        return {"html": html, "markdown": markdown, "text": text}

    @classmethod
    def _build_radar_private_html(cls, nickname, global_count, groups, tags, peak_period, top_emoji) -> str:
        groups_html = ""
        if groups:
            items = []
            for platform, gid, count in groups:
                items.append(
                    f'<span style="font-size:12px;margin-right:12px;">[{platform}] {gid}: {count}条</span>'
                )
            groups_html = "".join(items)
            groups_html = (
                f'<details style="margin-bottom:8px;">'
                f'<summary style="cursor:pointer;font-size:12px;color:{cls.SECONDARY_COLOR};">'
                f'群聊分布 ({len(groups)}个)</summary>'
                f'<div style="padding:6px 8px;display:flex;flex-wrap:wrap;gap:4px 0;">{groups_html}</div>'
                f'</details>'
            )

        tags_html = ""
        if tags:
            tags_html = (
                f'<div style="margin-bottom:6px;font-size:12px;">'
                f'<span style="color:{cls.ACCENT_COLOR};">社交标签:</span> {tags}'
                f'</div>'
            )

        period_html = ""
        if peak_period:
            period_html = (
                f'<div style="font-size:12px;">活跃时段: <b>{peak_period}</b></div>'
            )

        emoji_html = ""
        if top_emoji:
            emoji_str = " ".join(e for e, _ in top_emoji[:5])
            emoji_html = (
                f'<div style="font-size:12px;margin-top:4px;">常用表情: {emoji_str}</div>'
            )

        return (
            f'<div style="padding:12px;border-radius:8px;background:{cls.DARK_BG};color:#ccd;">'
            f'<div style="color:{cls.PRIMARY_COLOR};font-size:15px;font-weight:bold;margin-bottom:10px;">'
            f'{nickname} 的全局档案</div>'
            f'<div style="padding:6px 10px;background:rgba(0,255,136,0.06);'
            f'border-radius:6px;margin-bottom:10px;font-size:12px;">'
            f'消息统计: 共 <b>{global_count}</b> 条</div>'
            f'{groups_html}{tags_html}{period_html}{emoji_html}'
            f'</div>'
        )

    @classmethod
    def _build_radar_private_markdown(cls, nickname, global_count, groups, tags, peak_period, top_emoji) -> str:
        lines = [
            f"**{nickname} 的全局档案**",
            "",
            f"消息统计: 共 **{global_count}** 条",
        ]
        if groups:
            lines.append("")
            lines.append("**群聊分布:**")
            for platform, gid, count in groups:
                lines.append(f"  [{platform}] {gid}: {count}条")
            lines.append(f"\n活跃群聊: **{len(groups)}** 个")
        if tags:
            lines.append(f"\n社交标签: {tags}")
        if peak_period:
            lines.append(f"活跃时段: **{peak_period}**")
        if top_emoji:
            emoji_str = " ".join(e for e, _ in top_emoji[:5])
            lines.append(f"常用表情: {emoji_str}")
        return "\n".join(lines)

    @classmethod
    def _build_radar_private_text(cls, nickname, global_count, groups, tags, peak_period, top_emoji) -> str:
        lines = [
            f"{nickname} 的全局档案",
            "----------",
            f"消息统计: 共 {global_count} 条",
        ]
        if groups:
            lines.append("")
            lines.append("群聊分布:")
            for platform, gid, count in groups:
                lines.append(f"  [{platform}] {gid}: {count}条")
            lines.append(f"\n活跃群聊: {len(groups)} 个")
        if tags:
            lines.append(f"\n社交标签: {tags}")
        if peak_period:
            lines.append(f"活跃时段: {peak_period}")
        if top_emoji:
            emoji_str = " ".join(e for e, _ in top_emoji[:5])
            lines.append(f"常用表情: {emoji_str}")
        return "\n".join(lines)
