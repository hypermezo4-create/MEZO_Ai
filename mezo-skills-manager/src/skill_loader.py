import os

class SkillLoader:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir

    def discover_skills(self) -> list:
        skills = []
        for root, _, files in os.walk(self.skills_dir):
            for file in files:
                if file.endswith(".py"):
                    skills.append(os.path.join(root, file))
        return skills
