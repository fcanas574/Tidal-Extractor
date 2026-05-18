import yaml
from pathlib import Path


DEFAULTS = {
    "default_quality": "high_lossless",
    "default_format": "FLAC",
    "output_dir": "~/Music/TidalDownloads",
}


class AppConfig:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.default_quality: str = DEFAULTS["default_quality"]
        self.default_format: str = DEFAULTS["default_format"]
        self.output_dir: str = DEFAULTS["output_dir"]
        self._load()

    def _load(self):
        path = Path(self.config_path)
        if path.exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
            self.default_quality = data.get("default_quality", self.default_quality)
            self.default_format = data.get("default_format", self.default_format)
            self.output_dir = data.get("output_dir", self.output_dir)

    def save(self):
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(
                {
                    "default_quality": self.default_quality,
                    "default_format": self.default_format,
                    "output_dir": self.output_dir,
                },
                f,
                default_flow_style=False,
            )

    def update(self, **kwargs):
        if "default_quality" in kwargs:
            self.default_quality = kwargs["default_quality"]
        if "default_format" in kwargs:
            self.default_format = kwargs["default_format"]
        if "output_dir" in kwargs:
            self.output_dir = kwargs["output_dir"]

    def as_dict(self):
        return {
            "default_quality": self.default_quality,
            "default_format": self.default_format,
            "output_dir": self.output_dir,
        }
