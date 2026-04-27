import math
import time
from collections import defaultdict


class Analyzer:
    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Analyzer")
        self.storage = sdk.storage
        self.config = config

    def _default_weights(self):
        return self.config.get("weights", {
            "timing": 0.20,
            "emoji": 0.15,
            "vocab": 0.20,
            "interaction": 0.30,
            "cooccurrence": 0.15,
        })

    def _min_messages(self):
        return self.config.get("min_messages", 5)

    def _distance_threshold(self):
        return self.config.get("distance_threshold", 0.6)

    def _get_users(self, scope):
        return list(self.storage.get(f"{scope}:users", {}).keys())

    def _get_message_count(self, scope, uid):
        length_data = self.storage.get(f"{scope}:length:{uid}", {"count": 0})
        return length_data.get("count", 0)

    def _eligible_users(self, scope):
        users = self._get_users(scope)
        min_msg = self._min_messages()
        return [u for u in users if self._get_message_count(scope, u) >= min_msg]

    @staticmethod
    def jaccard(set_a, set_b):
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        a = set(set_a)
        b = set(set_b)
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def cosine_sim(dict_a, dict_b):
        if not dict_a or not dict_b:
            return 0.0
        all_keys = set(dict_a.keys()) | set(dict_b.keys())
        dot = sum(dict_a.get(k, 0) * dict_b.get(k, 0) for k in all_keys)
        norm_a = math.sqrt(sum(v ** 2 for v in dict_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in dict_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def timing_similarity(self, scope, uid_a, uid_b):
        ta = self.storage.get(f"{scope}:timing:{uid_a}", {})
        tb = self.storage.get(f"{scope}:timing:{uid_b}", {})
        hours_a = set(ta.keys())
        hours_b = set(tb.keys())
        if not hours_a and not hours_b:
            return 0.5
        all_hours = set(range(24))
        vec_a = {h: ta.get(str(h), 0) for h in all_hours}
        vec_b = {h: tb.get(str(h), 0) for h in all_hours}
        return self.cosine_sim(vec_a, vec_b)

    def emoji_similarity(self, scope, uid_a, uid_b):
        ea = self.storage.get(f"{scope}:emoji:{uid_a}", {})
        eb = self.storage.get(f"{scope}:emoji:{uid_b}", {})
        if not ea and not eb:
            return 0.5
        return self.cosine_sim(ea, eb)

    def vocab_similarity(self, scope, uid_a, uid_b):
        va = self.storage.get(f"{scope}:vocab:{uid_a}", {})
        vb = self.storage.get(f"{scope}:vocab:{uid_b}", {})
        if not va and not vb:
            return 0.5
        return self.cosine_sim(va, vb)

    def interaction_score(self, scope, uid_a, uid_b, max_interact=100.0):
        ia = self.storage.get(f"{scope}:interact:{uid_a}", {})
        ib = self.storage.get(f"{scope}:interact:{uid_b}", {})
        a_to_b = ia.get(uid_b, 0)
        b_to_a = ib.get(uid_a, 0)
        total = a_to_b + b_to_a
        if total == 0:
            return 0.0
        return min(total / max_interact, 1.0)

    def cooccurrence_score(self, scope, uid_a, uid_b, max_cooccur=50.0):
        cooccur = self.storage.get(f"{scope}:cooccur", {})
        pair = f"{uid_a}|{uid_b}"
        val = cooccur.get(pair, 0)
        if val == 0:
            return 0.0
        return min(val / max_cooccur, 1.0)

    def _compute_max_interact(self, scope, users):
        max_val = 0
        for uid in users:
            interact = self.storage.get(f"{scope}:interact:{uid}", {})
            for count in interact.values():
                max_val = max(max_val, count)
        return max(max_val, 1.0)

    def _compute_max_cooccur(self, scope, users):
        cooccur = self.storage.get(f"{scope}:cooccur", {})
        max_val = 0
        for count in cooccur.values():
            max_val = max(max_val, count)
        return max(max_val, 1.0)

    def compute_pair_distance(self, scope, uid_a, uid_b, weights=None, max_interact=100.0, max_cooccur=50.0):
        if weights is None:
            weights = self._default_weights()

        scores = {
            "timing": self.timing_similarity(scope, uid_a, uid_b),
            "emoji": self.emoji_similarity(scope, uid_a, uid_b),
            "vocab": self.vocab_similarity(scope, uid_a, uid_b),
            "interaction": self.interaction_score(scope, uid_a, uid_b, max_interact),
            "cooccurrence": self.cooccurrence_score(scope, uid_a, uid_b, max_cooccur),
        }

        total_w = sum(weights.values())
        distance = 0.0
        for dim, w in weights.items():
            nw = w / total_w if total_w > 0 else 0
            distance += nw * (1.0 - scores.get(dim, 0))

        return distance, scores

    def compute_distance_matrix(self, scope, force=False):
        cache_key = f"{scope}:cache"
        cached = self.storage.get(cache_key)
        if cached and not force:
            cached_time = cached.get("timestamp", 0)
            interval = self.config.get("update_interval", 3600)
            if time.time() - cached_time < interval:
                return cached

        users = self._eligible_users(scope)
        if len(users) < 2:
            return None

        weights = self._default_weights()
        max_interact = self._compute_max_interact(scope, users)
        max_cooccur = self._compute_max_cooccur(scope, users)
        matrix = {}
        scores_map = {}

        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                dist, scores = self.compute_pair_distance(scope, users[i], users[j], weights, max_interact, max_cooccur)
                matrix[f"{users[i]}|{users[j]}"] = dist
                matrix[f"{users[j]}|{users[i]}"] = dist
                scores_map[f"{users[i]}|{users[j]}"] = scores
                scores_map[f"{users[j]}|{users[i]}"] = scores

        result = {
            "timestamp": time.time(),
            "users": users,
            "matrix": matrix,
            "scores": scores_map,
        }
        self.storage.set(cache_key, result)
        return result

    def detect_islands(self, scope, data=None, threshold=None):
        if threshold is None:
            threshold = self._distance_threshold()
        if data is None:
            data = self.compute_distance_matrix(scope)
        if not data:
            return []

        users = data["users"]
        matrix = data["matrix"]

        parent = {u: u for u in users}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                key = f"{users[i]}|{users[j]}"
                dist = matrix.get(key, 1.0)
                if dist < threshold:
                    union(users[i], users[j])

        groups = defaultdict(list)
        for u in users:
            groups[find(u)].append(u)

        islands = []
        for root, members in groups.items():
            avg_dist = 0.0
            count = 0
            for mi in range(len(members)):
                for mj in range(mi + 1, len(members)):
                    key = f"{members[mi]}|{members[mj]}"
                    avg_dist += matrix.get(key, 1.0)
                    count += 1
            avg_dist = avg_dist / count if count > 0 else 0.0

            islands.append({
                "members": members,
                "avg_distance": round(avg_dist, 3),
                "size": len(members),
            })

        islands.sort(key=lambda x: x["size"], reverse=True)
        return islands

    def find_parallel_universe(self, scope, user_id):
        result_local = self._find_parallel_in_scope(scope, user_id)

        results_cross = []
        all_keys = self.storage.keys()
        all_scopes = set()
        for k in all_keys:
            if k.startswith("sonar:") and k.endswith(":users"):
                parts = k.rsplit(":users", 1)[0]
                if parts != scope:
                    all_scopes.add(parts)

        for other_scope in all_scopes:
            cross = self._find_parallel_in_scope(other_scope, user_id)
            if cross:
                cross["scope"] = other_scope
                results_cross.append(cross)

        results_cross.sort(key=lambda x: x["similarity"], reverse=True)
        top_cross = results_cross[:3] if results_cross else []

        return {
            "local": result_local,
            "cross_scope": top_cross,
        }

    def _find_parallel_in_scope(self, scope, user_id):
        data = self.compute_distance_matrix(scope)
        if not data or user_id not in data["users"]:
            return None

        users = data["users"]
        matrix = data["matrix"]
        scores_map = data["scores"]

        interact = self.storage.get(f"{scope}:interact:{user_id}", {})
        cooccur = self.storage.get(f"{scope}:cooccur", {})

        best = None
        best_behavior_sim = -1.0

        for other in users:
            if other == user_id:
                continue
            pair_key = f"{user_id}|{other}"

            has_interaction = (
                interact.get(other, 0) > 0
                or self.storage.get(f"{scope}:interact:{other}", {}).get(user_id, 0) > 0
            )
            has_cooccur = (
                cooccur.get(pair_key, 0) > 0
                or cooccur.get(f"{other}|{user_id}", 0) > 0
            )

            if has_interaction or has_cooccur:
                continue

            scores = scores_map.get(pair_key, {})
            behavior_sim = (
                scores.get("timing", 0) * 0.35
                + scores.get("emoji", 0) * 0.25
                + scores.get("vocab", 0) * 0.40
            )

            if behavior_sim > best_behavior_sim:
                best_behavior_sim = behavior_sim
                best = {
                    "user_id": other,
                    "similarity": round(behavior_sim, 3),
                    "scores": scores,
                }

        return best

    def get_user_distances(self, scope, user_id):
        data = self.compute_distance_matrix(scope)
        if not data or user_id not in data["users"]:
            return None

        users = data["users"]
        matrix = data["matrix"]
        scores_map = data["scores"]

        distances = {}
        for other in users:
            if other == user_id:
                continue
            key = f"{user_id}|{other}"
            distances[other] = {
                "distance": round(matrix.get(key, 1.0), 3),
                "scores": scores_map.get(key, {}),
            }

        sorted_distances = dict(
            sorted(distances.items(), key=lambda x: x[1]["distance"])
        )
        return sorted_distances

    def get_user_detail(self, scope, user_id):
        timing = self.storage.get(f"{scope}:timing:{user_id}", {})
        emoji = self.storage.get(f"{scope}:emoji:{user_id}", {})
        vocab = self.storage.get(f"{scope}:vocab:{user_id}", {})
        length = self.storage.get(f"{scope}:length:{user_id}", {"total": 0, "count": 0})
        interact = self.storage.get(f"{scope}:interact:{user_id}", {})

        active_hours = sorted(timing.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h for h, _ in active_hours[:3]] if active_hours else []

        top_emoji = sorted(emoji.items(), key=lambda x: x[1], reverse=True)[:5]
        top_vocab = sorted(vocab.items(), key=lambda x: x[1], reverse=True)[:5]

        avg_len = 0
        if length.get("count", 0) > 0:
            avg_len = round(length["total"] / length["count"], 1)

        return {
            "message_count": length.get("count", 0),
            "avg_length": avg_len,
            "peak_hours": peak_hours,
            "top_emoji": top_emoji,
            "top_vocab": top_vocab,
            "interact_count": sum(interact.values()),
            "interact_targets": len(interact),
        }

    def get_interact_detail(self, scope, uid_a, uid_b):
        ia = self.storage.get(f"{scope}:interact:{uid_a}", {})
        ib = self.storage.get(f"{scope}:interact:{uid_b}", {})
        a_to_b = ia.get(uid_b, 0)
        b_to_a = ib.get(uid_a, 0)

        timing_a = self.storage.get(f"{scope}:timing:{uid_a}", {})
        timing_b = self.storage.get(f"{scope}:timing:{uid_b}", {})
        overlap = [h for h in timing_a if h in timing_b and timing_a[h] > 0 and timing_b[h] > 0]
        overlap.sort()

        return {
            "a_to_b": a_to_b,
            "b_to_a": b_to_a,
            "reply_total": a_to_b + b_to_a,
            "shared_hours": overlap,
        }

    def get_cooccur_count(self, scope, uid_a, uid_b):
        cooccur = self.storage.get(f"{scope}:cooccur", {})
        return cooccur.get(f"{uid_a}|{uid_b}", 0)
