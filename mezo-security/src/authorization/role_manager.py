class RoleManager:
    def __init__(self):
        self.roles = {"admin": ["*"], "user": ["read", "chat"]}

    def check_permission(self, role: str, action: str) -> bool:
        perms = self.roles.get(role, [])
        return "*" in perms or action in perms
