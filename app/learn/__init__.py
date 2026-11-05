"""The teaching library: topics (Markdown files) explaining the terms the dashboard shows. No GUI code lives here."""
from .library import Issue, TopicLibrary, load_library
from .model import Topic, normalize

__all__ = ['Issue', 'Topic', 'TopicLibrary', 'load_library', 'normalize']
