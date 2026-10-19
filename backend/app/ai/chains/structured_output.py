from ..runtime import invoke_json


def run(settings, messages):
    return invoke_json(settings, messages)
