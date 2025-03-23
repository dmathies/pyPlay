import json

class ConfigManager:
  def __init__(self, config_path="config.json"):
    self.config_path = config_path
    self.config = self.load_config()

  def load_config(self):
    try:
      with open(self.config_path, "r") as file:
        return json.load(file)
    except FileNotFoundError:
      return {
        "dmx_config": {"universe": 0, "net": 0, "sub": 0},
        "osc_config": {"osc_port": 9000, "osc_name": "Video1"},
        "ip_address": "auto",
      }

  def save_config(self):
    with open(self.config_path, "w") as file:
      json.dump(self.config, file, indent=4)

  def get_ip_address(self):
    return self.config.get("ip_address", "auto")

  def get_dmx_config(self):
    return self.config.get("dmx_config", {})

  def get_osc_port(self):
    return self.config.get("osc_config", {}).get("osc_port", 9000)
