import disnake
from disnake.ext import commands
import json
import time
import datetime
import os
from collections import defaultdict


DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

PUNISHMENT_TYPE_NAMES = {
    "ban": "Бан",
    "mute_text": "Текстовый мут",
    "mute_voice": "Голосовой мут",
    "suspension": "Отстранение",
    "remark": "Замечание",
    "nedopusk": "Недопуск",
    "support_warn": "Предупреждение",
    "moderator_warn": "Предупреждение",
    "reprimand_support": "Выговор",
    "reprimand_moderator": "Выговор",
    "reprimand_control": "Выговор",
    "reprimand_admin": "Выговор",
}


def format_duration(seconds):
    seconds = int(seconds)
    if seconds <= 0:
        return "0 сек."
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h:
        parts.append(f"{h} ч.")
    if m:
        parts.append(f"{m} мин.")
    if s or not parts:
        parts.append(f"{s} сек.")
    return " ".join(parts)


class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = {}  # {user_id: {start, channel_id, channel_name}}
        self.data_file = "data/voice.json"

    def load_data(self):
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if not isinstance(raw, dict):
                    return {}
                result = {}
                for uid, udata in raw.items():
                    if isinstance(udata, dict) and "sessions" in udata:
                        result[uid] = udata
                    elif isinstance(udata, dict):
                        # migrate old format: {"verification": X, "mod": Y}
                        total = udata.get("verification", 0) + udata.get("mod", 0)
                        result[uid] = {"sessions": [], "total": float(total), "last_seen": 0.0}
                return result
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_data(self, data):
        os.makedirs("data", exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _get_config(self):
        with open("config.json", encoding="utf-8") as f:
            return json.load(f)

    def _get_user_group(self, member, config):
        role_ids = config.get("roles", {})
        priority = [
            ("owner", "Owner"), ("developer", "Developer"), ("admin", "Admin"),
            ("moderator", "Moderator"), ("support", "Support"),
            ("eventsmod", "Events"), ("creative", "Creative"),
            ("clanmaster", "Clan"), ("closemaker", "Close"), ("broadcaster", "Broadcast"),
        ]
        member_role_ids = {r.id for r in member.roles}
        for key, label in priority:
            rid = role_ids.get(key)
            if rid and rid in member_role_ids:
                return label
        return "Участник"

    def _get_week_bounds(self, offset=0):
        today = datetime.datetime.utcnow().date()
        monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=offset)
        sunday = monday + datetime.timedelta(days=6)
        return monday, sunday

    def _get_sessions_in_range(self, sessions, start_date, end_date):
        start_ts = datetime.datetime.combine(
            start_date, datetime.time.min, tzinfo=datetime.timezone.utc
        ).timestamp()
        end_ts = datetime.datetime.combine(
            end_date, datetime.time.max, tzinfo=datetime.timezone.utc
        ).timestamp()
        return [s for s in sessions if start_ts <= s.get("start", 0) <= end_ts]

    def _sessions_total(self, sessions):
        return sum(s.get("end", s.get("start", 0)) - s.get("start", 0) for s in sessions)

    def _sessions_by_channel(self, sessions):
        by_ch = {}
        for s in sessions:
            cid = str(s.get("channel_id", 0))
            if cid not in by_ch:
                by_ch[cid] = {"name": s.get("channel_name", "Неизвестно"), "total": 0.0}
            by_ch[cid]["total"] += s.get("end", s.get("start", 0)) - s.get("start", 0)
        return by_ch

    def _sessions_by_day(self, sessions, start_date, end_date):
        days = {}
        cur = start_date
        while cur <= end_date:
            days[cur.isoformat()] = {"total": 0.0, "channels": {}}
            cur += datetime.timedelta(days=1)
        for s in sessions:
            day = datetime.datetime.utcfromtimestamp(s["start"]).date().isoformat()
            if day in days:
                dur = s.get("end", s["start"]) - s["start"]
                days[day]["total"] += dur
                cid = str(s.get("channel_id", 0))
                if cid not in days[day]["channels"]:
                    days[day]["channels"][cid] = {"name": s.get("channel_name", "Неизвестно"), "total": 0.0}
                days[day]["channels"][cid]["total"] += dur
        return days

    def _sessions_by_hour(self, sessions, date_str):
        hours = {str(h): {"total": 0.0, "channels": {}} for h in range(24)}
        for s in sessions:
            s_date = datetime.datetime.utcfromtimestamp(s["start"]).date().isoformat()
            if s_date == date_str:
                hour = str(datetime.datetime.utcfromtimestamp(s["start"]).hour)
                dur = s.get("end", s["start"]) - s["start"]
                hours[hour]["total"] += dur
                cid = str(s.get("channel_id", 0))
                if cid not in hours[hour]["channels"]:
                    hours[hour]["channels"][cid] = {"name": s.get("channel_name", "Неизвестно"), "total": 0.0}
                hours[hour]["channels"][cid]["total"] += dur
        return hours

    def _build_embed(self, user, user_data, group, start_date, end_date, selected_day=None):
        sessions = user_data.get("sessions", [])
        range_sessions = self._get_sessions_in_range(sessions, start_date, end_date)
        period_total = self._sessions_total(range_sessions)
        all_time = user_data.get("total", 0.0)
        last_seen = user_data.get("last_seen", 0.0)

        embed = disnake.Embed(
            title=f"Голосовая активность — {user.display_name}",
            color=0x2b2d31
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.description = (
            f"• **Группа состава**: {group}\n"
            f"• **Период**: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n"
            f"• **За выбранный период**: {format_duration(period_total)}\n"
            f"• **За всё время**: {format_duration(all_time)}\n"
            f"• **Последняя активность**: " + (
                f"<t:{int(last_seen)}:F> (<t:{int(last_seen)}:R>)" if last_seen else "—"
            )
        )

        if selected_day:
            day_date = datetime.date.fromisoformat(selected_day)
            day_name = DAYS_RU[day_date.weekday()]
            day_sessions = [
                s for s in sessions
                if datetime.datetime.utcfromtimestamp(s["start"]).date().isoformat() == selected_day
            ]
            day_total = self._sessions_total(day_sessions)

            embed.add_field(
                name=f"🛡️ {day_name} ({day_date.strftime('%d.%m.%Y')}):",
                value=f"• **За день**: {format_duration(day_total)}",
                inline=False
            )

            hourly = self._sessions_by_hour(sessions, selected_day)
            active_hours = [(int(h), d) for h, d in hourly.items() if d["total"] > 0]
            active_hours.sort(key=lambda x: x[0])

            if active_hours:
                for hour, hdata in active_hours:
                    ch_lines = []
                    for cid, chinfo in sorted(hdata["channels"].items(), key=lambda x: -x[1]["total"]):
                        if chinfo["total"] > 0:
                            ch_lines.append(f"`{chinfo['name']}`: {format_duration(chinfo['total'])}")
                    val = format_duration(hdata["total"])
                    if ch_lines:
                        val += "\n" + "\n".join(ch_lines)
                    embed.add_field(
                        name=f"{hour:02d}:00 — {hour + 1:02d}:00",
                        value=val,
                        inline=True
                    )
        else:
            # Period categories
            by_channel = self._sessions_by_channel(range_sessions)
            if by_channel:
                cat_lines = [
                    f"**{chinfo['name']}**: {format_duration(chinfo['total'])}"
                    for chinfo in sorted(by_channel.values(), key=lambda x: -x["total"])
                    if chinfo["total"] > 0
                ]
                if cat_lines:
                    embed.add_field(name="• По категориям:", value="\n".join(cat_lines), inline=False)

            # Day breakdown
            days_data = self._sessions_by_day(range_sessions, start_date, end_date)
            cur = start_date
            while cur <= end_date:
                day_key = cur.isoformat()
                day_info = days_data.get(day_key, {"total": 0.0, "channels": {}})
                day_name = DAYS_RU[cur.weekday()]

                val = f"• **За день**: {format_duration(day_info['total'])}"
                if day_info["total"] > 0 and day_info["channels"]:
                    ch_lines = [
                        f"`{chinfo['name']}`: {format_duration(chinfo['total'])}"
                        for chinfo in sorted(day_info["channels"].values(), key=lambda x: -x["total"])
                        if chinfo["total"] > 0
                    ]
                    if ch_lines:
                        val += "\n• **По категориям**:\n" + "\n".join(ch_lines)

                embed.add_field(
                    name=f"🛡️ {day_name} ({cur.strftime('%d.%m.%Y')}):",
                    value=val,
                    inline=False
                )
                cur += datetime.timedelta(days=1)

        return embed

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        user_id = str(member.id)
        data = self.load_data()

        async def finish_session():
            if user_id in self.active:
                sess = self.active.pop(user_id)
                duration = time.time() - sess["start"]
                if duration >= 10:
                    if user_id not in data:
                        data[user_id] = {"sessions": [], "total": 0.0, "last_seen": 0.0}
                    data[user_id].setdefault("sessions", [])
                    data[user_id]["sessions"].append({
                        "start": sess["start"],
                        "end": time.time(),
                        "channel_id": sess["channel_id"],
                        "channel_name": sess["channel_name"],
                    })
                    data[user_id]["total"] = data[user_id].get("total", 0.0) + duration
                    data[user_id]["last_seen"] = time.time()

        await finish_session()

        if after.channel:
            self.active[user_id] = {
                "start": time.time(),
                "channel_id": after.channel.id,
                "channel_name": after.channel.name,
            }

        self.save_data(data)

    @commands.slash_command(name="voice", description="Голосовая активность участника")
    async def voice(
        self,
        inter: disnake.AppCmdInter,
        user: disnake.Member = commands.Param(name="участник", default=None)
    ):
        if not user:
            user = inter.author

        config = self._get_config()
        data = self.load_data()
        user_data = data.get(str(user.id), {"sessions": [], "total": 0.0, "last_seen": 0.0})
        group = self._get_user_group(user, config)
        start_date, end_date = self._get_week_bounds(0)

        embed = self._build_embed(user, user_data, group, start_date, end_date)
        view = VoiceView(self, user, user_data, group, 0, None)
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)


class VoiceView(disnake.ui.View):
    def __init__(self, cog, user, user_data, group, week_offset, selected_day):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.user_data = user_data
        self.group = group
        self.week_offset = week_offset
        self.selected_day = selected_day
        self._rebuild_selects()

    def _rebuild_selects(self):
        self.clear_items()
        start_date, end_date = self.cog._get_week_bounds(self.week_offset)
        sessions = self.user_data.get("sessions", [])
        range_sessions = self.cog._get_sessions_in_range(sessions, start_date, end_date)

        days_with_activity = set()
        for s in range_sessions:
            day = datetime.datetime.utcfromtimestamp(s["start"]).date().isoformat()
            days_with_activity.add(day)

        # Day select
        day_options = []
        cur = start_date
        while cur <= end_date:
            key = cur.isoformat()
            day_name = DAYS_RU[cur.weekday()]
            label = f"{day_name} ({cur.strftime('%d.%m.%Y')})"
            day_options.append(disnake.SelectOption(
                label=label,
                value=key,
                default=(self.selected_day == key),
                description="Есть активность" if key in days_with_activity else "Нет активности",
            ))
            cur += datetime.timedelta(days=1)

        self.add_item(DaySelect(day_options))

        # Week period select
        week_options = []
        for offset in range(0, -4, -1):
            s, e = self.cog._get_week_bounds(offset)
            label = f"{s.strftime('%d.%m.%Y')} - {e.strftime('%d.%m.%Y')}"
            week_options.append(disnake.SelectOption(
                label=label,
                value=str(offset),
                default=(self.week_offset == offset),
                description="Текущая неделя" if offset == 0 else f"{abs(offset)} нед. назад"
            ))
        self.add_item(WeekSelect(week_options))


class DaySelect(disnake.ui.StringSelect):
    def __init__(self, options):
        super().__init__(
            placeholder="Выберите дату",
            options=options,
            min_values=1,
            max_values=1,
            row=0
        )

    async def callback(self, inter: disnake.MessageInteraction):
        view: VoiceView = self.view
        selected = self.values[0]
        view.selected_day = selected
        start_date, end_date = view.cog._get_week_bounds(view.week_offset)

        data = view.cog.load_data()
        view.user_data = data.get(str(view.user.id), {"sessions": [], "total": 0.0, "last_seen": 0.0})

        embed = view.cog._build_embed(
            view.user, view.user_data, view.group,
            start_date, end_date, selected_day=selected
        )
        view._rebuild_selects()
        await inter.response.edit_message(embed=embed, view=view)


class WeekSelect(disnake.ui.StringSelect):
    def __init__(self, options):
        super().__init__(
            placeholder="Выберите период",
            options=options,
            min_values=1,
            max_values=1,
            row=1
        )

    async def callback(self, inter: disnake.MessageInteraction):
        view: VoiceView = self.view
        view.week_offset = int(self.values[0])
        view.selected_day = None
        start_date, end_date = view.cog._get_week_bounds(view.week_offset)

        data = view.cog.load_data()
        view.user_data = data.get(str(view.user.id), {"sessions": [], "total": 0.0, "last_seen": 0.0})

        embed = view.cog._build_embed(
            view.user, view.user_data, view.group,
            start_date, end_date, selected_day=None
        )
        view._rebuild_selects()
        await inter.response.edit_message(embed=embed, view=view)


def setup(bot):
    bot.add_cog(Voice(bot))
