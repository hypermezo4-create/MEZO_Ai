class FlyPlugin:
    def deploy_app(self, app_name: str, config_path: str) -> dict:
        return {"plugin": "FlyPlugin", "app": app_name, "config": config_path, "status": "deployed"}
