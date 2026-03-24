from .honeygain import HoneygainCollector
from .earnapp import EarnAppCollector
from .iproyal import IPRoyalCollector
from .packetstream import PacketStreamCollector
from .traffmonetizer import TraffmonetizerCollector
from .repocket import RepocketCollector
from .earnfm import EarnfmCollector
from .proxyrack import ProxyRackCollector
from .bitping import BitpingCollector
from .mysterium import MysteriumCollector


def make_collectors():
    return [
        HoneygainCollector(),
        EarnAppCollector(),
        IPRoyalCollector(),
        PacketStreamCollector(),
        TraffmonetizerCollector(),
        RepocketCollector(),
        EarnfmCollector(),
        ProxyRackCollector(),
        BitpingCollector(),
        MysteriumCollector(),
    ]


ALL_COLLECTORS = make_collectors()
