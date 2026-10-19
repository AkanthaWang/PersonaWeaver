from ..extraction_graph import extract_chapter


def run(settings, title, text):
    return extract_chapter(settings, title, text)
