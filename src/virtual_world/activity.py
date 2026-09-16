"""Durable public activity from the local research runner and Ollama API."""

from contextvars import ContextVar

current_trace = ContextVar("research_trace", default=None)


class ResearchStopped(Exception):
    pass


class Trace:
    def __init__(self, store, id):
        self.store = store
        self.id = id
        self.round = 0

    def emit(self, kind, message, **data):
        self.store.append_event(self.id, kind, message, {"round": self.round, **data})

    def check_stop(self):
        if self.store.job(self.id)["status"] != "running":
            raise ResearchStopped("Stop requested")


def emit(kind, message, **data):
    trace = current_trace.get()
    if trace:
        trace.emit(kind, message, **data)
