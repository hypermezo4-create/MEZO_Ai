class Preprocessor:
    def clean_dataset(self, data: list) -> list:
        return [item for item in data if item.get("prompt")]
