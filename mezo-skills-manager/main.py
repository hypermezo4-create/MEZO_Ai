from src.skill_loader import SkillLoader
from src.skill_executor import SkillExecutor

def main():
    loader = SkillLoader()
    skills = loader.discover_skills()
    print(f"[MEZO Skills Manager] Discovered {len(skills)} skill modules.")
    executor = SkillExecutor()
    res = executor.execute("system-skills/file_management.py")
    print(f"[MEZO Skills Manager] Execution test: {res}")

if __name__ == "__main__":
    main()
