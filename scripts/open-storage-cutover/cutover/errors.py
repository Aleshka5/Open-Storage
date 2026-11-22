"""Refusals for the cutover planners. Nothing in this package connects to a service."""


class CutoverRefused(Exception):
    """The plan will not do this. No dump, mirror, or write was started."""
