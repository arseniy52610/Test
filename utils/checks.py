def has_role(member, role_id):
    return any(role.id == role_id for role in member.roles)
