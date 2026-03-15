from .honeygain import HoneygainCollector
from .earnapp import EarnAppCollector
from .iproyal import IPRoyalCollector
from .packetstream import PacketStreamCollector
from .traffmonetizer import TraffmonetizerCollector


def make_collectors():
    return [
        HoneygainCollector(),
        EarnAppCollector(),
        IPRoyalCollector(),
        PacketStreamCollector(),
        TraffmonetizerCollector(),
    ]


ALL_COLLECTORS = make_collectors()
