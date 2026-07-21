class FileManagementSkill:
    def list_dir(self, path: str) -> list:
        return [f"Item in {path}"]

    def read_file(self, path: str) -> str:
        return f"Content of {path}"
