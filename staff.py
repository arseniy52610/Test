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

    # ---- все ваши исходные функции остались без изменений ----
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

    async def _send_staff_log(self, inter, action_type, role, users, reason="Не указана"):
        channel = inter.guild.get_channel(self.config["log_channel"])
        if not channel:
            return

        if action_type == "promote":
            title = "Выдача стафф роли"
            color = disnake.Color.green()
        else:
            title = "Снятие со стафф роли"
            color = disnake.Color.red()

        # Точный шаблон из вашего JSON
        role_line = f"{role.name} ({role.id})"
        executor_line = f"{inter.author.mention}\n• **Имя:** {inter.author.name}\n• **ID:** {inter.author.id}"
        reason_line = reason
        users_lines = "\n".join(f"• {u.mention} [{u.name}]" for u in users)

        description = (
            f"> **Роль:**\n```\n{role_line}\n```\n"
            f"> ** Исполнитель: **\n{executor_line}\n"
            f"> **Причина:**\n```\n{reason_line}\n```\n"
            f"> **Пользователи:**\n{users_lines}"
        )

        embed = disnake.Embed(title=title, description=description, color=color)
        await channel.send(embed=embed)

    # ---- команды с новым интерфейсом ----
    @commands.slash_command(name="staff", description="Управление составом")
    async def staff(self, inter: disnake.AppCmdInter):
        pass

    @staff.sub_command(name="promote", description="Выдать стафф-роль пользователю")
    async def staff_promote(self, inter: disnake.AppCmdInter):
        if not self._can_use_commands(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return
        embed = disnake.Embed(description="> Выберете 1 или несколько пользователей для выдачи роли")
        view = StaffUserSelectView(self, inter.author, action="promote", max_users=1)
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)

    @staff.sub_command(name="demote", description="Снять стафф-роль с одного или нескольких пользователей")
    async def staff_demote(self, inter: disnake.AppCmdInter):
        if not self._can_use_commands(inter.author):
            await inter.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return
        embed = disnake.Embed(description="> Выберете 1 или несколько пользователей для снятия роли")
        view = StaffUserSelectView(self, inter.author, action="demote", max_users=25)
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)


class StaffUserSelectView(disnake.ui.View):
    def __init__(self, cog, executor, action, max_users):
        super().__init__(timeout=60)
        self.cog = cog
        self.executor = executor
        self.action = action

        user_select = disnake.ui.UserSelect(
            placeholder="Выберите пользователей..." if max_users > 1 else "Выберите пользователя...",
            min_values=1,
            max_values=max_users,
            custom_id="staff_user_select"
        )
        user_select.callback = self.user_select_callback
        self.add_item(user_select)

    async def user_select_callback(self, inter: disnake.MessageInteraction):
        selected_users = inter.data.values
        members = []
        not_found = []
        for uid_str in selected_users:
            uid = int(uid_str)
            member = inter.guild.get_member(uid)
            if member:
                members.append(member)
            else:
                not_found.append(str(uid))

        if not members:
            msg = "❌ Нет доступных пользователей."
            if not_found:
                msg += f"\n❌ Не найдены: {', '.join(not_found)}"
            await inter.response.send_message(msg, ephemeral=True)
            return

        # Переход к выбору роли
        if self.action == "promote":
            embed = disnake.Embed(description="> Выберете роль для выдачи")
        else:
            embed = disnake.Embed(description="> Выберете роль для снятия")
        view = StaffRoleSelectView(self.cog, self.executor, self.action, members, not_found)
        await inter.response.edit_message(embed=embed, view=view)


class StaffRoleSelectView(disnake.ui.View):
    def __init__(self, cog, executor, action, members, not_found):
        super().__init__(timeout=60)
        self.cog = cog
        self.executor = executor
        self.action = action
        self.members = members
        self.not_found = not_found

        options = []
        for key, data in cog.role_levels.items():
            role_id = cog.config["roles"].get(key)
            if role_id and cog._can_manage_role(executor, key):
                options.append(disnake.SelectOption(
                    label=key.replace("_", " ").title(),
                    value=key,
                    description=f"Уровень {data['level']}, ветка {data['branch']}"
                ))

        if not options:
            options.append(disnake.SelectOption(label="Нет доступных ролей", value="none", default=True))

        select = disnake.ui.Select(placeholder="Выберите роль...", options=options, custom_id="staff_role_select")
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, inter: disnake.MessageInteraction):
        role_key = inter.data.values[0]
        if role_key == "none":
            await inter.response.send_message("❌ Нет доступных ролей.", ephemeral=True)
            return

        # Повторная проверка прав
        if not self.cog._can_manage_role(self.executor, role_key):
            await inter.response.send_message("❌ Вы больше не можете управлять этой ролью.", ephemeral=True)
            return

        role_id = self.cog.config["roles"].get(role_key)
        role = inter.guild.get_role(role_id)
        if not role:
            await inter.response.send_message("❌ Роль не найдена (возможно, удалена).", ephemeral=True)
            return

        if self.action == "promote":
            await self._handle_promote(inter, role)
        else:
            modal = StaffDemoteReasonModal(self.cog, self.executor, self.members, self.not_found, role, role_key)
            await inter.response.send_modal(modal)

    async def _handle_promote(self, inter, role):
        valid_members = []
        invalid_members = []
        for member in self.members:
            if role in member.roles:
                invalid_members.append(str(member.id))
            else:
                valid_members.append(member)

        if not valid_members:
            msg = "❌ Нет подходящих пользователей для выдачи роли."
            if self.not_found:
                msg += f"\n❌ Не найдены: {', '.join(self.not_found)}"
            if invalid_members:
                msg += f"\n⚠️ Уже имеют роль: {', '.join(invalid_members)}"
            await inter.response.send_message(msg, ephemeral=True)
            return

        reason = "Не указана"
        for member in valid_members:
            await member.add_roles(role, reason=reason)

        await self.cog._send_staff_log(inter, "promote", role, valid_members, reason)

        msg = f"✅ Роль {role.name} успешно выдана у {len(valid_members)} пользователей."
        if self.not_found:
            msg += f"\n❌ Не найдены: {', '.join(self.not_found)}"
        if invalid_members:
            msg += f"\n⚠️ Уже имеют роль: {', '.join(invalid_members)}"

        await inter.response.edit_message(content=msg, embed=None, view=None)


class StaffDemoteReasonModal(disnake.ui.Modal):
    def __init__(self, cog, executor, members, not_found, role, role_key):
        self.cog = cog
        self.executor = executor
        self.members = members
        self.not_found = not_found
        self.role = role
        self.role_key = role_key
        components = [
            disnake.ui.TextInput(
                label="Причина снятия",
                placeholder="Укажите причину снятия роли",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                required=True,
                max_length=500
            )
        ]
        super().__init__(title=f"Снятие роли {self.role.name}", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        reason = inter.text_values["reason"]

        if not self.cog._can_manage_role(self.executor, self.role_key):
            await inter.response.send_message("❌ Вы больше не можете управлять этой ролью.", ephemeral=True)
            return

        valid_members = []
        invalid_members = []
        for member in self.members:
            if self.role in member.roles:
                valid_members.append(member)
            else:
                invalid_members.append(str(member.id))

        if not valid_members:
            msg = "❌ Нет пользователей с данной ролью."
            if self.not_found:
                msg += f"\n❌ Не найдены: {', '.join(self.not_found)}"
            if invalid_members:
                msg += f"\n⚠️ Не имеют роли: {', '.join(invalid_members)}"
            await inter.response.send_message(msg, ephemeral=True)
            return

        for member in valid_members:
            await member.remove_roles(self.role, reason=reason)

        await self.cog._send_staff_log(inter, "demote", self.role, valid_members, reason)

        msg = f"✅ Роль {self.role.name} успешно снята у {len(valid_members)} пользователей."
        if self.not_found:
            msg += f"\n❌ Не найдены: {', '.join(self.not_found)}"
        if invalid_members:
            msg += f"\n⚠️ Не имеют роли: {', '.join(invalid_members)}"

        await inter.response.send_message(msg, ephemeral=True)


def setup(bot):
    bot.add_cog(StaffControl(bot))