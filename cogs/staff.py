import disnake
from disnake.ext import commands
import json
import datetime
import re
from utils.checks import has_role
from utils.logger import log_action

class StaffControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open("config.json") as f:
            self.config = json.load(f)
        self.role_levels = self.config.get("role_levels", {})

    def _has_global_access(self, member):
        global_roles = ["admin", "developer", "owner"]
        for role_key in global_roles:
            role_id = self.config["roles"].get(role_key)
            if role_id and has_role(member, role_id):
                return True
        return False

    def _get_member_branches(self, member):
        branches = []
        branch_role_keys = ["support", "moderator", "eventsmod", "creative", "clanmaster", "closemaker", "broadcaster"]
        for key in branch_role_keys:
            role_id = self.config["roles"].get(key)
            if role_id and has_role(member, role_id):
                branches.append(key)
        return branches

    def _get_member_level(self, member):
        if has_role(member, self.config["roles"]["owner"]):
            return 7
        if has_role(member, self.config["roles"]["developer"]):
            return 6
        if has_role(member, self.config["roles"]["admin"]):
            return 5
        if has_role(member, self.config["roles"]["admin_branch"]):
            return 4
        if has_role(member, self.config["roles"]["curator"]):
            return 3
        for key in ["otvechaet_support", "otvechaet_moderator", "otvechaet_eventsmod", "otvechaet_creative",
                    "otvechaet_clanmaster", "otvechaet_closemaker", "otvechaet_broadcaster"]:
            if has_role(member, self.config["roles"].get(key)):
                return 2
        return 1

    def _can_use_commands(self, member):
        return self._get_member_level(member) >= 3 or self._has_global_access(member)

    def _get_role_key_by_id(self, role_id):
        for key, rid in self.config["roles"].items():
            if rid == role_id and key in self.role_levels:
                return key
        return None

    def _can_manage_role(self, executor, target_role_key):
        if target_role_key not in self.role_levels:
            return False
        target_level = self.role_levels[target_role_key]["level"]
        target_branch = self.role_levels[target_role_key]["branch"]

        exec_level = self._get_member_level(executor)
        exec_branches = self._get_member_branches(executor)

        if self._has_global_access(executor):
            return exec_level > target_level

        if exec_level == 4:  # admin_branch
            if target_branch == "global":
                return False
            return target_branch in exec_branches and exec_level > target_level

        if exec_level == 3:  # curator
            if target_branch == "global":
                return False
            return target_branch in exec_branches and target_level <= 2 and exec_level > target_level

        return False

    @commands.slash_command(name="staff", description="Управление составом")
    async def staff(self, inter: disnake.AppCmdInter):
        pass

    @staff.sub_command(name="promote", description="Выдать стафф-роль пользователю")
    async def staff_promote(self, inter: disnake.AppCmdInter):
        if not self._can_use_commands(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return
        view = StaffRoleSelectView(self, inter.author, action="promote")
        embed = disnake.Embed(description="> Выберете роль для выдачи")
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)

    @staff.sub_command(name="demote", description="Снять стафф-роль с одного или нескольких пользователей")
    async def staff_demote(self, inter: disnake.AppCmdInter):
        if not self._can_use_commands(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return
        view = StaffRoleSelectView(self, inter.author, action="demote")
        embed = disnake.Embed(description="> Выберете роль для снятия")
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)


class StaffRoleSelectView(disnake.ui.View):
    def __init__(self, cog, executor, action):
        super().__init__(timeout=60)
        self.cog = cog
        self.executor = executor
        self.action = action

        role_select = disnake.ui.RoleSelect(
            placeholder="Выберите роль...",
            min_values=1,
            max_values=1,
            custom_id="staff_role_select"
        )
        role_select.callback = self.role_select_callback
        self.add_item(role_select)

    async def role_select_callback(self, inter: disnake.MessageInteraction):
        role = inter.guild.get_role(int(inter.data.values[0]))
        if not role:
            await inter.response.send_message("❌ Роль не найдена.", ephemeral=True)
            return

        if not self.cog._has_global_access(self.executor):
            role_key = self.cog._get_role_key_by_id(role.id)
            if not role_key or not self.cog._can_manage_role(self.executor, role_key):
                await inter.response.send_message("❌ У вас нет прав для управления этой ролью.", ephemeral=True)
                return

        if self.action == "promote":
            user_embed_text = "> Выберете 1 или несколько пользователей для выдачи роли"
        else:
            user_embed_text = "> Выберете 1 или несколько пользователей для снятия роли"
        embed = disnake.Embed(description=user_embed_text)
        view = StaffUserSelectView(self.cog, self.executor, self.action, role)
        await inter.response.edit_message(embed=embed, view=view)


class StaffUserSelectView(disnake.ui.View):
    def __init__(self, cog, executor, action, role):
        super().__init__(timeout=60)
        self.cog = cog
        self.executor = executor
        self.action = action
        self.role = role

        user_select = disnake.ui.UserSelect(
            placeholder="Выберите пользователей...",
            min_values=1,
            max_values=25,
            custom_id="staff_user_select"
        )
        user_select.callback = self.user_select_callback
        self.add_item(user_select)

    async def user_select_callback(self, inter: disnake.MessageInteraction):
        role = self.role

        if not self.cog._has_global_access(self.executor):
            role_key = self.cog._get_role_key_by_id(role.id)
            if not role_key or not self.cog._can_manage_role(self.executor, role_key):
                await inter.response.send_message("❌ У вас нет прав для управления этой ролью.", ephemeral=True)
                return

        members = []
        not_found = []
        no_role = []
        for uid_str in inter.data.values:
            uid = int(uid_str)
            member = inter.guild.get_member(uid)
            if not member:
                not_found.append(str(uid))
                continue

            if self.action == "promote":
                if role in member.roles:
                    no_role.append(member.display_name)
                else:
                    members.append(member)
            else:
                if role in member.roles:
                    members.append(member)
                else:
                    no_role.append(member.display_name)

        if not members:
            msg = "❌ Нет подходящих пользователей для выполнения действия."
            if not_found:
                msg += f"\n❌ Не найдены: {', '.join(not_found)}"
            if no_role:
                if self.action == "promote":
                    msg += f"\n⚠️ Уже имеют роль: {', '.join(no_role)}"
                else:
                    msg += f"\n⚠️ Не имеют роли: {', '.join(no_role)}"
            await inter.response.send_message(msg, ephemeral=True)
            return

        # Для обоих действий показываем модал с причиной
        modal = StaffReasonModal(
            cog=self.cog,
            action=self.action,
            role=role,
            members=members,
            not_found=not_found,
            no_role=no_role,
            guild=inter.guild,
            author=inter.author,
        )
        await inter.response.send_modal(modal)


class StaffReasonModal(disnake.ui.Modal):
    def __init__(self, cog, action, role, members, not_found, no_role, guild, author):
        self.cog = cog
        self.action = action
        self.role = role
        self.members = members
        self.not_found = not_found
        self.no_role = no_role
        self.guild = guild
        self.author = author

        if action == "promote":
            label = "Причина выдачи"
            placeholder = "Укажите причину выдачи роли"
            title = f"Выдача роли {role.name}"
        else:
            label = "Причина снятия"
            placeholder = "Укажите причину снятия роли"
            title = f"Снятие роли {role.name}"

        components = [
            disnake.ui.TextInput(
                label=label,
                placeholder=placeholder,
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
            )
        ]
        super().__init__(title=title, components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        reason = inter.text_values["reason"]
        action_word = "Выдача" if self.action == "promote" else "Снятие"
        audit_reason = f"{action_word} через /staff {self.action} | {reason} | {self.author}"

        for member in self.members:
            if self.action == "promote":
                await member.add_roles(self.role, reason=audit_reason)
            else:
                await member.remove_roles(self.role, reason=audit_reason)

        # Отправляем лог используя сохранённые guild и author
        await self._send_log(reason)

        action_done = "выдана" if self.action == "promote" else "снята"
        msg = f"✅ Роль {self.role.name} успешно {action_done} у {len(self.members)} пользователей."
        if self.not_found:
            msg += f"\n❌ Не найдены: {', '.join(self.not_found)}"
        if self.no_role:
            if self.action == "promote":
                msg += f"\n⚠️ Уже имеют роль: {', '.join(self.no_role)}"
            else:
                msg += f"\n⚠️ Не имеют роли: {', '.join(self.no_role)}"
        await inter.response.send_message(msg, ephemeral=True)

    async def _send_log(self, reason):
        if self.action == "demote":
            channel_id = self.cog.config.get("staff_log_channel", self.cog.config["log_channel"])
        else:
            channel_id = self.cog.config["log_channel"]

        channel = self.guild.get_channel(channel_id)
        if not channel:
            return

        title = "Выдача стафф роли" if self.action == "promote" else "Снятие со стафф роли"
        color = disnake.Color.green() if self.action == "promote" else disnake.Color.red()

        role_line = f"{self.role.name} ({self.role.id})"
        users_lines = "\n".join(f"• {u.mention} [{u.display_name}]" for u in self.members)

        description = (
            f"> **Роль:**\n```{role_line}```\n"
            f"> **Исполнитель:**\n"
            f"• {self.author.mention}\n"
            f"• **Имя:** {self.author.display_name}\n"
            f"• **ID:** {self.author.id}\n"
            f"> **Причина:**\n```{reason}```\n"
            f"> **Пользователи:**\n{users_lines}"
        )

        embed = disnake.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        await channel.send(embed=embed)


def setup(bot):
    bot.add_cog(StaffControl(bot))