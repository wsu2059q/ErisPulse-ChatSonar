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

        @command("我的位置", help="查看你在群社交圈中的位置")
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
        group_id = event.get_group_id() if detail_type == "group" else f"dm_{event.get_user_id()}"
        if not group_id:
            return None, None
        return f"sonar:{platform}:{group_id}", group_id

    def _get_nickname(self, event, user_id):
        scope, _ = self._get_scope(event)
        if scope:
            users = self.sdk.storage.get(f"{scope}:users", {})
            user_info = users.get(user_id)
            if isinstance(user_info, dict) and user_info.get("nickname"):
                return user_info["nickname"]
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
            raw = event.get_text()
            for arg in args:
                if arg.startswith("@"):
                    return arg[1:]
        return None

    async def _handle_sonar(self, event):
        scope, group_id = self._get_scope(event)
        if not scope:
            await event.reply("无法识别当前群组")
            return

        data = self.analyzer.compute_distance_matrix(scope, force=True)
        if not data or len(data["users"]) < 2:
            users = self.analyzer._get_users(scope)
            min_msg = self.analyzer._min_messages()
            eligible = [(u, self.analyzer._get_message_count(scope, u)) for u in users]
            eligible.sort(key=lambda x: x[1], reverse=True)
            info = "\n".join(f"  {self._get_nickname(event, u)}: {c}条 (需{min_msg}条)" for u, c in eligible[:10])
            await event.reply(f"数据不足，至少需要 2 位用户各发 {min_msg} 条以上消息\n\n当前数据:\n{info}")
            return

        islands = self.analyzer.detect_islands(scope, data)

        nicknames = {}
        msg_counts = {}
        for uid in data["users"]:
            nicknames[uid] = self._get_nickname(event, uid)
            msg_counts[uid] = self.analyzer._get_message_count(scope, uid)

        image_bytes = self.visualizer.generate_sonar(
            data["users"], data["matrix"], islands, nicknames, msg_counts
        )

        text = f"声呐扫描完成\n"
        text += f"采集 {sum(self.analyzer._get_message_count(scope, u) for u in data['users'])} 条消息，"
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
        scope, group_id = self._get_scope(event)
        if not scope:
            await event.reply("无法识别当前群组")
            return

        target_id = self._get_mentioned_user(event)
        if not target_id:
            await event.reply("请 @一个人，例如: /亲密度 @某人")
            return

        user_id = event.get_user_id()
        if target_id == user_id:
            await event.reply("你不能探测自己")
            return

        optout = self.storage_get_optout(scope)
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
        scope, group_id = self._get_scope(event)
        if not scope:
            await event.reply("无法识别当前群组")
            return

        data = self.analyzer.compute_distance_matrix(scope)
        if not data:
            await event.reply("数据不足")
            return

        islands = self.analyzer.detect_islands(scope, data)
        nicknames = {}
        for uid in data["users"]:
            nicknames[uid] = self._get_nickname(event, uid)

        island_names = self._generate_island_names(scope, islands, nicknames)

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

        await event.reply(text.strip())

    async def _handle_parallel(self, event):
        scope, group_id = self._get_scope(event)
        if not scope:
            await event.reply("无法识别当前群组")
            return

        user_id = event.get_user_id()
        result = self.analyzer.find_parallel_universe(scope, user_id)

        local = result.get("local") if result else None
        cross = result.get("cross_scope", []) if result else []

        if not local and not cross:
            data = self.analyzer.compute_distance_matrix(scope)
            if not data or user_id not in data["users"]:
                count = self.analyzer._get_message_count(scope, user_id)
                min_msg = self.analyzer._min_messages()
                await event.reply(f"你的消息数: {count}条 (需要 {min_msg} 条)")
            else:
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
                other_users = self.sdk.storage.get(f"{other_scope}:users", {})
                other_info = other_users.get(other_uid, {})
                other_nick = other_info.get("nickname", "") if isinstance(other_info, dict) else ""

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
        scope, group_id = self._get_scope(event)
        if not scope:
            await event.reply("无法识别当前群组")
            return

        user_id = event.get_user_id()
        distances = self.analyzer.get_user_distances(scope, user_id)

        if not distances:
            count = self.analyzer._get_message_count(scope, user_id)
            min_msg = self.analyzer._min_messages()
            if count < min_msg:
                await event.reply(f"你的消息数: {count}条 (需要 {min_msg} 条)")
            else:
                await event.reply("群里其他人数据不足")
            return

        nicknames = {}
        for uid in distances:
            nicknames[uid] = self._get_nickname(event, uid)
        nicknames[user_id] = self._get_nickname(event, user_id)

        image_bytes = self.visualizer.generate_personal_radar(
            user_id, distances, nicknames
        )

        text = f"你的社交雷达\n\n"

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

    async def _handle_sonaroff(self, event):
        scope, group_id = self._get_scope(event)
        if not scope:
            await event.reply("无法识别当前群组")
            return

        user_id = event.get_user_id()
        await event.reply(
            "确认关闭声呐数据收集？\n"
            "将删除你在本群的所有特征数据\n"
            "已生成的声呐图中你将不再出现\n\n"
            "回复\"确认\"执行，其他内容取消"
        )

        reply = await event.wait_reply(timeout=30)
        if reply and reply.get_text().strip() == "确认":
            self.collector.delete_user_data(scope, user_id)
            await event.reply(
                "已完成:\n"
                "- 已删除你的特征记录\n"
                "- 从距离矩阵中移除\n"
                "- 后续消息不再采集\n\n"
                "随时发送 /可以盯我了 重新加入"
            )
        else:
            await event.reply("已取消")

    async def _handle_sonaron(self, event):
        scope, group_id = self._get_scope(event)
        if not scope:
            await event.reply("无法识别当前群组")
            return

        user_id = event.get_user_id()
        self.collector.rejoin_user(scope, user_id)
        await event.reply(
            "已重新加入声呐监测\n"
            "当前特征数据为空，发几条消息后就能看到你的位置了"
        )

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
            if h >= 0 and h < 6:
                tags.append("夜猫子")
            elif h >= 6 and h < 12:
                tags.append("早起鸟")
            elif h >= 12 and h < 18:
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
        total_members = max(detail.get("interact_count", 1), 1)
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
