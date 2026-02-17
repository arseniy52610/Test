import disnake
from disnake.ext import commands
import json
import datetime

class NickHistory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file = "data/nicknames.json"

    def load_data(self):
        try:
            with open(self.file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_data(self, data):
        with open(self.file, "w") as f:
            json.dump(data, f, indent=4)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.display_name != after.display_name:
            data = self.load_data()
            user_id = str(after.id)
            if user_id not in data:
                data[user_id] = []
            data[user_id].append({
                "nickname": after.display_name,
                "timestamp": datetime.datetime.utcnow().timestamp()
            })
            self.save_data(data)

    @commands.slash_command(name="history_nick", description="История никнеймов пользователя")
    async def history_nick(self, inter, user: disnake.Member = None):
        if not user:
            user = inter.author
        data = self.load_data()
        entries = data.get(str(user.id), [])
        if not entries:
            await inter.response.send_message("История никнеймов пуста.", ephemeral=True)
            return
        embed = disnake.Embed(title=f"История никнеймов {user.display_name}", color=disnake.Color.blue())
        for entry in entries[-10:]:  # последние 10
            dt = datetime.datetime.fromtimestamp(entry["timestamp"])
            embed.add_field(name=dt.strftime("%d.%m.%Y %H:%M"), value=entry["nickname"], inline=False)
        await inter.response.send_message(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(NickHistory(bot))