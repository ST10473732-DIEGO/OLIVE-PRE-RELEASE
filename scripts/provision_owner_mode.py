"""Owner-authorized setup/rollback. Not a model tool or launch hook."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from olive.identity import resolve_profile
from olive.authority.migration import migrate
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--restore',action='store_true');a=p.parse_args()
 print(json.dumps(migrate(a.profile or resolve_profile(),a.receipt,a.restore)))
