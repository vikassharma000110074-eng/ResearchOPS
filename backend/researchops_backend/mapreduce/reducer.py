#!/usr/bin/env python3
import sys
current=None; total=0
for line in sys.stdin:
    try: key,val=line.rstrip('\n').split('\t',1); val=int(val)
    except Exception: continue
    if current is None: current=key; total=val
    elif key==current: total+=val
    else: print(f'{current}\t{total}'); current=key; total=val
if current is not None: print(f'{current}\t{total}')
