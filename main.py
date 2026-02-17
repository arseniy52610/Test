import disnake
from disnake.ext import commands, tasks
import json
import os
import datetime

# Используем InteractionBot (не требует префикса)
intents = disnake.Intents.all()
bot = commands.InteractionBot(intents=intents)

with open("config.json") as f:
    config = json.load(f)

# Загружаем все коги из папки cogs
for file in os.listdir("./cogs"):
    if file.endswith(".py") and file != "__init__.py":
        bot.load_extension(f"cogs.{file[:-3]}")

# Автоснятие наказаний по времени
@tasks.loop(minutes=1)
async def check_punishments():
    # Пытаемся загрузить данные, обрабатываем возможные ошибки
    try:
        with open("data/punishments.json", "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Если файл не найден или пуст/повреждён, инициализируем пустой словарь
        data = {}

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    changed = False

    # Проходим по каждому пользователю
    for user_id in list(data.keys()):
        punishments = data[user_id]  # список наказаний
        new_punishments = []
        for p in punishments:
            # Если наказание имеет срок и он истёк
            if p.get("end_time") and now >= p["end_time"]:
                # Пытаемся снять роль
                guild = bot.guilds[0]  # предполагаем, что бот на одном сервере
                member = guild.get_member(int(user_id))
                if member:
                    role = guild.get_role(p["role_id"])
                    if role:
                        await member.remove_roles(role)
                    try:
                        embed = disnake.Embed(
                            title="✅ Наказание снято",
                            color=0x2ecc71
                        )
                        if guild.icon:
                            embed.set_thumbnail(url=guild.icon.url)
                        embed.add_field(name="Сервер", value=guild.name, inline=False)
                        embed.add_field(name="Тип наказания", value=p["type"], inline=False)
                        embed.add_field(name="Причина снятия", value="Срок наказания истёк", inline=False)
                        await member.send(embed=embed)
                    except Exception:
                        pass
                changed = True
                # это наказание не добавляем в новый список (оно удаляется)
            else:
                new_punishments.append(p)

        # Обновляем список или удаляем пользователя, если наказаний не осталось
        if new_punishments:
            data[user_id] = new_punishments
        else:
            del data[user_id]

    # Если были изменения, сохраняем обновлённые данные
    if changed:
        with open("data/punishments.json", "w") as f:
            json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")
    check_punishments.start()

bot.run(config["token"])