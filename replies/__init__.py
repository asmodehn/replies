from .mock import AsksMock
from .reply import CallbackReply, Reply

# useful for tests
from .reply import BaseReply, std_mock


# expose default mock namespace
mock = _default_mock = AsksMock(assert_all_requests_are_fired=False)
__all__ = ["CallbackReply", "Reply", "AsksMock"]
for __attr in (a for a in dir(_default_mock) if not a.startswith("_")):
    __all__.append(__attr)
    globals()[__attr] = getattr(_default_mock, __attr)

