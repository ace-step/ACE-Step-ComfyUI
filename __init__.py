from .nodes import AceStepMusicGen

NODE_CLASS_MAPPINGS = {
    "AceStepMusicGen": AceStepMusicGen,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AceStepMusicGen": "ACE-Step Music Generate",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
