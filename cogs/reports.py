import disnake
from disnake.ext import commands
import json
import datetime
import os


def load_reports():
    try:
        with open("data/reports.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"count": 0, "reports": {}}


def save_reports(data):
    os.makedirs("data", exist_ok=True)
    with open("data/reports.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


class Reports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_config(self):
        with open("config.json", encoding="utf-8") as f:
            return json.load(f)

    @commands.slash_command(name="report", description="Пожаловаться на участника")
    async def report(
        self,
        inter: disnake.AppCmdInter,
        user: disnake.Member = commands.Param(name="участник", description="На кого жалуетесь"),
        reason: str = commands.Param(name="причина", description="Причина жалобы")
    ):
        config = self._get_config()
        channel = inter.guild.get_channel(config["report_channel"])
        if not channel:
            await inter.response.send_message("❌ Канал репортов не настроен.", ephemeral=True)
            return

        if user.id == inter.author.id:
            await inter.response.send_message("❌ Нельзя пожаловаться на самого себя.", ephemeral=True)
            return

        if user.bot:
            await inter.response.send_message("❌ Нельзя пожаловаться на бота.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        reports_data = load_reports()
        reports_data["count"] += 1
        report_num = reports_data["count"]

        embed = disnake.Embed(
            title=f"Жалоба #{report_num} — {user.display_name}",
            color=0xe74c3c,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_author(
            name=f"От: {inter.author.display_name} ({inter.author.name})",
            icon_url=inter.author.display_avatar.url
        )
        embed.add_field(
            name="Нарушитель",
            value=f"{user.mention}\n`ID: {user.id}`",
            inline=True
        )
        embed.add_field(
            name="Подающий жалобу",
            value=f"{inter.author.mention}\n`ID: {inter.author.id}`",
            inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.set_footer(text=f"Репорт #{report_num}")

        reports_data["reports"][str(report_num)] = {
            "reporter_id": inter.author.id,
            "target_id": user.id,
            "reason": reason,
            "status": "pending"
        }
        save_reports(reports_data)

        view = ReportView(report_num)
        await channel.send(embed=embed, view=view)

        confirm_embed = disnake.Embed(
            description=f"✅ Ваша жалоба **#{report_num}** на **{user.display_name}** отправлена.",
            color=0x2ecc71
        )
        await inter.edit_original_response(embed=confirm_embed)

    @commands.Cog.listener()
    async def on_button_click(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id

        if custom_id.startswith("report_accept_"):
            report_num = int(custom_id.split("_")[-1])
            modal = ReportActionModal(report_num, "accept")
            await inter.response.send_modal(modal)

        elif custom_id.startswith("report_reject_"):
            report_num = int(custom_id.split("_")[-1])
            modal = ReportActionModal(report_num, "reject")
            await inter.response.send_modal(modal)


class ReportView(disnake.ui.View):
    def __init__(self, report_num: int):
        super().__init__(timeout=None)
        self.add_item(disnake.ui.Button(
            label="Принять",
            style=disnake.ButtonStyle.success,
            custom_id=f"report_accept_{report_num}",
        ))
        self.add_item(disnake.ui.Button(
            label="Отклонить",
            style=disnake.ButtonStyle.danger,
            custom_id=f"report_reject_{report_num}",
        ))


class ReportActionModal(disnake.ui.Modal):
    def __init__(self, report_num: int, action: str):
        self.report_num = report_num
        self.action = action
        title = "Принять жалобу" if action == "accept" else "Отклонить жалобу"
        components = [
            disnake.ui.TextInput(
                label="Примечание / причина",
                placeholder="Укажите причину или принятые меры",
                custom_id="note",
                style=disnake.TextInputStyle.paragraph,
                max_length=300,
                required=False,
            )
        ]
        super().__init__(title=title, components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        note = inter.text_values.get("note", "").strip()

        data = load_reports()
        report_info = data["reports"].get(str(self.report_num), {})

        if self.action == "accept":
            data["reports"][str(self.report_num)]["status"] = "accepted"
            status_label = "✅ Принята"
            color = 0x2ecc71
        else:
            data["reports"][str(self.report_num)]["status"] = "rejected"
            status_label = "❌ Отклонена"
            color = 0x95a5a6

        save_reports(data)

        # Edit the original embed
        if inter.message.embeds:
            orig = inter.message.embeds[0]
            new_embed = disnake.Embed(
                title=orig.title,
                color=color,
                timestamp=orig.timestamp
            )
            if orig.thumbnail:
                new_embed.set_thumbnail(url=orig.thumbnail.url)
            if orig.author:
                new_embed.set_author(name=orig.author.name, icon_url=orig.author.icon_url)
            for field in orig.fields:
                new_embed.add_field(name=field.name, value=field.value, inline=field.inline)
            if orig.footer:
                new_embed.set_footer(text=orig.footer.text)

            mod_note = f"\nПримечание: {note}" if note else ""
            new_embed.add_field(
                name=f"Статус: {status_label}",
                value=f"Модератор: {inter.author.mention}{mod_note}",
                inline=False
            )
            await inter.response.edit_message(embed=new_embed, view=None)
        else:
            await inter.response.edit_message(view=None)

        await inter.followup.send(
            f"Жалоба **#{self.report_num}** — {status_label.lower()}.",
            ephemeral=True
        )


def setup(bot):
    bot.add_cog(Reports(bot))
