from .nodes import (
    AceStepAudioCodes,
    AceStepText2MusicGenParams,
    AceStepSettings,
    AceStepText2MusicServer,
    AceStepShowText,
)

NODE_CLASS_MAPPINGS = {
    "AceStepAudioCodes": AceStepAudioCodes,
    "AceStepText2MusicGenParams": AceStepText2MusicGenParams,
    "AceStepSettings": AceStepSettings,
    "AceStepText2MusicServer": AceStepText2MusicServer,
    "AceStepShowText": AceStepShowText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AceStepAudioCodes": "ACE-Step Audio Codes",
    "AceStepText2MusicGenParams": "ACE-Step Text2music Gen Params",
    "AceStepSettings": "ACE-Step Settings",
    "AceStepText2MusicServer": "ACE-Step Text2music Server",
    "AceStepShowText": "ACE-Step Show Text",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
