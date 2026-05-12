from enum import StrEnum


class Status(StrEnum):
    new = "new"
    contacted = "contacted"
    onboarding = "onboarding"
    installed = "installed"
