from .Templates import SonarTemplates


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

    def _get_command_prefix(self) -> str:
        try:
            from ErisPulse.Core import config
            event_config = config.getConfig("ErisPulse.event", {})
            command_config = event_config.get("command", {})
            return command_config.get("prefix", "/")
        except Exception:
            return "/"

    def _select_best_format(self, event, templates):
        try:
            if event.supports("Html"):
                return ("Html", templates["html"])
            if event.supports("Markdown"):
                return ("Markdown", templates["markdown"])
        except Exception:
            pass
        return ("Text", templates["text"])

    def _supports_image(self, event):
        try:
            return event.supports("Image")
        except Exception:
            return False

    async def _send_with_format(self, event, templates, image_bytes=None):
        if image_bytes and self._supports_image(event):
            try:
                await event.reply(image_bytes, method="Image")
                return
            except Exception as e:
                self.logger.warning(f"图片发送失败，回退到文本: {e}")
        fmt, content = self._select_best_format(event, templates)
        try:
            await event.reply(content, method=fmt)
        except Exception:
            await event.reply(templates["text"])

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

        global_total = sum(self.analyzer._get_global_count(u) for u in data["users"])
        local_total = sum(msg_counts.values())

        island_names = self._generate_island_names(scope, islands, nicknames)

        drifters = [u for u in data["users"]
                     if not any(u in isl["members"] for isl in islands)]

        prefix = self._get_command_prefix()

        image_bytes = self.visualizer.render_sonar(
            users=data["users"], matrix=data["matrix"], islands=islands,
            nicknames=nicknames, msg_counts=msg_counts,
            island_names=island_names, drifters=drifters,
            global_total=global_total, local_total=local_total,
            command_prefix=prefix,
        )

        templates = SonarTemplates.build_sonar(
            global_total, local_total, len(data["users"]),
            len(islands), islands, island_names, drifters, nicknames, prefix
        )
        await self._send_with_format(event, templates, image_bytes)

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

        optout = self.storage_get_optout(scope)
        if target_id in optout:
            await event.reply("该用户已关闭数据收集")
            return

        dist, scores = self.analyzer.compute_pair_distance(scope, user_id, target_id)

        dist_label = "非常近" if dist < 0.3 else "较近" if dist < 0.5 else "中等" if dist < 0.7 else "很远" if dist < 0.85 else "极远"

        nickname_a = self._get_nickname(event, user_id)
        nickname_b = self._get_nickname(event, target_id)

        interact = self.analyzer.get_interact_detail(scope, user_id, target_id)
        cooccur_count = self.analyzer.get_cooccur_count(scope, user_id, target_id)
        rank = self._get_distance_rank(scope, user_id, target_id)
        prefix = self._get_command_prefix()

        radar_bytes = self.visualizer.render_intimacy(
            nickname_a=nickname_a, nickname_b=nickname_b, dist=dist,
            dist_label=dist_label, scores=scores, interact=interact,
            cooccur_count=cooccur_count, rank=rank, command_prefix=prefix,
        )

        templates = SonarTemplates.build_ping(
            nickname_a, nickname_b, dist, dist_label, scores,
            interact, cooccur_count, rank, prefix
        )
        await self._send_with_format(event, templates, radar_bytes)

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

        global_total = sum(self.analyzer._get_global_count(u) for u in data["users"])
        local_total = sum(msg_counts.values())

        drifters = [u for u in data["users"]
                     if not any(u in isl["members"] for isl in islands)]

        prefix = self._get_command_prefix()

        image_bytes = self.visualizer.render_sonar(
            users=data["users"],
            matrix=data["matrix"],
            islands=islands,
            nicknames=nicknames,
            msg_counts=msg_counts,
            island_names=island_names,
            drifters=drifters,
            global_total=global_total,
            local_total=local_total,
            command_prefix=prefix,
        )

        templates = SonarTemplates.build_sonar(
            global_total, local_total, len(data["users"]),
            len(islands), islands, island_names, drifters, nicknames, prefix
        )
        await self._send_with_format(event, templates, image_bytes)

    async def _handle_parallel(self, event):
        scope, _ = self._get_scope(event)
        user_id = event.get_user_id()

        global_count = self.analyzer._get_global_count(user_id)
        min_msg = self.analyzer._min_messages()

        if global_count < min_msg:
            await event.reply(f"你总共发送了 {global_count} 条消息，需要至少 {min_msg} 条才能生成画像")
            return

        result = self.analyzer.find_parallel_universe(scope, user_id)
        local = result.get("local") if result else None
        cross = result.get("cross_scope", []) if result else []

        my_name = self._get_nickname(event, user_id)

        if local:
            local["nickname"] = self._get_nickname(event, local["user_id"])

        for item in cross:
            other_uid = item["user_id"]
            other_info = self.sdk.storage.get(f"sonar:profile:{other_uid}:info", {})
            item["nickname"] = other_info.get("nickname", "") or other_uid

        prefix = self._get_command_prefix()

        if not local and not cross:
            templates = SonarTemplates.build_parallel(my_name, None, None, None, prefix)
        else:
            templates = SonarTemplates.build_parallel(my_name, local, cross, None, prefix)

        image_bytes = self.visualizer.render_parallel(
            my_name=my_name, local=local, cross=cross, command_prefix=prefix,
        )

        await self._send_with_format(event, templates, image_bytes)

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

        presence = self.analyzer._get_presence(scope, user_id)

        rings = {"inner": [], "middle": [], "outer": [], "dark": []}
        for uid, info in distances.items():
            d = info["distance"]
            name = nicknames.get(uid, uid)
            if d < 0.3:
                rings["inner"].append((name, d))
            elif d < 0.6:
                rings["middle"].append((name, d))
            elif d < 0.8:
                rings["outer"].append((name, d))
            else:
                rings["dark"].append((name, d))

        detail = self.analyzer.get_user_detail(scope, user_id)
        tags = self._generate_tags(detail) if detail else ""

        image_bytes = self.visualizer.render_personal_radar(
            user_id=user_id, distances=distances, nicknames=nicknames,
            global_count=global_count, presence=presence,
            command_prefix=self._get_command_prefix(),
        )

        templates = SonarTemplates.build_radar_group(
            global_count, presence, rings, tags
        )
        await self._send_with_format(event, templates, image_bytes)

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

        group_tuples = []
        if groups:
            real_groups = [g for g in groups if not g.split(":")[-1].startswith("dm_")]
            for g_scope in real_groups:
                presence = self.analyzer._get_presence(g_scope, user_id)
                scope_parts = g_scope.split(":")
                platform = scope_parts[1] if len(scope_parts) > 1 else "?"
                gid = scope_parts[2] if len(scope_parts) > 2 else "?"
                group_tuples.append((platform, gid, presence))

        tags = self._generate_tags(detail) if detail else ""

        peak_period = ""
        if detail:
            peak = detail.get("peak_hours", [])
            if peak:
                h = int(peak[0])
                if 0 <= h < 6:
                    peak_period = "夜猫子 (0-6点)"
                elif 6 <= h < 12:
                    peak_period = "早起鸟 (6-12点)"
                elif 12 <= h < 18:
                    peak_period = "午后型 (12-18点)"
                else:
                    peak_period = "晚间型 (18-24点)"

        top_emoji = detail.get("top_emoji", []) if detail else []

        image_bytes = self.visualizer.render_profile(
            nickname=nickname, global_count=global_count, groups=group_tuples,
            tags=tags, peak_period=peak_period, top_emoji=top_emoji,
        )

        templates = SonarTemplates.build_radar_private(
            nickname, global_count, group_tuples, tags, peak_period, top_emoji
        )
        await self._send_with_format(event, templates, image_bytes)

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
