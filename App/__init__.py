__all__ = ["AgentRunReport", "maintain_wiki"]


def __getattr__(name):
    if name in __all__:
        from App.agent import AgentRunReport, maintain_wiki

        return {
            "AgentRunReport": AgentRunReport,
            "maintain_wiki": maintain_wiki,
        }[name]
    raise AttributeError(name)
