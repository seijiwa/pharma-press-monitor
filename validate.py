import csv,sys
from pathlib import Path
p=Path(__file__).resolve().parent
r=list(csv.DictReader(open(p/'companies.csv',encoding='utf-8-sig')))
assert len(r)==71, len(r)
assert all(x['Official/Source page'].startswith('http') for x in r)
assert len({x['Company'] for x in r})==71
b=[x for x in r if x['Company']=='Biogen']; assert len(b)==1 and 'biogen' in b[0]['Official/Source page'].lower()
print('PASS: 71/71 unique companies; all official source URLs populated; Biogen included:',b[0]['Official/Source page'])
