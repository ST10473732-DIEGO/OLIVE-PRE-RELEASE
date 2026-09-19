"""Discord role/channel overwrite calculation for bounded bot destination lists."""
def permissions(guild, member, channel, bot_id):
    roles=set(member.get('roles',[]));roles.add(guild['id'])
    base=0
    for role in guild.get('roles',[]):
        if role['id'] in roles:base|=int(role['permissions'])
    if base & 8 or guild.get('owner_id')==bot_id:return (1<<10)|(1<<11)
    overrides=channel.get('permission_overwrites',[])
    for overwrite in overrides:
        if overwrite['id']==guild['id']:base=(base & ~int(overwrite['deny']))|int(overwrite['allow'])
    deny=allow=0
    for overwrite in overrides:
        if overwrite['type']==0 and overwrite['id'] in roles and overwrite['id']!=guild['id']:
            deny|=int(overwrite['deny']);allow|=int(overwrite['allow'])
    base=(base & ~deny)|allow
    for overwrite in overrides:
        if overwrite['type']==1 and overwrite['id']==bot_id:base=(base & ~int(overwrite['deny']))|int(overwrite['allow'])
    return base
