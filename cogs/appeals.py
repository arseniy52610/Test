# cogs/appeals.py
import disnake
from disnake.ext import commands
import json
import os
import datetime
from utils.checks import has_role
from utils.helpers import load_punishments, remove_punishment

APPEALS_FILE = "data/appeals.json"


def load_appeals():
    try:
        with open(APPEALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"counter": 0, "cooldowns": {}}


def save_appeals(data):
    os.makedirs("data", exist_ok=True)
    with open(APPEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def next_appeal_number():
    data = load_appeals()
    data["counter"] = data.get("counter", 0) + 1
    if "cooldowns" not in data:
        data["cooldowns"] = {}
    save_appeals(data)
    return data["counter"]


def set_cooldown(user_id, appeal_type):
    data = load_appeals()
    if "cooldowns" not in data:
        data["cooldowns"] = {}
    user_id = str(user_id)
    if user_id not in data["cooldowns"]:
        data["cooldowns"][user_id] = {}
    expire = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).timestamp()
    data["cooldowns"][user_id][appeal_type] = expire
    save_appeals(data)


def get_cooldown(user_id, appeal_type):
    data = load_appeals()
    user_id = str(user_id)
    cd = data.get("cooldowns", {}).get(user_id, {}).get(appeal_type)
    if cd is None:
        return None
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    if now >= cd:
        # cooldown expired, clean up
        data["cooldowns"][user_id].pop(appeal_type, None)
        if not data["cooldowns"][user_id]:
            data["cooldowns"].pop(user_id, None)
        save_appeals(data)
        return None
    return cd


def _find_punishment(user_id, role_id):
    """Find punishment data for a user by role_id."""
    punishments = load_punishments()
    user_id = str(user_id)
    if user_id in punishments:
        for p in punishments[user_id]:
            if p["role_id"] == role_id:
                return p
    return None


# ========== Persistent View for /apil message ==========

class AppealButtonView(disnake.ui.View):
    """Persistent view with two buttons: appeal nedopusk and appeal ban."""

    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(
        label="Апелляция недопуска",
        style=disnake.ButtonStyle.primary,
        custom_id="appeal_nedopusk_btn",
        emoji="📋"
    )
    async def appeal_nedopusk(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await self._handle_appeal_click(inter, "nedopusk")

    @disnake.ui.button(
        label="Апелляция бана",
        style=disnake.ButtonStyle.primary,
        custom_id="appeal_ban_btn",
        emoji="🔓"
    )
    async def appeal_ban(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await self._handle_appeal_click(inter, "ban")

    async def _handle_appeal_click(self, inter: disnake.MessageInteraction, appeal_type: str):
        cog = inter.bot.get_cog("Appeals")
        if not cog:
            await inter.response.send_message("❌ Система апелляций не загружена.", ephemeral=True)
            return

        config = cog.config
        roles = config.get("roles", {})

        # Check if user has the punishment role
        role_key = appeal_type  # "nedopusk" or "ban"
        role_id = roles.get(role_key)
        if not role_id:
            await inter.response.send_message("❌ Роль наказания не настроена в конфиге.", ephemeral=True)
            return

        if not has_role(inter.author, role_id):
            type_name = "недопуска" if appeal_type == "nedopusk" else "бана"
            await inter.response.send_message(
                f"❌ У вас нет активного {type_name}.", ephemeral=True
            )
            return

        # Check cooldown
        cd = get_cooldown(inter.author.id, appeal_type)
        if cd is not None:
            await inter.response.send_message(
                f"❌ Вы уже подавали апелляцию. Повторная подача доступна <t:{int(cd)}:R>.",
                ephemeral=True
            )
            return

        # Show modal
        modal = AppealSubmitModal(appeal_type)
        await inter.response.send_modal(modal)


# ========== Modal for user to fill appeal ==========

class AppealSubmitModal(disnake.ui.Modal):
    def __init__(self, appeal_type: str):
        self.appeal_type = appeal_type
        type_name = "недопуска" if appeal_type == "nedopusk" else "бана"
        components = [
            disnake.ui.TextInput(
                label="Доказательства невиновности",
                placeholder="Опишите почему наказание должно быть снято...",
                custom_id="evidence",
                style=disnake.TextInputStyle.paragraph,
                max_length=1000,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Дополнительная информация",
                placeholder="Ссылки на скриншоты, видео и т.д. (необязательно)",
                custom_id="extra_info",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=False,
            ),
        ]
        super().__init__(
            title=f"Апелляция {type_name}",
            custom_id=f"appeal_submit_{appeal_type}",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        cog = inter.bot.get_cog("Appeals")
        if not cog:
            await inter.response.send_message("❌ Ошибка системы.", ephemeral=True)
            return

        evidence = inter.text_values["evidence"]
        extra_info = inter.text_values.get("extra_info", "").strip()

        config = cog.config
        roles = config.get("roles", {})
        role_id = roles.get(self.appeal_type)

        # Get punishment data
        punishment = _find_punishment(inter.author.id, role_id)

        # Generate appeal number
        appeal_num = next_appeal_number()

        # Determine target channel
        if self.appeal_type == "nedopusk":
            channel_id = config.get("appeal_nedopusk_channel")
            type_title = "недопуска"
            color = disnake.Color.orange()
        else:
            channel_id = config.get("appeal_ban_channel")
            type_title = "бана"
            color = disnake.Color.red()

        if not channel_id:
            await inter.response.send_message(
                "❌ Канал для апелляций не настроен.", ephemeral=True
            )
            return

        guild = inter.guild
        channel = guild.get_channel(channel_id) if guild else None
        if not channel:
            await inter.response.send_message(
                "❌ Канал для апелляций не найден.", ephemeral=True
            )
            return

        # Build embed matching the screenshot format
        user = inter.author
        avatar_url = user.display_avatar.url

        description = (
            f"> **Отправитель:**\n"
            f"• {user.mention}\n"
            f"• **Имя:** {user.display_name}\n"
            f"• **ID:** {user.id}\n"
            f"• **Аватар:** [ТЫК]({avatar_url})\n\n"
        )

        # Punishment issuer info
        if punishment:
            mod_id = punishment.get("moderator_id")
            if mod_id and guild:
                mod = guild.get_member(int(mod_id))
                if mod:
                    description += (
                        f"> **Выдал наказание:**\n"
                        f"• {mod.mention}\n"
                        f"• **Имя:** {mod.display_name}\n"
                        f"• **ID:** {mod.id}\n\n"
                    )
                else:
                    description += (
                        f"> **Выдал наказание:**\n"
                        f"• <@{mod_id}>\n"
                        f"• **ID:** {mod_id}\n\n"
                    )
            else:
                description += f"> **Выдал наказание:**\n• Не найдено\n\n"

            # Reason
            reason = punishment.get("reason", "Не указана")
            description += f"> **Причина {type_title}:**\n```{reason}```\n"

            # Date
            issued_at = punishment.get("issued_at")
            if issued_at:
                description += f"> **Дата {type_title}:**\n```{datetime.datetime.fromtimestamp(issued_at, tz=datetime.timezone.utc).strftime('%d.%m.%Y, %H:%M')}```\n"
        else:
            description += (
                f"> **Выдал наказание:**\n• Не найдено\n\n"
                f"> **Причина {type_title}:**\n```Не найдено в системе```\n"
            )

        # Evidence
        description += f"> **Доказательства невиновности:**\n```{evidence}```\n"

        if extra_info:
            description += f"> **Дополнительная информация:**\n```{extra_info}```\n"

        description += f"• **Статус:** Ожидание"

        embed = disnake.Embed(
            title=f"Аппеляция {type_title} | No {appeal_num}",
            description=description,
            color=color,
        )
        embed.set_thumbnail(url=avatar_url)

        # Determine ping role
        ping_content = ""
        if self.appeal_type == "nedopusk":
            # Nedopusk → always ping otvechaet_support
            ping_role_id = roles.get("otvechaet_support")
            if ping_role_id:
                ping_content = f"<@&{ping_role_id}>"
        elif self.appeal_type == "ban" and punishment:
            # Ban → ping otvechaet based on who issued the ban
            mod_id = punishment.get("moderator_id")
            if mod_id and guild:
                mod = guild.get_member(int(mod_id))
                if mod:
                    # Check which staff role the mod has, ping corresponding otvechaet
                    staff_to_otvechaet = {
                        "support": "otvechaet_support",
                        "moderator": "otvechaet_moderator",
                        "eventsmod": "otvechaet_eventsmod",
                        "creative": "otvechaet_creative",
                        "clanmaster": "otvechaet_clanmaster",
                        "closemaker": "otvechaet_closemaker",
                        "broadcaster": "otvechaet_broadcaster",
                    }
                    for staff_key, otv_key in staff_to_otvechaet.items():
                        staff_rid = roles.get(staff_key)
                        if staff_rid and has_role(mod, staff_rid):
                            otv_rid = roles.get(otv_key)
                            if otv_rid:
                                ping_content = f"<@&{otv_rid}>"
                            break

        # Buttons for admins
        view = AppealDecisionView(user.id, self.appeal_type, appeal_num)
        await channel.send(content=ping_content, embed=embed, view=view)

        await inter.response.send_message(
            f"✅ Ваша апелляция №{appeal_num} отправлена на рассмотрение.",
            ephemeral=True,
        )


# ========== Decision buttons (Approve / Reject) ==========

class AppealDecisionView(disnake.ui.View):
    """View with Approve/Reject buttons. Persistent via custom_id."""

    def __init__(self, target_id: int, appeal_type: str, appeal_num: int):
        super().__init__(timeout=None)
        self.add_item(AppealApproveButton(target_id, appeal_type, appeal_num))
        self.add_item(AppealRejectButton(target_id, appeal_type, appeal_num))


class AppealApproveButton(disnake.ui.Button):
    def __init__(self, target_id, appeal_type, appeal_num):
        super().__init__(
            label="Одобрить",
            style=disnake.ButtonStyle.success,
            custom_id=f"appeal_approve_{appeal_type}_{target_id}_{appeal_num}",
        )

    async def callback(self, inter: disnake.MessageInteraction):
        cog = inter.bot.get_cog("Appeals")
        if not cog or not cog._is_admin(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return

        parts = self.custom_id.split("_")
        # appeal_approve_{type}_{target_id}_{num}
        appeal_type = parts[2]
        target_id = int(parts[3])
        appeal_num = int(parts[4])

        modal = AppealReasonModal(
            action="approve",
            appeal_type=appeal_type,
            target_id=target_id,
            appeal_num=appeal_num,
            guild=inter.guild,
            admin=inter.author,
            message=inter.message,
        )
        await inter.response.send_modal(modal)


class AppealRejectButton(disnake.ui.Button):
    def __init__(self, target_id, appeal_type, appeal_num):
        super().__init__(
            label="Отклонить",
            style=disnake.ButtonStyle.danger,
            custom_id=f"appeal_reject_{appeal_type}_{target_id}_{appeal_num}",
        )

    async def callback(self, inter: disnake.MessageInteraction):
        cog = inter.bot.get_cog("Appeals")
        if not cog or not cog._is_admin(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return

        parts = self.custom_id.split("_")
        appeal_type = parts[2]
        target_id = int(parts[3])
        appeal_num = int(parts[4])

        modal = AppealReasonModal(
            action="reject",
            appeal_type=appeal_type,
            target_id=target_id,
            appeal_num=appeal_num,
            guild=inter.guild,
            admin=inter.author,
            message=inter.message,
        )
        await inter.response.send_modal(modal)


# ========== Modal for admin reason ==========

class AppealReasonModal(disnake.ui.Modal):
    def __init__(self, action, appeal_type, target_id, appeal_num, guild, admin, message):
        self.action = action  # "approve" or "reject"
        self.appeal_type = appeal_type
        self.target_id = target_id
        self.appeal_num = appeal_num
        self.guild = guild
        self.admin = admin
        self.original_message = message

        action_name = "одобрения" if action == "approve" else "отклонения"
        components = [
            disnake.ui.TextInput(
                label=f"Причина {action_name}",
                placeholder="Укажите причину...",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=True,
            ),
        ]
        super().__init__(
            title=f"Причина {action_name} апелляции №{appeal_num}",
            custom_id=f"appeal_reason_{action}_{appeal_type}_{target_id}_{appeal_num}",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        cog = inter.bot.get_cog("Appeals")
        if not cog:
            await inter.response.send_message("❌ Ошибка системы.", ephemeral=True)
            return

        reason = inter.text_values["reason"]
        config = cog.config
        roles = config.get("roles", {})

        target = self.guild.get_member(self.target_id)
        type_name = "недопуска" if self.appeal_type == "nedopusk" else "бана"

        if self.action == "approve":
            # === APPROVE ===
            if target:
                role_id = roles.get(self.appeal_type)
                if role_id:
                    role = self.guild.get_role(role_id)
                    if role and role in target.roles:
                        await target.remove_roles(role, reason=f"Апелляция №{self.appeal_num} одобрена")
                    remove_punishment(self.target_id, role_id)

                # For nedopusk: give unverified role
                if self.appeal_type == "nedopusk":
                    unverified_id = roles.get("unverified")
                    if unverified_id:
                        unverified_role = self.guild.get_role(unverified_id)
                        if unverified_role:
                            await target.add_roles(unverified_role, reason=f"Апелляция №{self.appeal_num} одобрена")

                # DM user
                try:
                    await target.send(
                        f"✅ **Ваша апелляция {type_name} №{self.appeal_num} одобрена.**\n"
                        f"**Причина:** {reason}\n"
                        f"**Рассмотрел:** {self.admin.display_name}"
                    )
                except:
                    pass

            # Update embed
            await self._update_embed(inter, "✅ Одобрено", disnake.Color.green(), reason)

        else:
            # === REJECT ===
            set_cooldown(self.target_id, self.appeal_type)

            if target:
                try:
                    await target.send(
                        f"❌ **Ваша апелляция {type_name} №{self.appeal_num} отклонена.**\n"
                        f"**Причина:** {reason}\n"
                        f"**Рассмотрел:** {self.admin.display_name}\n"
                        f"Повторная подача апелляции доступна через **7 дней**."
                    )
                except:
                    pass

            await self._update_embed(inter, "❌ Отклонено", disnake.Color.dark_grey(), reason)

    async def _update_embed(self, inter, status_text, color, reason):
        """Update the original appeal embed with the decision."""
        msg = self.original_message
        if not msg:
            await inter.response.send_message(f"{status_text} — апелляция обработана.", ephemeral=True)
            return

        old_embed = msg.embeds[0] if msg.embeds else None
        if old_embed:
            new_desc = old_embed.description or ""
            # Replace status line
            new_desc = new_desc.replace("• **Статус:** Ожидание", f"• **Статус:** {status_text}")
            new_desc += (
                f"\n\n> **Решение:**\n"
                f"• **Рассмотрел:** {self.admin.mention}\n"
                f"• **Причина:** {reason}"
            )
            new_embed = disnake.Embed(
                title=old_embed.title,
                description=new_desc,
                color=color,
            )
            if old_embed.thumbnail:
                new_embed.set_thumbnail(url=old_embed.thumbnail.url)
        else:
            new_embed = disnake.Embed(
                title=f"Апелляция №{self.appeal_num}",
                description=f"{status_text}\nПричина: {reason}",
                color=color,
            )

        # Disable buttons
        disabled_view = disnake.ui.View()
        disabled_view.add_item(disnake.ui.Button(
            label="Одобрить", style=disnake.ButtonStyle.success, disabled=True, custom_id="disabled_approve"
        ))
        disabled_view.add_item(disnake.ui.Button(
            label="Отклонить", style=disnake.ButtonStyle.danger, disabled=True, custom_id="disabled_reject"
        ))

        await msg.edit(embed=new_embed, view=disabled_view)
        await inter.response.send_message(f"{status_text} — апелляция №{self.appeal_num} обработана.", ephemeral=True)


# ========== Cog ==========

class Appeals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open("config.json", encoding="utf-8") as f:
            self.config = json.load(f)
        self._ready = False
        self.webhook = None

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready:
            return
        self._ready = True

        self.bot.add_view(AppealButtonView())

        # Create or find webhook in appeal submit channel
        channel_id = self.config.get("appeal_submit_channel")
        if channel_id:
            for guild in self.bot.guilds:
                channel = guild.get_channel(channel_id)
                if channel:
                    webhooks = await channel.webhooks()
                    for wh in webhooks:
                        if wh.name == "Appeals":
                            self.webhook = wh
                            break
                    if not self.webhook:
                        self.webhook = await channel.create_webhook(name="Appeals")
                    print(f"[Appeals] Webhook ready in #{channel.name}")
                    break

    def _check_permission(self, member, role_key):
        role_id = self.config["roles"].get(role_key)
        if not role_id:
            return False
        return has_role(member, role_id)

    def _is_admin(self, member):
        """Check if member is admin/developer/owner."""
        for role_key in ["admin", "developer", "owner"]:
            if self._check_permission(member, role_key):
                return True
        return False

    @commands.slash_command(name="apil", description="Управление апелляциями")
    async def apil(self, inter):
        pass

    @apil.sub_command(name="panel", description="Отправить панель апелляций")
    async def apil_panel(self, inter: disnake.AppCmdInter):
        if not self._is_admin(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return

        if not self.webhook:
            await inter.response.send_message("❌ Вебхук не готов. Проверьте appeal_submit_channel в конфиге.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        embed = disnake.Embed(
            title="📋 Апелляции",
            description=(
                "Если вы считаете, что ваше наказание было выдано несправедливо, "
                "вы можете подать апелляцию, нажав на соответствующую кнопку ниже.\n\n"
                "• **Апелляция недопуска** — если вам выдан недопуск\n"
                "• **Апелляция бана** — если вам выдан бан\n\n"
                "⚠️ После отклонения апелляции повторная подача доступна через **7 дней**."
            ),
            color=disnake.Color.blurple(),
        )

        view = AppealButtonView()
        bot_user = self.bot.user
        await self.webhook.send(
            embed=embed,
            view=view,
            username=bot_user.display_name,
            avatar_url=bot_user.display_avatar.url,
            wait=True,
        )
        await inter.edit_original_response(content="✅ Панель апелляций отправлена.")

    @apil.sub_command(name="clean", description="Удалить отклонённые апелляции из канала")
    async def apil_clean(self, inter: disnake.AppCmdInter):
        if not self._is_admin(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        deleted = 0
        for channel_id in [self.config.get("appeal_nedopusk_channel"), self.config.get("appeal_ban_channel")]:
            if not channel_id:
                continue
            channel = inter.guild.get_channel(channel_id)
            if not channel:
                continue

            async for msg in channel.history(limit=200):
                if msg.embeds:
                    desc = msg.embeds[0].description or ""
                    if "❌ Отклонено" in desc:
                        await msg.delete()
                        deleted += 1

        await inter.edit_original_response(content=f"✅ Удалено отклонённых апелляций: {deleted}")


def setup(bot):
    bot.add_cog(Appeals(bot))
