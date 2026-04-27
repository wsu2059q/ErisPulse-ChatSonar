import io


class Commands:
    def __init__(self, sdk, collector, analyzer, visualizer, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Commands")
        self.collector = collector
        self.analyzer = analyzer
        self.visualizer = visualizer
        self.config = config

    def register(self):
        from ErisPulse.Core.Event import command

        @command("群地图", help="生成全群社交关系地图")
        async def sonar_cmd(event):
            await self._handle_sonar(event)

        @command("亲密度", help="查看你和某人的亲密度 /亲密度 @某人")
        async def ping_cmd(event):
            await self._handle_ping(event)

        @command("小圈子", help="查看群里的社交圈子分布")
        async def islands_cmd(event):
            await self._handle_islands(event)

        @command("另一个我", help="找到和你最像但从未说过话的人")
        async def parallel_cmd(event):
            await self._handle_parallel(event)

        @command("我的位置", help="查看你在社交圈中的位置 / 个人档案")
        async def radar_cmd(event):
            await self._handle_radar(event)

        @command("别盯着我", help="停止收集你的数据并删除")
        async def sonaroff_cmd(event):
            await self._handle_sonaroff(event)

        @command("可以盯我了", help="重新加入声呐监测")
        async def sonaron_cmd(event):
            await self._handle_sonaron(event)

    def _get_scope(self, event):
        platform = event.get_platform()
        detail_type = event.get_detail_type()
        if detail_type != "group":
            return None, None
        group_id = event.get_group_id()
        if not group_id:
            return None, None
        return f"sonar:{platform}:{group_id}", group_id

    def _get_nickname(self, event, user_id):
        info = self.sdk.storage.get(f"sonar:profile:{user_id}:info", {})
        if info.get("nickname"):
            return info["nickname"]
        sender = event.get_sender()
        if sender and sender.get("user_id") == user_id:
            return sender.get("nickname", "") or sender.get("user_name", "") or user_id
        return user_id

    def _get_mentioned_user(self, event):
        mentions = event.get_mentions()
        if mentions:
            return mentions[0]
        args = event.get_command_args()
        if args:
            for arg in args:
                if arg.startswith("@"):
                    return arg[1:]
        return None

    def _require_group(self, event):
        scope, group_id = self._get_scope(event)
        if not scope:
            return None, None
        return scope, group_id

    async def _handle_sonar(self, event):
        scope, group_id = self._require_group(event)
        if not scope:
            await event.reply("请在群聊中使用此命令")
            return

        data = self.analyzer.compute_distance_matrix(scope, force=True)
        if not data or len(data["users"]) < 2:
            await self._reply_insufficient_data(event, scope)
            return

        islands = self.analyzer.detect_islands(scope, data)

        nicknames = {}
        msg_counts = {}
        for uid in data["users"]:
            nicknames[uid] = self._get_nickname(event, uid)
            msg_counts[uid] = self.analyzer._get_presence(scope, uid)

        image_bytes = self.visualizer.generate_sonar(
            data["users"], data["matrix"], islands, nicknames, msg_counts
        )

        global_total = sum(self.analyzer._get_global_count(u) for u in data["users"])
        local_total = sum(msg_counts.values())

        text = f"声呐扫描完成\n"
        text += f"采集 {global_total} 条全局消息（本群 {local_total} 条），"
        text += f"覆盖 {len(data['users'])} 位用户，"
        text += f"检测到 {len(islands)} 个岛屿\n\n"
        text += "岛屿分布:\n"
        text += "─" * 20 + "\n"

        island_names = self._generate_island_names(scope, islands, nicknames)
        for idx, island in enumerate(islands):
            name = island_names[idx]
            members_str = "、".join(nicknames.get(m, m) for m in island["members"])
            text += f"{name}({island['size']}人)\n"
            text += f"  {members_str}\n"
            text += f"  内部距离: {island['avg_distance']}\n\n"

        drifters = [u for u in data["users"]
                     if not any(u in isl["members"] for isl in islands)]
        if drifters:
            drifter_names = "、".join(nicknames.get(u, u) for u in drifters)
            text += f"漂流者({len(drifters)}人)\n  {drifter_names}\n\n"

        text += "用 /亲密度 @某人 查看具体距离"

        if image_bytes:
            await event.reply(image_bytes, method="Image")
        await event.reply(text.strip())

    async def _handle_ping(self, event):
        scope, group_id = self._require_group(event)
        if not scope:
            await event.reply("请在群聊中使用此命令")
            return

        target_id = self._get_mentioned_user(event)
        if not target_id:
            await event.reply("请 @一个人，例如: /亲密度 @某人")
            return

        user_id = event.get_user_id()
        if target_id == user_id:
            await event.reply("你不能探测自己")
            return

        optout = self.collector.storage_get_optout(scope)
        if target_id in optout:
            await event.reply("该用户已关闭数据收集")
            return

        dist, scores = self.analyzer.compute_pair_distance(scope, user_id, target_id)

        dist_label = "非常近" if dist < 0.3 else "较近" if dist < 0.5 else "中等" if dist < 0.7 else "很远" if dist < 0.85 else "极远"

        nickname_a = self._get_nickname(event, user_id)
        nickname_b = self._get_nickname(event, target_id)

        text = f"亲密度报告\n\n"
        text += f"{nickname_a} <-> {nickname_b}\n"
        text += f"综合距离: {dist:.2f} ({dist_label})\n\n"
        text += "维度分析:\n"

        dim_names = {
            "timing": "时段重叠",
            "emoji": "表情相似",
            "vocab": "词汇相似",
            "interaction": "直接互动",
            "cooccurrence": "共现频率",
        }
        for dim, label in dim_names.items():
            val = scores.get(dim, 0)
            pct = int(val * 100)
            filled = int(val * 10)
            bar = "█" * filled + "░" * (10 - filled)
            text += f"{label}  {bar} {pct}%\n"

        radar_bytes = self.visualizer.generate_radar_chart(scores)
        if radar_bytes:
            await event.reply(radar_bytes, method="Image")

        interact = self.analyzer.get_interact_detail(scope, user_id, target_id)
        cooccur_count = self.analyzer.get_cooccur_count(scope, user_id, target_id)

        if interact["reply_total"] > 0 or cooccur_count > 0:
            text += f"\n互动记录:\n"
            if interact["a_to_b"] > 0 or interact["b_to_a"] > 0:
                text += f"- 你 @了TA {interact['a_to_b']} 次\n"
                text += f"- TA @了你 {interact['b_to_a']} 次\n"
                text += f"- 互相回复 {interact['reply_total']} 次\n"
            if interact["shared_hours"]:
                hours_str = ", ".join(f"{h}:00" for h in interact["shared_hours"][:4])
                text += f"- 共同活跃时段: {hours_str}\n"
            if cooccur_count > 0:
                text += f"- 共现次数: {cooccur_count}\n"

        rank = self._get_distance_rank(scope, user_id, target_id)
        if rank:
            text += f"\n你们是本群第 {rank} 亲密的组合"

        await event.reply(text.strip())

    async def _handle_islands(self, event):
        scope, group_id = self._require_group(event)
        if not scope:
            await event.reply("请在群聊中使用此命令")
            return

        data = self.analyzer.compute_distance_matrix(scope)
        if not data:
            await self._reply_insufficient_data(event, scope)
            return

        islands = self.analyzer.detect_islands(scope, data)
        nicknames = {}
        for uid in data["users"]:
            nicknames[uid] = self._get_nickname(event, uid)

        island_names = self._generate_island_names(scope, islands, nicknames)

        msg_counts = {}
        for uid in data["users"]:
            msg_counts[uid] = self.analyzer._get_presence(scope, uid)

        image_bytes = self.visualizer.generate_sonar(
            users=data["users"],
            matrix=data["matrix"],
            islands=islands,
            nicknames=nicknames,
            msg_counts=msg_counts,
        )

        text = f"岛屿态势报告\n\n"

        for idx, island in enumerate(islands):
            name = island_names[idx]
            members_str = "、".join(nicknames.get(m, m) for m in island["members"])
            text += f"{name}({island['size']}人)\n"
            text += f"  {members_str}\n"
            text += f"  内部距离: {island['avg_distance']}\n\n"

        drifters = [u for u in data["users"]
                     if not any(u in isl["members"] for isl in islands)]
        if drifters:
            drifter_names = "、".join(nicknames.get(u, u) for u in drifters)
            text += f"漂流者({len(drifters)}人)\n  {drifter_names}\n"

        if image_bytes:
            await event.reply(image_bytes, method="Image")
        await event.reply(text.strip())

    async def _handle_parallel(self, event):
        scope, _ = self._get_scope(event)
        user_id = event.get_user_id()

        global_count = self.analyzer._get_global_count(user_id)
        min_msg = self.analyzer._min_messages()

        if global_count < min_msg:
            await event.reply(f"你总共发送了 {global_count} 条消息，需要至少 {min_msg} 条才能生成画像")
            return

        if scope:
            result = self.analyzer.find_parallel_universe(scope, user_id)
            local = result.get("local") if result else None
            cross = result.get("cross_scope", []) if result else []
        else:
            local = None
            cross = []
            all_scopes = self.collector.get_all_scopes()
            for other_scope_str in all_scopes:
                other_scope = f"sonar:{other_scope_str}"
                match = self.analyzer._find_parallel_in_scope(other_scope, user_id)
                if match:
                    match["scope"] = other_scope
                    cross.append(match)
            cross.sort(key=lambda x: x["similarity"], reverse=True)
            cross = cross[:3]

        if not local and not cross:
            await event.reply("没有找到另一个你（可能你和所有人都互动过了）")
            return

        my_name = self._get_nickname(event, user_id)
        text = "正在寻找另一个你...\n\n"

        if local:
            target = local
            tname = self._get_nickname(event, target["user_id"])
            text += f"本群匹配:\n"
            text += f"  {my_name} <-> {tname}\n"
            text += f"  相似度: {int(target['similarity'] * 100)}%\n"
            text += self._format_parallel_reason(target["scores"])
            text += f"  试试 /亲密度 @{tname} 看看详细距离\n\n"

        if cross:
            text += f"跨群匹配 (找到 {len(cross)} 个):\n"
            for item in cross:
                other_scope = item["scope"]
                scope_parts = other_scope.split(":")
                platform_name = scope_parts[1] if len(scope_parts) > 1 else "未知"
                group_hint = scope_parts[2] if len(scope_parts) > 2 else ""

                other_uid = item["user_id"]
                other_info = self.sdk.storage.get(f"sonar:profile:{other_uid}:info", {})
                other_nick = other_info.get("nickname", "")

                label = other_nick or other_uid
                text += f"  [{platform_name}] {label} (相似度 {int(item['similarity'] * 100)}%)\n"

                scores = item.get("scores", {})
                details = []
                if scores.get("timing", 0) > 0.6:
                    details.append(f"时段{int(scores['timing'] * 100)}%")
                if scores.get("emoji", 0) > 0.6:
                    details.append(f"表情{int(scores['emoji'] * 100)}%")
                if scores.get("vocab", 0) > 0.6:
                    details.append(f"词汇{int(scores['vocab'] * 100)}%")
                if details:
                    text += f"    匹配项: {', '.join(details)}\n"
                text += f"    用户ID: {other_uid}\n"

        await event.reply(text.strip())

    def _format_parallel_reason(self, scores):
        text = ""
        checks = [
            ("  活跃时段匹配度", "timing"),
            ("  消息风格相似", "vocab"),
            ("  表情使用偏好", "emoji"),
        ]
        for label, dim in checks:
            val = scores.get(dim, 0)
            pct = int(val * 100)
            mark = "+" if val >= 0.6 else "-"
            text += f"    {mark} {label} {pct}%\n"
        return text

    async def _handle_radar(self, event):
        scope, _ = self._get_scope(event)

        if scope:
            await self._handle_radar_group(event, scope)
        else:
            await self._handle_radar_private(event)

    async def _handle_radar_group(self, event, scope):
        user_id = event.get_user_id()
        global_count = self.analyzer._get_global_count(user_id)
        min_msg = self.analyzer._min_messages()

        if global_count < min_msg:
            await event.reply(f"你总共发送了 {global_count} 条消息，需要至少 {min_msg} 条才能生成画像")
            return

        distances = self.analyzer.get_user_distances(scope, user_id)

        if not distances:
            presence = self.analyzer._get_presence(scope, user_id)
            all_scope_users = self.analyzer._get_users(scope)
            eligible = self.analyzer._eligible_users(scope)
            if len(eligible) < 2:
                info_lines = []
                for uid in all_scope_users:
                    g = self.analyzer._get_global_count(uid)
                    p = self.analyzer._get_presence(scope, uid)
                    name = self._get_nickname(event, uid)
                    mark = "✓" if g >= min_msg else "✗"
                    info_lines.append(f"  {mark} {name}: 全局{g}条, 本群{p}条")
                details = "\n".join(info_lines[:10])
                await event.reply(f"本群活跃用户不足，需要至少 2 位用户各有 {min_msg} 条以上消息\n\n{details}")
            else:
                await event.reply("你在本群还没有足够的互动数据")
            return

        nicknames = {}
        for uid in distances:
            nicknames[uid] = self._get_nickname(event, uid)
        nicknames[user_id] = self._get_nickname(event, user_id)

        image_bytes = self.visualizer.generate_personal_radar(
            user_id, distances, nicknames
        )

        presence = self.analyzer._get_presence(scope, user_id)
        text = f"你的社交雷达\n\n"
        text += f"全局消息: {global_count} 条 | 本群消息: {presence} 条\n\n"

        inner = []
        middle = []
        outer = []
        dark = []
        for uid, info in distances.items():
            d = info["distance"]
            name = nicknames.get(uid, uid)
            if d < 0.3:
                inner.append((name, d))
            elif d < 0.6:
                middle.append((name, d))
            elif d < 0.8:
                outer.append((name, d))
            else:
                dark.append((name, d))

        if inner:
            text += "内圈 (距离 < 0.3)\n"
            for name, d in inner:
                text += f"  {name} ({d:.2f})\n"
            text += "\n"
        if middle:
            text += "中圈 (0.3 ~ 0.6)\n"
            for name, d in middle:
                text += f"  {name} ({d:.2f})\n"
            text += "\n"
        if outer:
            text += "外圈 (0.6 ~ 0.8)\n"
            for name, d in outer:
                text += f"  {name} ({d:.2f})\n"
            text += "\n"
        if dark:
            text += "暗区 (> 0.8)\n"
            for name, d in dark:
                text += f"  {name} ({d:.2f})\n"

        detail = self.analyzer.get_user_detail(scope, user_id)
        if detail:
            text += "\n"
            tags = self._generate_tags(detail)
            if tags:
                text += f"你的社交标签:\n{tags}"

        if image_bytes:
            await event.reply(image_bytes, method="Image")
        await event.reply(text.strip())

    async def _handle_radar_private(self, event):
        user_id = event.get_user_id()
        global_count = self.analyzer._get_global_count(user_id)
        min_msg = self.analyzer._min_messages()

        if global_count < min_msg:
            await event.reply(f"你总共发送了 {global_count} 条消息，需要至少 {min_msg} 条才能生成画像")
            return

        detail = self.analyzer.get_user_detail(user_id)
        groups = self.analyzer.get_user_groups(user_id)

        nickname = self._get_nickname(event, user_id)

        text = f"{nickname} 的全局档案\n\n"
        text += f"消息统计: 共 {global_count} 条\n"

        if groups:
            group_details = []
            real_groups = [g for g in groups if not g.split(":")[-1].startswith("dm_")]
            for g_scope in real_groups:
                presence = self.analyzer._get_presence(g_scope, user_id)
                scope_parts = g_scope.split(":")
                platform = scope_parts[1] if len(scope_parts) > 1 else "?"
                gid = scope_parts[2] if len(scope_parts) > 2 else "?"
                group_details.append(f"  [{platform}] {gid}: {presence}条")
            if group_details:
                text += "群聊分布:\n" + "\n".join(group_details) + "\n"
                text += f"\n活跃群聊: {len(real_groups)} 个\n"

        text += "\n"
        tags = self._generate_tags(detail)
        if tags:
            text += f"社交标签:\n  {tags}\n"

        peak = detail.get("peak_hours", [])
        if peak:
            h = int(peak[0])
            if 0 <= h < 6:
                period = "夜猫子 (0-6点)"
            elif 6 <= h < 12:
                period = "早起鸟 (6-12点)"
            elif 12 <= h < 18:
                period = "午后型 (12-18点)"
            else:
                period = "晚间型 (18-24点)"
            text += f"活跃时段: {period}\n"

        top_emoji = detail.get("top_emoji", [])
        if top_emoji:
            emoji_str = " ".join(e for e, _ in top_emoji[:5])
            text += f"常用表情: {emoji_str}\n"

        await event.reply(text.strip())

    async def _handle_sonaroff(self, event):
        scope, _ = self._get_scope(event)
        user_id = event.get_user_id()

        if scope:
            await event.reply(
                "确认关闭本群声呐数据收集？\n"
                "将删除你在本群的互动数据（全局画像保留）\n\n"
                "回复\"确认\"执行，其他内容取消"
            )
            reply = await event.wait_reply(timeout=30)
            if reply and reply.get_text().strip() == "确认":
                self.collector.delete_user_data(scope, user_id)
                await event.reply(
                    "已完成:\n"
                    "- 已删除本群互动记录\n"
                    "- 从本群距离矩阵中移除\n"
                    "- 后续本群消息不再采集\n"
                    "- 全局画像数据已保留\n\n"
                    "随时发送 /可以盯我了 重新加入"
                )
            else:
                await event.reply("已取消")
        else:
            await event.reply(
                "确认关闭所有声呐数据收集？\n"
                "将删除你的全部数据（包括全局画像）\n\n"
                "回复\"确认\"执行，其他内容取消"
            )
            reply = await event.wait_reply(timeout=30)
            if reply and reply.get_text().strip() == "确认":
                self.collector.delete_global_data(user_id)
                await event.reply(
                    "已完成:\n"
                    "- 已删除全部特征记录\n"
                    "- 已清理所有群级数据\n"
                    "- 后续消息不再采集\n\n"
                    "随时发送 /可以盯我了 重新加入"
                )
            else:
                await event.reply("已取消")

    async def _handle_sonaron(self, event):
        scope, _ = self._get_scope(event)
        user_id = event.get_user_id()

        if scope:
            self.collector.rejoin_user(scope, user_id)
            await event.reply(
                "已重新加入本群声呐监测\n"
                "发几条消息后就能看到你的位置了"
            )
        else:
            await event.reply(
                "已重新加入声呐监测\n"
                "在群聊中发消息后就能看到你的位置了"
            )

    async def _reply_insufficient_data(self, event, scope):
        users = self.analyzer._get_users(scope)
        min_msg = self.analyzer._min_messages()
        eligible = self.analyzer._eligible_users(scope)
        info_lines = []
        for uid in users:
            g = self.analyzer._get_global_count(uid)
            p = self.analyzer._get_presence(scope, uid)
            name = self._get_nickname(event, uid)
            mark = "✓" if g >= min_msg else "✗"
            info_lines.append((g, p, f"  {mark} {name}: 全局{g}条, 本群{p}条"))
        info_lines.sort(key=lambda x: x[0], reverse=True)
        details = "\n".join(line for _, _, line in info_lines[:10])

        text = f"本群活跃用户不足，需要至少 2 位用户各有 {min_msg} 条以上消息"
        text += f"\n（达标用户: {len(eligible)}/{len(users)}）\n\n{details}"
        await event.reply(text)

    def storage_get_optout(self, scope):
        return self.sdk.storage.get(f"{scope}:optout", [])

    def _get_distance_rank(self, scope, uid_a, uid_b):
        data = self.analyzer.compute_distance_matrix(scope)
        if not data:
            return None

        users = data["users"]
        matrix = data["matrix"]

        pairs = []
        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                key = f"{users[i]}|{users[j]}"
                dist = matrix.get(key, 1.0)
                pairs.append((users[i], users[j], dist))

        pairs.sort(key=lambda x: x[2])

        for rank, (a, b, _) in enumerate(pairs, 1):
            if (a == uid_a and b == uid_b) or (a == uid_b and b == uid_a):
                return rank
        return None

    def _generate_island_names(self, scope, islands, nicknames):
        all_uids = set()
        for island in islands:
            all_uids.update(island["members"])

        details_cache = {}
        for uid in all_uids:
            details_cache[uid] = self.analyzer.get_user_detail(scope, uid)

        names = []
        for island in islands:
            members = island["members"]
            if island["avg_distance"] < 0.2:
                base = "铁三角" if len(members) == 3 else "核心圈"
            else:
                base = "群岛"

            labels = []
            for uid in members:
                detail = details_cache.get(uid)
                if detail:
                    tags = self._generate_tags(detail)
                    if tags:
                        labels.append(tags.split("/")[0].strip())
            if labels:
                names.append(f"「{''.join(labels[:2])}」{base}")
            else:
                names.append(base)
        return names

    def _generate_tags(self, detail):
        tags = []
        peak = detail.get("peak_hours", [])
        if peak:
            h = int(peak[0])
            if 0 <= h < 6:
                tags.append("夜猫子")
            elif 6 <= h < 12:
                tags.append("早起鸟")
            elif 12 <= h < 18:
                tags.append("午后型")
            else:
                tags.append("晚间型")

        avg_len = detail.get("avg_length", 0)
        if avg_len > 50:
            tags.append("长文选手")
        elif avg_len < 10:
            tags.append("短平快")

        top_emoji = detail.get("top_emoji", [])
        if len(top_emoji) > 3:
            tags.append("表情包达人")

        interact_count = detail.get("interact_targets", 0)
        if interact_count > 5:
            tags.append("社牛")
        elif interact_count <= 1:
            tags.append("独行者")

        msg_count = detail.get("message_count", 0)
        if msg_count > 500:
            tags.append("话痨")
        elif msg_count < 20:
            tags.append("潜水员")

        return " / ".join(tags[:4]) if tags else ""
