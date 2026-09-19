"""Opt-in actual multicast acceptance on loopback; three isolated synthetic peers."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.connect_process_fixture import acceptance

if __name__ == '__main__':
    acceptance(discovery=True)
    print('PASS: actual loopback mDNS, three processes, C2 mTLS, ping/status, replay, reconnect, spoof rejection, revocation, shutdown')
