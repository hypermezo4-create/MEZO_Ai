class SystemAgent:
    def __init__(self, name: str = "SystemAgent"):
        self.name = name

    def execute_command(self, cmd: str) -> dict:
        return {"agent": self.name, "command": cmd, "status": "executed", "exit_code": 0}
