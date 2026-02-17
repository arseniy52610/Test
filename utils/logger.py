async def log_action(guild, channel_id, embed):
    channel = guild.get_channel(channel_id)
    if channel:
        await channel.send(embed=embed)
